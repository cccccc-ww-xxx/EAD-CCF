/*=============================================================================
  01_import.sas  -  Read the synthetic data produced by the Python generator
  -----------------------------------------------------------------------------
  The synthetic data is generated ONCE in Python (python/ead_ccf/synthetic_data.py)
  and read here, so that SAS and Python start from exactly the same records.
  An explicit DATA step (instead of PROC IMPORT) fixes types and lengths, which
  makes the program deterministic and auditable.
=============================================================================*/

data raw.defaults;
  infile "&root/data/raw/defaults.csv" dsd firstobs=2 truncover;
  length facility_id $12 obligor_id $12 product $10 segment $10;
  input facility_id $ obligor_id $ product $ segment $
        reference_date :yymmdd10. default_date :yymmdd10. default_year
        limit_ref drawn_ref grade_ref months_on_book arrears_flag_6m
        limit_cut_flag limit_default ead_default;
  format reference_date default_date yymmdd10.;
run;

data raw.performing;
  infile "&root/data/raw/performing.csv" dsd firstobs=2 truncover;
  length facility_id $12 product $10 segment $10;
  input facility_id $ product $ segment $ application_date :yymmdd10.
        limit_ref drawn_ref grade_ref months_on_book arrears_flag_6m limit_cut_flag;
  format application_date yymmdd10.;
run;

title "Record counts after import";
proc sql;
  select 'defaults'   as dataset, count(*) as n from raw.defaults
  union all
  select 'performing' as dataset, count(*) as n from raw.performing;
quit;
title;
