/*=============================================================================
  run_all.sas  -  Run the complete SAS pipeline
  -----------------------------------------------------------------------------
  Prerequisites:
    1. Run the Python pipeline once (python python/run_pipeline.py) - it creates
       the synthetic data in data/raw/ and the Python reconciliation files.
    2. Edit &root in sas/00_config.sas.
    3. Create the folder outputs/sas/ if it does not exist.
  Then submit this program.
=============================================================================*/

%let sasdir = C:/path/to/ead-ccf-model/sas;   /* <-- EDIT THIS */

%include "&sasdir/00_config.sas";
%include "&sasdir/01_import.sas";
%include "&sasdir/02_realised_ccf.sas";
%include "&sasdir/03_lra.sas";
%include "&sasdir/03b_segment_tests.sas";
%include "&sasdir/04_fractional_logit.sas";
%include "&sasdir/05_quantification.sas";
%include "&sasdir/06_validation.sas";
%include "&sasdir/07_export_recon.sas";
