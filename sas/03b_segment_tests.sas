/*=============================================================================
  03b_segment_tests.sas  -  Segmentation tests (checkpoint C, decision D004)
  -----------------------------------------------------------------------------
  SAS equivalent of python/ead_ccf/segment_tests.py

  Welch two-sample t-test (unequal variances, Satterthwaite degrees of freedom)
  between segments, ordering stability of utilisation bands by year, and
  segment sizes. Same statistic as scipy.stats.ttest_ind(equal_var=False).
=============================================================================*/

/*---------------------------------------------------------------------------
  Welch t-test between two groups of derived.rds, appended to &out
---------------------------------------------------------------------------*/
%macro welch(out=, label=, cond_a=, cond_b=, name_a=, name_b=);
  proc sql noprint;
    create table _w as
    select "&label" as comparison length=24,
           "&name_a" as segment_a length=24, "&name_b" as segment_b length=24,
           a.n as n_a, b.n as n_b, a.m as mean_a, b.m as mean_b,
           (a.m - b.m) / sqrt(a.v / a.n + b.v / b.n) as t_stat,
           (a.v / a.n + b.v / b.n)**2
             / ((a.v / a.n)**2 / (a.n - 1) + (b.v / b.n)**2 / (b.n - 1)) as df_welch
    from (select count(*) as n, mean(ccf_realised) as m, var(ccf_realised) as v
          from derived.rds where &cond_a) a,
         (select count(*) as n, mean(ccf_realised) as m, var(ccf_realised) as v
          from derived.rds where &cond_b) b;
  quit;
  data _w;
    set _w;
    p_value = 2 * (1 - probt(abs(t_stat), df_welch));
    length result $14;
    result = ifc(p_value < 0.05, 'different', 'NOT different');
  run;
  proc append base=&out data=_w force; run;
%mend welch;

/*---------------------------------------------------------------------------
  1. Chosen calibration segments - all pairs
---------------------------------------------------------------------------*/
proc datasets lib=derived nolist; delete seg_chosen seg_hetero; quit;

proc sql noprint;
  select distinct calib_segment into :seg1-  from derived.rds order by calib_segment;
  %let n_seg = &sqlobs;
quit;

%macro chosen_pairs;
  %do i = 1 %to &n_seg;
    %do j = %eval(&i + 1) %to &n_seg;
      %welch(out=derived.seg_chosen, label=chosen segments,
             cond_a=%str(calib_segment = "&&seg&i"), cond_b=%str(calib_segment = "&&seg&j"),
             name_a=&&seg&i, name_b=&&seg&j);
    %end;
  %end;
%mend chosen_pairs;
%chosen_pairs;

/*---------------------------------------------------------------------------
  2. Candidate splits: neighbouring bands within product, products within band
---------------------------------------------------------------------------*/
%macro candidate_splits;
  %let products = CORP_RCF RET_CARD RET_OVD SME_CRL;
  %let bands    = U1_lt50 U2_50_95 U3_ge95;
  %do p = 1 %to 4;
    %let pr = %scan(&products, &p);
    %do b = 1 %to 2;
      %let b1 = %scan(&bands, &b);
      %let b2 = %scan(&bands, %eval(&b + 1));
      %welch(out=derived.seg_hetero, label=band within product,
             cond_a=%str(product = "&pr" and util_band = "&b1"),
             cond_b=%str(product = "&pr" and util_band = "&b2"),
             name_a=&pr/&b1, name_b=&pr/&b2);
    %end;
  %end;
  %do b = 1 %to 3;
    %let bd = %scan(&bands, &b);
    %do p = 1 %to 3;
      %do q = %eval(&p + 1) %to 4;
        %let p1 = %scan(&products, &p);
        %let p2 = %scan(&products, &q);
        %welch(out=derived.seg_hetero, label=product within band,
               cond_a=%str(product = "&p1" and util_band = "&bd"),
               cond_b=%str(product = "&p2" and util_band = "&bd"),
               name_a=&p1/&bd, name_b=&p2/&bd);
      %end;
    %end;
  %end;
%mend candidate_splits;
%candidate_splits;

/*---------------------------------------------------------------------------
  3. Ordering stability: share of years in which band k > band k+1, per product
---------------------------------------------------------------------------*/
proc sql;
  create table _yb as
  select product, default_year,
         mean(case when util_band = 'U1_lt50'  then ccf_realised end) as u1,
         mean(case when util_band = 'U2_50_95' then ccf_realised end) as u2,
         mean(case when util_band = 'U3_ge95'  then ccf_realised end) as u3
  from derived.rds group by product, default_year;

  create table derived.seg_order as
  select product, 'U1_lt50' as higher, 'U2_50_95' as lower, count(*) as n_years,
         mean(u1 > u2) as share_years_order_holds
  from _yb where u1 is not missing and u2 is not missing group by product
  union all
  select product, 'U2_50_95', 'U3_ge95', count(*), mean(u2 > u3)
  from _yb where u2 is not missing and u3 is not missing group by product;
quit;

/*---------------------------------------------------------------------------
  4. Segment sizes
---------------------------------------------------------------------------*/
proc sql;
  create table derived.seg_counts as
  select calib_segment, sum(n) as n_defaults, min(n) as min_per_year, mean(n) as mean_per_year
  from (select calib_segment, default_year, count(*) as n
        from derived.rds group by calib_segment, default_year)
  group by calib_segment order by calib_segment;
quit;
