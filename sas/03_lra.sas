/*=============================================================================
  03_lra.sas  -  Long-run average realised CCF by calibration segment
  -----------------------------------------------------------------------------
  SAS equivalent of python/ead_ccf/lra.py

  facility_weighted : mean of all realised CCFs (EBA draft GL EBA/CP/2025/10, 7.1)
  yearly_average    : mean of the yearly means   (historical ECB guide expectation)
=============================================================================*/

%macro lra_by_segment(in=, out=);
  proc sql;
    create table _yearly as
    select calib_segment, default_year, mean(ccf_realised) as ccf_year
    from &in group by calib_segment, default_year;

    create table &out as
    select a.calib_segment,
           a.n_facilities,
           a.lra_facility_weighted,
           b.n_years,
           b.lra_yearly_average,
           a.lra_facility_weighted - b.lra_yearly_average as difference
    from (select calib_segment, count(*) as n_facilities,
                 mean(ccf_realised) as lra_facility_weighted
          from &in group by calib_segment) a
    inner join
         (select calib_segment, count(distinct default_year) as n_years,
                 mean(ccf_year) as lra_yearly_average
          from _yearly group by calib_segment) b
    on a.calib_segment = b.calib_segment
    order by calib_segment;
  quit;

  /* selected LRA according to the configured method */
  data &out;
    set &out;
    %if &lra_method = facility_weighted %then %do; lra = lra_facility_weighted; %end;
    %else %do; lra = lra_yearly_average; %end;
  run;
%mend lra_by_segment;

/* full observation period (final quantification) */
%lra_by_segment(in=derived.rds, out=derived.recon_lra_by_segment);

/* development sample only (used to calibrate models before OOT testing) */
data _dev; set derived.rds; where sample = 'DEV'; run;
%lra_by_segment(in=_dev, out=derived.lra_dev);

/* yearly series (portfolio) for the downturn analysis and chart */
proc sql;
  create table derived.yearly as
  select default_year, count(*) as n_facilities, mean(ccf_realised) as mean_ccf
  from derived.rds group by default_year order by default_year;
quit;
