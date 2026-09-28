/*=============================================================================
  06_validation.sas  -  Performance testing on development and out-of-time
  -----------------------------------------------------------------------------
  SAS equivalent of python/ead_ccf/validation.py

  accuracy      : MAE, RMSE, R2, EAD predicted / actual
  discrimination: Spearman rank correlation (PROC CORR)
  calibration   : one-sided t-test per segment, H0: mean(realised) <= estimate
  stability     : PSI of drivers, development vs out-of-time
=============================================================================*/

/*---------------------------------------------------------------------------
  1. Score development and OOT with the DEVELOPMENT model and calibrate to
     the development LRA
---------------------------------------------------------------------------*/
%score_fractional_logit(pe=derived.fl_dev, in=derived.x_dev, out=_sd);
%score_fractional_logit(pe=derived.fl_dev, in=derived.x_oot, out=_so);

proc sql;
  create table _cf_dev as
  select a.calib_segment, b.lra / a.mean_pred as cf
  from (select calib_segment, mean(ccf_pred_raw) as mean_pred from _sd group by calib_segment) a
  inner join derived.lra_dev b on a.calib_segment = b.calib_segment;

  create table _val as
  select s.*, s.ccf_pred_raw * coalesce(c.cf, 1) as ccf_pred
  from (select *, 'DEV' as smp length=3 from _sd
        union all corr
        select *, 'OOT' as smp length=3 from _so) s
  left join _cf_dev c on s.calib_segment = c.calib_segment;
quit;

/*---------------------------------------------------------------------------
  2. Accuracy and discrimination
---------------------------------------------------------------------------*/
proc sql;
  create table _acc as
  select 'fractional_logit' as model length=20, smp as sample, count(*) as n,
         mean(ccf_realised) as mean_realised, mean(ccf_pred) as mean_predicted,
         mean(abs(ccf_realised - ccf_pred)) as MAE,
         sqrt(mean((ccf_realised - ccf_pred)**2)) as RMSE,
         1 - sum((ccf_realised - ccf_pred)**2) / css(ccf_realised) as R2,
         sum(drawn_ref + ccf_pred * ccf_denominator) / sum(ead_default) as EAD_pred_over_actual
  from _val group by smp;
quit;

proc sort data=_val; by smp; run;
proc corr data=_val spearman noprint outs=_sp;
  by smp;
  var ccf_realised ccf_pred;
run;
data _sp;
  set _sp;
  where _type_ = 'CORR' and _name_ = 'ccf_realised';
  sample = smp; spearman = ccf_pred;
  keep sample spearman;
run;
proc sql;
  create table derived.performance as
  select a.*, b.spearman from _acc a inner join _sp b on a.sample = b.sample;
quit;

/*---------------------------------------------------------------------------
  3. One-sided t-test per segment (OOT, calibrated model + LRA for ROI/FD)
---------------------------------------------------------------------------*/
data _oot_all;
  set derived.rds;
  where sample = 'OOT';
run;
proc sql;
  create table _oot_est as
  select o.facility_id, o.calib_segment, o.ccf_realised,
         coalesce(v.ccf_pred, l.lra) as estimate
  from _oot_all o
  left join (select facility_id, ccf_pred from _val where smp = 'OOT') v
         on o.facility_id = v.facility_id
  left join derived.lra_dev l on o.calib_segment = l.calib_segment;
quit;

%macro ttest_by_segment(in=, out=);
  proc sql;
    create table &out as
    select calib_segment as segment, count(*) as n,
           mean(ccf_realised) as mean_realised, mean(estimate) as mean_estimate,
           mean(ccf_realised - estimate) / (std(ccf_realised - estimate) / sqrt(count(*))) as t_stat
    from &in group by calib_segment order by calib_segment;
  quit;
  data &out;
    set &out;
    p_value = 1 - probt(t_stat, n - 1);
    length result $16;
    if missing(p_value) then result = 'n/a';
    else if p_value < &ttest_alpha then result = 'UNDERESTIMATION';
    else result = 'ok';
  run;
%mend ttest_by_segment;

%ttest_by_segment(in=_oot_est, out=derived.ttest_oot_calibrated);

data _fin_est; set derived.final_rds; estimate = ccf_final; run;
%ttest_by_segment(in=_fin_est, out=derived.ttest_final);

/*---------------------------------------------------------------------------
  4. Decile calibration table (OOT)
---------------------------------------------------------------------------*/
proc rank data=_val(where=(smp='OOT')) out=_dec groups=10 ties=low;
  var ccf_pred;
  ranks bin;
run;
proc sql;
  create table derived.deciles_oot as
  select bin + 1 as bin, count(*) as n, mean(ccf_pred) as mean_predicted,
         mean(ccf_realised) as mean_realised
  from _dec group by bin order by bin;
quit;

/*---------------------------------------------------------------------------
  5. Population stability index (dev deciles applied to OOT)
---------------------------------------------------------------------------*/
%macro psi(var=);
  proc univariate data=derived.x_dev noprint;
    var &var;
    output out=_edges pctlpts=10 to 90 by 10 pctlpre=e_;
  run;
  data _null_;
    set _edges;
    array e e_:;
    length s $400;
    do i = 1 to dim(e); s = catx(' ', s, e[i]); end;
    call symputx('edges', s);
  run;
  data _bins;
    set derived.x_dev(in=d keep=&var) derived.x_oot(keep=&var);
    smp = ifc(d, 'DEV', 'OOT');
    bin = 0;
    do i = 1 to countw("&edges", ' ');
      if &var > input(scan("&edges", i, ' '), best32.) then bin = i;
    end;
  run;
  proc sql;
    create table _psi_&var as
    select "&var" as variable length=32,
           sum((a - e) * log(a / e)) as psi
    from (select bin,
                 max(sum((smp='DEV')) / (select count(*) from derived.x_dev), 1e-4) as e,
                 max(sum((smp='OOT')) / (select count(*) from derived.x_oot), 1e-4) as a
          from _bins group by bin);
  quit;
%mend psi;

%psi(var=x_utilisation) %psi(var=x_log_limit) %psi(var=x_grade)
%psi(var=x_arrears_6m)  %psi(var=x_log_mob)

data derived.stability;
  set _psi_:;
  length assessment $8;
  if psi < 0.10 then assessment = 'stable';
  else if psi < 0.25 then assessment = 'monitor';
  else assessment = 'shift';
run;
