/*=============================================================================
  07_export_recon.sas  -  Export SAS results for the Python/SAS reconciliation
  -----------------------------------------------------------------------------
  Writes outputs/sas/recon_*.csv with the SAME column names as the Python
  files in outputs/python/. Then run:   python python/reconcile.py
=============================================================================*/

%macro export(ds=, file=);
  proc export data=&ds outfile="&out_sas/&file..csv" dbms=csv replace;
  run;
%mend export;

%export(ds=derived.recon_population,       file=recon_population);
%export(ds=derived.recon_ccf_distribution, file=recon_ccf_distribution);
%export(ds=derived.recon_lra_by_segment(drop=lra), file=recon_lra_by_segment);
%export(ds=derived.recon_fractional_logit, file=recon_fractional_logit);

/* not strictly reconciled (bootstrap / RNG), exported for comparison */
%export(ds=derived.scope,          file=scope);
%export(ds=derived.dq,             file=dq);
%export(ds=derived.downturn,       file=downturn);
%export(ds=derived.moc,            file=moc);
%export(ds=derived.final_segment,  file=final_segment);
%export(ds=derived.performance,    file=performance);
%export(ds=derived.application,    file=application);
