/*=============================================================================
  00_config.sas  -  Configuration (mirror of config/config.yaml)
  -----------------------------------------------------------------------------
  SAS equivalent of python/ead_ccf/config.py.
  Keep every value IDENTICAL to config/config.yaml, otherwise the Python/SAS
  reconciliation (python/reconcile.py) will fail - which is the point.

  HOW TO RUN: set &root below to the folder where you cloned the repository,
  then submit sas/run_all.sas.
=============================================================================*/

%let root = C:/path/to/ead-ccf-model;          /* <-- EDIT THIS */

libname raw     "&root/data/raw";
libname derived "&root/data/derived";
%let out_sas = &root/outputs/sas;

options mprint nosymbolgen fullstimer;

/* --- general -------------------------------------------------------------- */
%let seed            = 20260928;

/* --- realised CCF ----------------------------------------------------------- */
%let roi_threshold   = 0.95;   /* utilisation >= this -> region of instability   */
/* D002 approved (hybrid): negatives kept for STANDARD, floored at 0 for ROI / FULLY_DRAWN */
%let floor_standard  = .;      /* '.' = no floor                                  */
%let floor_near_full = 0;
%let ccf_cap         = .;      /* cap on realised CCF   ('.' = no cap)           */
%let model_cap       = 1;      /* cap used only for the fractional-logit target  */

/* --- segmentation: utilisation band edges ---------------------------------- */
%let band1_upper     = 0.50;   /* U1_lt50  : util <  0.50                         */
%let band2_upper     = 0.95;   /* U2_50_95 : 0.50 <= util < 0.95 ; U3_ge95 : rest */

/* --- LRA method: facility_weighted | yearly_average ------------------------- */
%let lra_method      = facility_weighted;

/* --- development / out-of-time split --------------------------------------- */
%let oot_first_year  = 2022;

/* --- downturn -------------------------------------------------------------- */
%let n_worst_years   = 2;
%let macro_dt_years  = 2012 2013 2020;
%let min_dt_obs      = 30;

/* --- margin of conservatism ------------------------------------------------ */
%let boot_samples    = 1000;
%let moc_confidence  = 0.90;

/* --- validation ------------------------------------------------------------ */
%let ttest_alpha     = 0.05;

/* --- standardised CCF per product (input floor = 50% x SA CCF) ------------- */
/* [DECISION] verify buckets against CRR3 Art. 111                            */
proc format;
  value $sa_ccf
    'RET_OVD'  = '0.10'
    'RET_CARD' = '0.10'
    'SME_CRL'  = '0.40'
    'CORP_RCF' = '0.40';
run;
