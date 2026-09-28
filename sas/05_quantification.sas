/*=============================================================================
  05_quantification.sas  -  Calibration, downturn, MoC, input floor, application
  -----------------------------------------------------------------------------
  SAS equivalent of python/ead_ccf/quantification.py

  model prediction
    -> x calibration factor  (mean prediction = segment LRA)
    -> + downturn add-on     (downturn CCF - LRA, >= 0)
    -> + MoC (A + B + C)
    -> floored at 50% x SA CCF (CRR3 input floor)

  NOTE on reconciliation: MoC category C uses a bootstrap. SAS and Python use
  different random number generators, so category C (and therefore final CCFs)
  agree only approximately. All other steps must agree to rounding precision.
=============================================================================*/

/*---------------------------------------------------------------------------
  1. Calibration factors on the full sample
---------------------------------------------------------------------------*/
%score_fractional_logit(pe=derived.recon_fractional_logit, in=derived.x_all, out=_scored_all);

proc sql;
  create table derived.calibration_factors as
  select a.calib_segment, b.lra / a.mean_pred as calibration_factor
  from (select calib_segment, mean(ccf_pred_raw) as mean_pred
        from _scored_all group by calib_segment) a
  inner join derived.recon_lra_by_segment b
  on a.calib_segment = b.calib_segment
  order by calib_segment;
quit;

/*---------------------------------------------------------------------------
  2. Downturn years: N worst years by average realised CCF + macro candidates
---------------------------------------------------------------------------*/
proc sort data=derived.yearly out=_yr; by descending mean_ccf; run;
data _null_;
  set _yr(obs=&n_worst_years) end=last;
  length yrs $200;
  retain yrs '';
  yrs = catx(' ', yrs, default_year);
  if last then call symputx('data_dt_years', yrs);
run;

data _dt_years;
  length default_year 8;
  do i = 1 to countw("&data_dt_years &macro_dt_years");
    default_year = input(scan("&data_dt_years &macro_dt_years", i), 8.);
    output;
  end;
  keep default_year;
run;
proc sort data=_dt_years nodupkey; by default_year; run;
%put NOTE: data-driven downturn years = &data_dt_years ; macro = &macro_dt_years;

/*---------------------------------------------------------------------------
  3. Downturn CCF per segment = max(LRA, mean realised CCF in downturn years)
---------------------------------------------------------------------------*/
proc sql noprint;
  select mean(ccf_realised) into :dt_mean_port trimmed
  from derived.rds where default_year in (select default_year from _dt_years);
  select mean(ccf_realised) into :lra_port trimmed from derived.rds;
quit;

proc sql;
  create table derived.downturn as
  select l.calib_segment, l.lra,
         coalesce(d.n_downturn_obs, 0) as n_downturn_obs,
         case when coalesce(d.n_downturn_obs, 0) >= &min_dt_obs then d.dt_mean
              else l.lra * (&dt_mean_port / &lra_port) end as downturn_observed,
         (coalesce(d.n_downturn_obs, 0) < &min_dt_obs) as fallback_portfolio_ratio
  from derived.recon_lra_by_segment l
  left join (select calib_segment, count(*) as n_downturn_obs, mean(ccf_realised) as dt_mean
             from derived.rds
             where default_year in (select default_year from _dt_years)
             group by calib_segment) d
  on l.calib_segment = d.calib_segment
  order by calib_segment;
quit;

data derived.downturn;
  set derived.downturn;
  downturn_ccf    = max(downturn_observed, lra);
  downturn_addon  = downturn_ccf - lra;   /* additive: robust when LRA <= 0 */
run;

/*---------------------------------------------------------------------------
  4. Margin of conservatism
     A: |LRA(all) - LRA(complete ratings)|   B: |LRA - LRA(capped at 100%)|
     C: bootstrap quantile - bootstrap mean
---------------------------------------------------------------------------*/
proc sql;
  create table _moc_ab as
  select calib_segment, count(*) as n, mean(ccf_realised) as lra,
         abs(calculated lra
             - (sum(ccf_realised * (not missing(grade_ref))) / sum(not missing(grade_ref))))
             as moc_A_data,
         abs(calculated lra - mean(min(ccf_realised, 1))) as moc_B_method
  from derived.rds group by calib_segment;
quit;

proc sort data=derived.rds out=_rds_seg; by calib_segment; run;
proc surveyselect data=_rds_seg out=_boot method=urs samprate=1 outhits
                  reps=&boot_samples seed=&seed noprint;
  strata calib_segment;
run;
proc means data=_boot noprint nway;
  class replicate calib_segment;
  var ccf_realised;
  output out=_boot_means(keep=calib_segment replicate boot_mean) mean=boot_mean;
run;
%let q_pct = %sysevalf(&moc_confidence * 100);
proc univariate data=_boot_means noprint pctldef=5;
  class calib_segment;
  var boot_mean;
  output out=_boot_q mean=boot_avg pctlpts=&q_pct pctlpre=q_;
run;
data _boot_q;
  set _boot_q;
  moc_C_estimation = max(q_%sysfunc(round(&q_pct)) - boot_avg, 0);
  keep calib_segment moc_C_estimation;
run;

proc sql;
  create table derived.moc as
  select a.*, b.moc_C_estimation,
         a.moc_A_data + a.moc_B_method + b.moc_C_estimation as moc_total
  from _moc_ab a inner join _boot_q b on a.calib_segment = b.calib_segment
  order by calib_segment;
quit;

/*---------------------------------------------------------------------------
  5. Final CCF (macro used for both the RDS and the performing portfolio)
---------------------------------------------------------------------------*/
%macro final_ccf(in=, out=);
  proc sql;
    create table &out as
    select s.*, c.calibration_factor as _cf, d.lra as _lra, d.downturn_addon,
           m.moc_total as moc
    from &in s
    left join derived.calibration_factors c on s.calib_segment = c.calib_segment
    left join derived.downturn d            on s.calib_segment = d.calib_segment
    left join derived.moc m                 on s.calib_segment = m.calib_segment;
  quit;
  data &out;
    set &out;
    if facility_type = 'STANDARD' then do;
      ccf_model = ccf_pred_raw;
      calibration_factor = coalesce(_cf, 1);
    end;
    else do;
      ccf_model = _lra;
      calibration_factor = 1;
    end;
    ccf_calibrated   = ccf_model * calibration_factor;
    ccf_downturn     = ccf_calibrated + coalesce(downturn_addon, 0);
    ccf_before_floor = ccf_downturn + coalesce(moc, 0);
    input_floor      = 0.5 * input(put(product, $sa_ccf.), 8.);
    ccf_final        = max(ccf_before_floor, input_floor);
    floor_binding    = (ccf_final > ccf_before_floor);
    drop _cf _lra;
  run;
%mend final_ccf;

/* RDS: STANDARD facilities get the model score, others the segment LRA */
%build_features(in=derived.rds, out=_rds_x, grade_median=&grade_median_all);
%score_fractional_logit(pe=derived.recon_fractional_logit, in=_rds_x, out=_rds_scored);
%final_ccf(in=_rds_scored, out=derived.final_rds);

proc sql;
  create table derived.final_segment as
  select calib_segment, count(*) as n, mean(ccf_model) as ccf_model,
         mean(ccf_calibrated) as ccf_calibrated, mean(downturn_addon) as downturn_addon,
         mean(moc) as moc, mean(input_floor) as input_floor, mean(ccf_final) as ccf_final,
         mean(floor_binding) as share_floor_binding
  from derived.final_rds group by calib_segment order by calib_segment;
quit;

/*---------------------------------------------------------------------------
  6. Application to the performing portfolio
---------------------------------------------------------------------------*/
data _perf;
  set raw.performing;
  length facility_type $12 util_band $10 calib_segment $24;
  util = drawn_ref / limit_ref;
  if drawn_ref >= limit_ref            then facility_type = 'FULLY_DRAWN';
  else if util >= &roi_threshold       then facility_type = 'ROI';
  else                                      facility_type = 'STANDARD';
  util_c = min(max(util, 0), 1);
  if util_c < &band1_upper      then util_band = 'U1_lt50';
  else if util_c < &band2_upper then util_band = 'U2_50_95';
  else                               util_band = 'U3_ge95';
  calib_segment = catx('/', product, util_band);
  drop util_c;
run;
%build_features(in=_perf, out=_perf_x, grade_median=&grade_median_all);
%score_fractional_logit(pe=derived.recon_fractional_logit, in=_perf_x, out=_perf_scored);
%final_ccf(in=_perf_scored, out=_perf_final);

data derived.application_ead;
  set _perf_final;
  undrawn = max(limit_ref - drawn_ref, 0);
  if util >= &roi_threshold then denom = max(undrawn, (1 - &roi_threshold) * limit_ref);
  else denom = undrawn;
  ead_irb = drawn_ref + ccf_final * denom;
  ead_sa  = drawn_ref + input(put(product, $sa_ccf.), 8.) * undrawn;
run;

proc sql;
  create table derived.application as
  select product, count(*) as n, sum(limit_ref) as limit, sum(drawn_ref) as drawn,
         mean(ccf_final) as mean_ccf_final, mean(floor_binding) as share_floor_binding,
         sum(ead_irb) as ead_irb, sum(ead_sa) as ead_sa,
         calculated ead_irb / calculated ead_sa as ead_irb_over_sa
  from derived.application_ead group by product
  union all
  select 'TOTAL', count(*), sum(limit_ref), sum(drawn_ref), mean(ccf_final),
         mean(floor_binding), sum(ead_irb), sum(ead_sa), sum(ead_irb) / sum(ead_sa)
  from derived.application_ead;
quit;
