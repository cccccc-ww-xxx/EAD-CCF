# CLAUDE.md — EAD-CCF Model Development Project

> This file is read automatically by Claude Code at the start of every session.
> It tells Claude what the project is, which rules apply, and where the human
> checkpoints are. Adapt every section to your bank's internal policies before use.

## 1. Project context
- Goal: (re)build the EAD / CCF model for the in-scope BNP Paribas Fortis portfolio(s).
- Primary language: **Python** (development, analysis, documentation).
  SAS equivalents are kept for every step (./sas/) and must stay in sync.
- Data: **SYNTHETIC ONLY** (python/ead_ccf/synthetic_data.py). No client data in this repo, ever.
- Model owner / accountable person: <NAME>. Claude drafts; humans decide and sign off.
- Portfolio scope: <segments, e.g. retail revolving / corporate revolving — to be confirmed>.

## 2. Regulatory reference library (in ./regulation/)
Always cite the specific article/paragraph when a methodological choice depends on it.
If a document is not in ./regulation/, say so instead of quoting from memory.
- CRR (Reg. 575/2013) as amended by CRR3 (Reg. 2024/1623) — esp. Art. 166 (EAD / CCF
  scope and floors), Art. 179 (general estimation requirements), Art. 182 (own CCF estimates)
- EBA Guidelines on PD/LGD estimation (EBA/GL/2017/16) — general estimation parts, MoC framework
- EBA RTS on IRB assessment methodology (Commission Delegated Reg. 2022/439)
- EBA draft Guidelines on CCF estimation under Art. 182(5) CRR (EBA/CP/2025/10, July 2025).
  Treat as the de-facto blueprint (structure: data, realised CCF, risk differentiation,
  long-run average, in-default CCF, MoC, downturn). ALWAYS check whether the FINAL version
  has been published and use it instead; flag every place where final text differs.
- ECB Guide to internal models: release 4.1 (June 2026) WITHDREW its CCF guidance pending
  the EBA Guidelines. Do not cite old EGIM CCF paragraphs as current requirements; mention
  them only as historical supervisory expectations, clearly labelled.
- Internal: model risk policy, model documentation standard, default definition, data dictionary

## 3. Data rules (NON-NEGOTIABLE)
- Only work on data in ./data/ that is approved for this environment.
- Never copy, print or summarise identifiable client data into documentation or chat.
  Use aggregated statistics only (counts, means, percentiles by segment).
- Never modify raw input files. All transformations go to ./data/derived/ via code.

## 4. Modelling conventions
- Realised CCF definition, reference-date approach (fixed-horizon vs cohort vs variable
  time horizon), treatment of CCF < 0 and > 1, and the default definition must be
  written down in ./docs/decisions/ BEFORE estimation. Claude proposes options with
  pros/cons + regulatory references; the human chooses.
- Every number in the documentation must be produced by code in this repo (no manual edits).
- SAS and Python implementations must be independent and reconciled: key outputs
  (population counts, realised CCF by segment, calibrated CCF) must match within a
  stated tolerance. Log the reconciliation in ./docs/reconciliation/.
- Set seeds for anything random. Record software versions.

## 5. Folder structure
- ./config/config.yaml  single source of truth for all parameters ([DECISION] = needs sign-off)
- ./python/ead_ccf/     Python package, one module per step; ./python/run_pipeline.py runs all
- ./python/reconcile.py compares Python vs SAS outputs
- ./sas/                SAS equivalents, numbered by step; sas/run_all.sas runs all
- ./tests/              unit tests with hand-calculated examples (python -m unittest discover -s tests)
- ./data/raw, ./data/derived   generated synthetic data (not committed; regenerate with the pipeline)
- ./outputs/            tables (outputs/python, outputs/sas) and figures referenced by the documentation
- ./docs/               model_documentation.md (generated), decisions/, reconciliation/
- ./regulation/, ./literature/  source texts (add PDFs; not committed if licensing forbids)

## 5b. How to work in this repo
- Change a parameter -> edit config/config.yaml AND sas/00_config.sas, log it in docs/decisions/.
- Change a calculation -> change the Python module AND the matching SAS program, add/adjust a
  unit test, rerun `python python/run_pipeline.py`, then reconcile.
- Never edit docs/model_documentation.md by hand: edit python/ead_ccf/report.py and rerun.
- Before committing: tests pass, pipeline runs end to end, no client data in any file.

## 6. Workflow and human checkpoints
Stop and ask for explicit approval at each checkpoint. Do not proceed past one on your own.
1. Data scope, default definition, observation period            -> CHECKPOINT A
2. Realised CCF computation and data-quality results              -> CHECKPOINT B
3. Segmentation / risk drivers                                    -> CHECKPOINT C
4. Calibration (long-run average), downturn, floors, MoC          -> CHECKPOINT D
5. Performance testing (discrimination, calibration, stability)   -> CHECKPOINT E
6. Documentation complete, SAS/Python reconciled                  -> CHECKPOINT F

## 7. Documentation standard (for internal validation and ECB)
Each chapter must contain: purpose, data used, method, regulatory reference,
results (table/chart from ./outputs/), limitations, and the code file that produced it.
Keep an "Open issues & deficiencies" list — never hide a weakness to make results look better.

## 8. Behaviour
- If a requirement is unclear or two regulations seem to conflict, flag it; don't guess.
- Explain SAS/Python code in plain language (the model developer is still learning to code).
- Prefer simple, auditable methods over complex ones unless there is a documented reason.

## 9. Literature and candidate methods (in ./literature/)
Keep the PDFs in ./literature/. Cite author + year + journal in the documentation.
Never invent a reference: if a paper isn't in the folder, say so.

Core references:
- Taplin, To & Hee (2007), J. of Credit Risk — argues the CCF ratio is unstable; model EAD directly.
- Tong, Mues, Brown & Thomas (2016), European J. of Operational Research — "EAD models with and
  without the CCF": zero-adjusted gamma mixture for EAD; credit usage as segmentation criterion
  to combine direct-EAD and CCF models.
- Gürtler, Hibbeln & Usselmann (2018), J. of Banking & Finance — systematic review + empirical
  comparison of estimation approaches (cohort vs fixed-horizon etc.); favours the generalised
  cohort approach and the CCF parameter for unbiased EAD.
- Wattanawongwan, Mues, Okhrati, Choudhry & So (2023), Int. J. of Forecasting — GAMLSS mixture
  model for credit-card EAD, conditioning on whether the limit was hit before default.

Method ladder (propose in this order; each rung must beat the previous one out-of-time
AND stay explainable, or we stop):
1. BENCHMARK (always built): pooled long-run average realised CCF by simple segments
   (e.g. product x utilisation band). This is also the regulatory calibration anchor.
2. Parametric risk differentiation: OLS on truncated CCF, fractional logit, beta /
   zero-one-inflated beta regression, or a mixture (P(CCF=0), P(CCF=1), level in between).
3. Direct-EAD / utilisation-change alternatives (Taplin 2007; Tong 2016) as challengers,
   especially for near-fully-drawn facilities.
4. ML challengers (e.g. gradient boosting with monotonic constraints) ONLY as challenger /
   driver-discovery tools in Python, with SHAP-type explanations; not as the production
   model unless the model owner and validation explicitly agree.
Whatever wins, the final estimate is still calibrated to the long-run average, then
downturn and MoC are applied per the EBA framework.

Known technical pitfalls to handle explicitly (from EBA draft GL and literature):
- Realised CCF per facility per default (Art. 4(1)(56) CRR3); exceptions (e.g. umbrella
  facilities / related contracts) must be justified. NOTE: current Fortis practice of
  aggregating restructured facilities at borrower level must be checked against this.
- "Region of instability": near-fully-drawn facilities give exploding CCFs (tiny denominator).
- Fully drawn revolving facilities are in scope under the draft GL.
- Long-run average weighting: draft GL (facility-weighted average) vs older EGIM (average of
  yearly averages) — document which one and why.
- Bimodal CCF distribution (mass at 0 and 1): don't assume normal errors.
