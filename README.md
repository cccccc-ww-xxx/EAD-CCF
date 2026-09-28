# EAD-CCF model — Python prototype with SAS equivalents

A complete, reproducible prototype of an A-IRB **credit conversion factor (CCF)** model
for undrawn revolving commitments, built on **synthetic data only**. It shows the full
development chain an internal validation team or the ECB expects to see: data quality,
realised CCF, risk differentiation, calibration, downturn, margin of conservatism,
input floor, performance testing, documentation and a Python/SAS reconciliation.

> **Not an approved model.** All numbers come from synthetic data. Every methodological
> choice is a *proposal* in [`docs/decisions/decision_log.md`](docs/decisions/decision_log.md)
> waiting for a human decision.

## Quick start (Python)

```bash
pip install -r requirements.txt
python python/run_pipeline.py          # generate data, estimate, test, write the documentation
python -m unittest discover -s tests   # unit tests with hand-calculated examples
```

Then open [`docs/model_documentation.md`](docs/model_documentation.md).

## SAS

The SAS programs in [`sas/`](sas/) repeat every step. They read the synthetic data that
the Python pipeline writes to `data/raw/`, so both start from the same records.

1. Run the Python pipeline once (creates `data/raw/*.csv`).
2. Edit the root path in `sas/00_config.sas` and `sas/run_all.sas`.
3. Submit `sas/run_all.sas` — results go to `outputs/sas/`.
4. Run `python python/reconcile.py` → `docs/reconciliation/reconciliation_report.md`.

The SAS code has **not yet been run** in a SAS session; expect small fixes on first run.

## What the pipeline does

| Step | Python | SAS | Regulatory anchor |
|---|---|---|---|
| Synthetic data | `ead_ccf/synthetic_data.py` | reads CSV (`01_import.sas`) | — |
| Data quality, realised CCF | `ead_ccf/realised_ccf.py` | `02_realised_ccf.sas` | CRR3 Art. 4(1)(56); draft GL 5.5 |
| Segmentation, long-run average | `ead_ccf/segmentation.py`, `lra.py` | `03_lra.sas` | draft GL 7.1 |
| Benchmark, fractional logit, GBM challenger | `ead_ccf/models.py` | `04_fractional_logit.sas` (GBM: Python only) | draft GL ch. 6 |
| Calibration, downturn, MoC, input floor | `ead_ccf/quantification.py` | `05_quantification.sas` | draft GL ch. 7, 9, 10; CRR3 Art. 166 |
| Performance tests | `ead_ccf/validation.py` | `06_validation.sas` | draft GL 6.1 |
| Documentation | `ead_ccf/report.py` | — | — |
| Reconciliation | `reconcile.py` | `07_export_recon.sas` | — |

"draft GL" = EBA/CP/2025/10, draft Guidelines on CCF estimation (July 2025). Check whether
the final Guidelines have been published and update the references.

## Method ladder

1. **Benchmark** – segment long-run average (product × utilisation band).
2. **Fractional logit** (Papke & Wooldridge, 1996) – replaces the benchmark only if it
   improves out-of-time MAE *and* rank correlation.
3. **Direct-EAD challengers** (Taplin et al., 2007; Tong et al., 2016) – open issue.
4. **Gradient boosting with monotonic constraints** – challenger for driver discovery only.

## Repository layout

```
config/config.yaml        all parameters ([DECISION] = needs sign-off)
python/ead_ccf/           one module per step
python/run_pipeline.py    runs everything
python/reconcile.py       Python vs SAS comparison
sas/                      SAS equivalents (run_all.sas)
tests/                    unit tests
docs/                     model documentation, decision log, data dictionary, reconciliation
outputs/                  tables and figures used in the documentation
CLAUDE.md                 instructions for Claude when working in this repo
```

## Working with Claude on this repo

`CLAUDE.md` tells Claude the rules: synthetic data only, cite the regulation, change
Python and SAS together, never hand-edit the generated documentation, and stop at the
six human checkpoints.
