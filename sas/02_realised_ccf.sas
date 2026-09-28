/*=============================================================================
  02_realised_ccf.sas  -  Realised CCF, data quality checks, population summary
  -----------------------------------------------------------------------------
  SAS equivalent of python/ead_ccf/realised_ccf.py + segmentation.py

  realised CCF = (drawn at default - drawn at reference)
                 / (limit at reference - drawn at reference)      CRR3 Art. 4(1)(56)

  ROI / FULLY_DRAWN facilities: denominator stabilised to
  max(undrawn, (1 - roi_threshold) x limit)                       decision D003
=============================================================================*/

/*---------------------------------------------------------------------------
  1. Data quality checks (same list as Python DQ01-DQ10)
---------------------------------------------------------------------------*/
proc sql noprint;
  select count(*) into :n_total trimmed from raw.defaults;
quit;

proc sql;
  create table derived.dq as
  select 'DQ01 missing facility_id' as check length=40,
         sum(missing(facility_id)) as n_fail from raw.defaults
  union all
  select 'DQ02 duplicate facility_id', coalesce(sum(cnt), 0) from
        (select count(*) as cnt from raw.defaults group by facility_id having count(*) > 1)
  union all
  select 'DQ03 limit_ref <= 0',             sum(limit_ref <= 0)            from raw.defaults
  union all
  select 'DQ04 drawn_ref < 0',              sum(drawn_ref < 0)             from raw.defaults
  union all
  select 'DQ05 drawn_ref > limit_ref',      sum(drawn_ref > limit_ref + 0.01) from raw.defaults
  union all
  select 'DQ06 ead_default < 0',            sum(ead_default < 0)           from raw.defaults
  union all
  select 'DQ07 reference_date >= default_date', sum(reference_date >= default_date) from raw.defaults
  union all
  select 'DQ08 missing grade_ref',          sum(missing(grade_ref))        from raw.defaults
  union all
  select 'DQ09 grade_ref outside 1-12',
         sum(not missing(grade_ref) and (grade_ref < 1 or grade_ref > 12)) from raw.defaults
  union all
  select 'DQ10 missing ead_default',        sum(missing(ead_default))      from raw.defaults;
quit;

data derived.dq;
  set derived.dq;
  pct_fail = round(100 * n_fail / &n_total, 0.001);
run;

/*---------------------------------------------------------------------------
  2. Realised CCF per facility (the reference data set, "RDS")
---------------------------------------------------------------------------*/
/*---------------------------------------------------------------------------
  Scope (D011): large corporates (turnover > EUR 500m) are F-IRB -> no own CCF.
  They are excluded from the reference data set used for estimation.
---------------------------------------------------------------------------*/
data derived.rds_all;
  set raw.defaults;
  length scope_reason $60;
  airb_ccf_scope = not (segment = 'corporate' and annual_turnover_meur > &large_corp_turnover);
  if airb_ccf_scope then scope_reason = 'in scope: revolving, A-IRB eligible';
  else scope_reason = 'large corporate (turnover > EUR 500m): F-IRB, SA CCF';
run;

proc sql;
  create table derived.scope as
  select product, scope_reason, count(*) as n_facilities, sum(limit_ref) as sum_limit
  from derived.rds_all group by product, scope_reason;
quit;

data derived.rds;
  set derived.rds_all;
  where airb_ccf_scope = 1;
  length facility_type $12 util_band $10 calib_segment $24 sample $3;

  undrawn_ref     = max(limit_ref - drawn_ref, 0);
  utilisation_ref = drawn_ref / limit_ref;
  extra_drawing   = ead_default - drawn_ref;

  /* facility type at reference date */
  if undrawn_ref <= 0                      then facility_type = 'FULLY_DRAWN';
  else if utilisation_ref >= &roi_threshold then facility_type = 'ROI';
  else                                          facility_type = 'STANDARD';

  /* raw CCF - undefined for fully drawn facilities */
  if undrawn_ref > 0 then ccf_raw = extra_drawing / undrawn_ref;
  else ccf_raw = .;

  /* stabilised denominator for ROI / FULLY_DRAWN */
  if facility_type = 'STANDARD' then ccf_denominator = undrawn_ref;
  else ccf_denominator = max(undrawn_ref, (1 - &roi_threshold) * limit_ref);

  ccf_realised = extra_drawing / ccf_denominator;
  /* D002: floor depends on facility type */
  if facility_type = 'STANDARD' then do;
    if not missing(&floor_standard) then ccf_realised = max(ccf_realised, &floor_standard);
  end;
  else do;
    if not missing(&floor_near_full) then ccf_realised = max(ccf_realised, &floor_near_full);
  end;
  if not missing(&ccf_cap)   then ccf_realised = min(ccf_realised, &ccf_cap);

  /* target for the fractional logit only: capped to [0, model_cap] */
  ccf_model_target = min(max(ccf_realised, 0), &model_cap);

  flag_negative_raw = (extra_drawing < 0);
  flag_above_one    = (ccf_realised > 1);

  /* segmentation: product x utilisation band (decision D004) */
  util_c = min(max(utilisation_ref, 0), 1);
  if util_c < &band1_upper      then util_band = 'U1_lt50';
  else if util_c < &band2_upper then util_band = 'U2_50_95';
  else                               util_band = 'U3_ge95';
  %assign_calib_segment;   /* D004 - macro defined in 00_config.sas */

  sample = ifc(default_year >= &oot_first_year, 'OOT', 'DEV');
  drop util_c;
run;

/*---------------------------------------------------------------------------
  3. Population summary (reconciled against Python recon_population.csv)
---------------------------------------------------------------------------*/
proc sql;
  create table derived.recon_population as
  select product, facility_type,
         count(*)          as n_facilities,
         sum(limit_ref)    as sum_limit_ref,
         sum(drawn_ref)    as sum_drawn_ref,
         sum(ead_default)  as sum_ead_default,
         mean(ccf_realised) as mean_ccf_realised
  from derived.rds
  group by product, facility_type
  order by product, facility_type;
quit;

/*---------------------------------------------------------------------------
  4. Distribution of realised CCF (PCTLDEF=5 = Python "averaged_inverted_cdf")
---------------------------------------------------------------------------*/
proc sort data=derived.rds out=_rds_sorted; by product facility_type; run;

proc means data=_rds_sorted noprint pctldef=5;
  by product facility_type;
  var ccf_realised;
  output out=_dist(drop=_type_ _freq_) n=n mean=mean p25=p25 median=median p75=p75;
run;

proc sql;
  create table derived.recon_ccf_distribution as
  select a.*, b.share_zero, b.share_ge_one, b.share_negative_raw
  from _dist a inner join
       (select product, facility_type,
               mean(ccf_realised = 0)  as share_zero,
               mean(ccf_realised >= 1) as share_ge_one,
               mean(flag_negative_raw) as share_negative_raw
        from derived.rds group by product, facility_type) b
  on a.product = b.product and a.facility_type = b.facility_type
  order by product, facility_type;
quit;
