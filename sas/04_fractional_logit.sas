/*=============================================================================
  04_fractional_logit.sas  -  Risk differentiation: fractional logit
  -----------------------------------------------------------------------------
  SAS equivalent of models.FeatureBuilder + models.FractionalLogit (Python).

  Papke & Wooldridge (1996) quasi-likelihood:
      maximise  sum[ y*eta - log(1 + exp(eta)) ],  eta = X*b,  y in [0,1]
  PROC NLMIXED with the EMPIRICAL option gives the robust (sandwich) covariance,
  the same estimator as the Python implementation.

  Only STANDARD facilities are modelled. limit_cut_flag is NOT a driver
  (it happens after the reference date - decision D006).

  NOTE: in NLMIXED a parameter may not have the same name as a data set
  variable, so the features are prefixed "x_" and the parameters carry the
  Python variable names. This keeps the reconciliation keys identical.
=============================================================================*/

/*---------------------------------------------------------------------------
  Feature construction (imputation value learned on the fitting sample)
---------------------------------------------------------------------------*/
%macro build_features(in=, out=, grade_median=);
  data &out;
    set &in;
    x_utilisation   = min(max(drawn_ref / limit_ref, 0), 1);
    x_log_limit     = log(limit_ref);
    x_grade_missing = missing(grade_ref);
    x_grade         = coalesce(grade_ref, &grade_median);
    x_arrears_6m    = arrears_flag_6m;
    x_log_mob       = log(1 + months_on_book);
    x_prod_RET_CARD = (product = 'RET_CARD');
    x_prod_SME_CRL  = (product = 'SME_CRL');
    x_prod_CORP_RCF = (product = 'CORP_RCF');    /* base product = RET_OVD */
  run;
%mend build_features;

/*---------------------------------------------------------------------------
  Fit + tidy parameter table (variable, coefficient, robust_se, z, p)
---------------------------------------------------------------------------*/
%macro fit_fractional_logit(in=, pe_out=);
  proc nlmixed data=&in empirical tech=newrap;
    parms intercept=0 utilisation=0 log_limit=0 grade_missing=0 grade=0
          arrears_6m=0 log_mob=0 prod_RET_CARD=0 prod_SME_CRL=0 prod_CORP_RCF=0;
    eta = intercept
        + utilisation   * x_utilisation
        + log_limit     * x_log_limit
        + grade_missing * x_grade_missing
        + grade         * x_grade
        + arrears_6m    * x_arrears_6m
        + log_mob       * x_log_mob
        + prod_RET_CARD * x_prod_RET_CARD
        + prod_SME_CRL  * x_prod_SME_CRL
        + prod_CORP_RCF * x_prod_CORP_RCF;
    ll = ccf_model_target * eta - log(1 + exp(eta));
    model ccf_model_target ~ general(ll);
    ods output ParameterEstimates = _pe_raw;
  run;

  data &pe_out;
    set _pe_raw(keep=parameter estimate standarderror);
    length variable $32;
    variable  = parameter;
    coefficient = estimate;
    robust_se = standarderror;
    z_value   = coefficient / robust_se;
    p_value   = 2 * (1 - probnorm(abs(z_value)));   /* normal, as in Python */
    keep variable coefficient robust_se z_value p_value;
  run;
%mend fit_fractional_logit;

/*---------------------------------------------------------------------------
  Scoring: prediction = 1 / (1 + exp(-X*b)) using a parameter table
---------------------------------------------------------------------------*/
%macro score_fractional_logit(pe=, in=, out=, predvar=ccf_pred_raw);
  data _null_;
    set &pe;
    call symputx(cats('b_', variable), coefficient);
  run;
  data &out;
    set &in;
    _eta = &b_intercept
         + &b_utilisation   * x_utilisation
         + &b_log_limit     * x_log_limit
         + &b_grade_missing * x_grade_missing
         + &b_grade         * x_grade
         + &b_arrears_6m    * x_arrears_6m
         + &b_log_mob       * x_log_mob
         + &b_prod_RET_CARD * x_prod_RET_CARD
         + &b_prod_SME_CRL  * x_prod_SME_CRL
         + &b_prod_CORP_RCF * x_prod_CORP_RCF;
    &predvar = 1 / (1 + exp(-_eta));
    drop _eta;
  run;
%mend score_fractional_logit;

/*---------------------------------------------------------------------------
  A. Development fit (used for out-of-time testing in 06_validation.sas)
---------------------------------------------------------------------------*/
proc means data=derived.rds noprint median;
  where facility_type = 'STANDARD' and sample = 'DEV';
  var grade_ref;
  output out=_med median=grade_median;
run;
data _null_; set _med; call symputx('grade_median_dev', grade_median); run;

data _std_dev _std_oot;
  set derived.rds;
  where facility_type = 'STANDARD';
  if sample = 'DEV' then output _std_dev; else output _std_oot;
run;
%build_features(in=_std_dev, out=derived.x_dev, grade_median=&grade_median_dev);
%build_features(in=_std_oot, out=derived.x_oot, grade_median=&grade_median_dev);
%fit_fractional_logit(in=derived.x_dev, pe_out=derived.fl_dev);

/*---------------------------------------------------------------------------
  B. Full-sample fit (final model, reconciled with Python)
---------------------------------------------------------------------------*/
proc means data=derived.rds noprint median;
  where facility_type = 'STANDARD';
  var grade_ref;
  output out=_med median=grade_median;
run;
data _null_; set _med; call symputx('grade_median_all', grade_median); run;

data _std_all; set derived.rds; where facility_type = 'STANDARD'; run;
%build_features(in=_std_all, out=derived.x_all, grade_median=&grade_median_all);
%fit_fractional_logit(in=derived.x_all, pe_out=derived.recon_fractional_logit);

title "Fractional logit - full sample (robust standard errors)";
proc print data=derived.recon_fractional_logit noobs; run;
title;
