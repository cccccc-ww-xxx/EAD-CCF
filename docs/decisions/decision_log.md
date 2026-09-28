# Decision log — EAD-CCF model

Every methodological choice that needs a **human decision** is recorded here
before estimation (CLAUDE.md section 4). Claude proposes options with pros,
cons and regulatory references; the model owner decides.

Status values: **PROPOSED** (default in `config/config.yaml`, not yet approved) ·
**APPROVED** · **REJECTED**. All entries are PROPOSED until signed off.

Regulatory shorthand: *CRR* = Reg. (EU) 575/2013 as amended by CRR3 (Reg. (EU)
2024/1623); *draft GL* = EBA/CP/2025/10 draft Guidelines on CCF estimation
(check whether the final Guidelines have been published and update references).

---

## D001 — Reference date approach and observation period
**Status: APPROVED (2026-09-28, Estelle)**

| Option | Pros | Cons |
|---|---|---|
| **Fixed horizon (default − 12 months)** | Simple, one observation per default, matches the 12-month horizon of PD | Ignores facilities defaulting < 12 months after origination; one point in time only |
| Cohort approach (fixed calendar reference dates) | Uses the portfolio as it was at fixed dates; favoured by Gürtler et al. (2018) in its generalised form | More complex data preparation; several observations per default must be weighted |
| Variable time horizon (several reference dates per default) | Uses more information | Correlated observations; weighting choices |

**Proposal:** fixed 12-month horizon for the prototype (`realised_ccf.horizon_months`), with the generalised cohort approach as a challenger once real data is available.
**References:** CRR Art. 182(1); draft GL section 5.4.
**Decision:** Fixed 12-month horizon (reference date = default date − 12 months). The generalised cohort approach remains a possible challenger once real data is available. No config change needed.

## D002 — Floor and cap on realised CCF
**Status: APPROVED (2026-09-28, Estelle)**

**Decision:**
- **Negative CCFs (repayments):** kept for STANDARD facilities (utilisation < 95%); floored at 0 for ROI and FULLY_DRAWN facilities.
- **CCFs above 100%:** no cap. Over-limit drawing is real exposure.
- Raw values are always kept (`ccf_raw`, `flag_negative_raw`).
- For the fractional-logit fit only, the target is restricted to [0, 100%]. Calibration to the long-run average uses the unrestricted values, so this does not change the final level.

**Why the hybrid:** keeping negatives everywhere was tested first. In the near-fully-drawn segments the stabilised denominator (D003) is small, so repayments dominate and the long-run average became negative (−0.16 to +0.01). An average CCF below zero implies an EAD below today's drawn amount, which is not defensible. Under the hybrid those segments have a long-run average of 0.29–0.40.

**Consequence for downturn (see D008):** the downturn adjustment was changed from a multiplicative factor (downturn ÷ LRA) to an additive add-on (downturn − LRA). The multiplicative form broke down when the LRA was near zero (a ×26 factor in one test).

**Supervisory note:** keeping negatives for standard facilities lowers their long-run average (by 0.08–0.13 for the 50–95% utilisation band). Expect validation and the ECB to ask for justification. Supporting analysis to prepare: share of negative CCFs, their causes (repayment vs. limit cuts), and sensitivity with a 0 floor.

**References:** CRR Art. 4(1)(56); draft GL section 5.5.

## D003 — Region of instability and fully drawn facilities
**Status: APPROVED (2026-09-28, Estelle)**

Near-fully-drawn facilities have a tiny undrawn amount, so the raw CCF explodes (example: limit 1,000, drawn 995, extra drawing 30 → CCF 600%). Fully drawn revolving facilities are in scope of IRB-CCF under the draft GL, but the raw CCF is undefined.

| Option | Pros | Cons |
|---|---|---|
| **Stabilised denominator: max(undrawn, 5% × limit) for utilisation ≥ 95%** | One consistent formula; bounded values; EAD = drawn + CCF × stabilised undrawn is applicable to fully drawn facilities | The 95% / 5% choice is a judgement; must be justified |
| Separate "limit-based" factor (extra drawing / limit) | Intuitive | Two parameters to maintain; not a CCF in the CRR sense |
| Exclude and apply fixed conservative CCF | Simple | Loses information; possibly excessive conservatism |

**Proposal:** stabilised denominator (`realised_ccf.roi_threshold = 0.95`); separate calibration segment for these facilities; sensitivity to the threshold to be shown at checkpoint B.
**References:** CRR Art. 4(1)(56); draft GL sections 4.1, 5.5.
**Decision:** Stabilised denominator max(undrawn, 5% × limit) for utilisation ≥ 95%, including fully drawn facilities; these form their own calibration segment. Threshold sensitivity (e.g. 90% and 98%) to be shown to validation at checkpoint B.

## D004 — Segmentation (benchmark and calibration segments)
**Status: APPROVED (2026-09-28, Estelle)**

**Decision:** 4 calibration segments, chosen on test evidence:

| Segment | Rule |
|---|---|
| RETAIL/U1_lt50 | retail products, utilisation < 50% |
| CORPORATE/U1_lt50 | corporate products, utilisation < 50% |
| ALL/U2_50_95 | all products, 50% ≤ utilisation < 95% |
| ALL/U3_ge95 | all products, utilisation ≥ 95% incl. fully drawn (stabilised CCF, D003) |

Product remains a risk driver inside the fractional logit; the segments only set the calibration level.

**Evidence (synthetic data, see model documentation section 6.0):**
- **< 50% vs 50–95%:** significant for every product (p < 0.0001); ordering held in 15 of 15 years.
- **Within < 50%:** retail vs corporate differ (p < 0.001); overdraft vs card (p = 0.61) and SME vs corporate RCF (p = 0.35) do not.
- **Within 50–95% and ≥ 95%:** no product pair differs significantly (all p > 0.06), so these bands are pooled.
- **≥ 95% band:** kept separate for methodological reasons (different CCF formula).
- **Size:** the smallest chosen segment has 1,365 defaults, and at least 56 in every year.

**Alternatives considered:** 12 segments (product × band), rejected because most splits are not statistically supported; 6 segments (retail/corporate × band), rejected because retail vs corporate is not different above 50% utilisation.

**On real data:** rerun the same tests (`python/ead_ccf/segment_tests.py`, `sas/03b_segment_tests.sas`); band edges and splits may change.
**References:** draft GL chapter 6.

## D005 — Long-run average weighting
**Status: APPROVED (2026-09-28, Estelle)**

| Option | Source | Effect |
|---|---|---|
| **Facility-weighted average of all realised CCFs** | draft GL section 7.1 | Years with many defaults (typically downturns) weigh more |
| Arithmetic average of yearly averages | Former ECB Guide to internal models (CCF chapter withdrawn in release 4.1, June 2026) | Each year weighs the same |

Industry responses to the consultation flagged this inconsistency. Both are computed in section 6.1 of the model documentation; the `difference` column shows the impact.
**Decision:** facility-weighted, following the draft GL. On the synthetic data it is 0.9–2.1 percentage points higher than the average of yearly averages in every segment, i.e. also the more conservative choice. Revisit when the final GL is published; the yearly average stays in the documentation as a sensitivity.

## D006 — Eligible risk drivers
**Status: APPROVED (2026-09-28, Estelle)**

Only information known **at the reference date** may be used. `limit_cut_flag` (bank cut the limit between reference date and default) is a strong driver in the data but would leak future information, so it is excluded. It remains useful to explain back-testing results and to monitor limit-management policy (CRR Art. 182(1)(h)).
**Decision:** exclude `limit_cut_flag` and any other variable observed after the reference date. General rule for all future candidate drivers: a variable is eligible only if its value is known at the reference date.

## D007 — Estimation sample for final quantification
**Status: APPROVED (2026-09-28, Estelle)**

Models are developed on the development sample and tested out-of-time (default years ≥ 2022). After successful OOT testing, the final long-run average, calibration, downturn and MoC use the **full** observation period, as the draft GL requires all relevant data to be used for the long-run average.
**Decision:** develop on 2010–2021, test out-of-time on 2022–2024, then re-estimate all final parameters on 2010–2024.

## D008 — Downturn period identification
**Status: APPROVED (2026-09-28, Estelle)**

Downturn years = union of (i) the two years with the highest average realised CCF and (ii) macro-economic candidate years (2012–2013 euro-area crisis, 2020 COVID-19). Downturn CCF = max(LRA, average realised CCF in downturn years) per segment, applied as an additive add-on (downturn CCF − LRA) on top of the calibrated CCF; segments with fewer than 30 downturn observations use the portfolio-level ratio. To be aligned with the bank's downturn framework for LGD.
**References:** draft GL chapter 10.
**Decision:** downturn years = union of data-driven (2 highest-CCF years) and macro-economic candidates; on the synthetic data 2012, 2013 and 2020. Downturn applied as an additive add-on (see D002). On real data, the macro candidates must be justified with economic indicators and aligned with the LGD downturn periods.

## D009 — Margin of conservatism
**Status: INTERIM — proxies kept until the bank framework is applied**

Prototype proxies: A = impact of missing ratings, B = impact of the cap choice (D002), C = bootstrap estimation error (90% quantile). Must be replaced by the bank's approved MoC framework (EBA/GL/2017/16 section 4.4; draft GL chapter 9).
**Decision (2026-09-28, Estelle):** keep the proxies for the prototype, clearly labelled. The bank's MoC framework will be provided and implemented next; this entry will then be updated.

## D010 — Facility-level realised CCF vs borrower-level aggregation
**Status: OPEN ISSUE — under investigation**

Current practice combines restructured facilities at borrower level. CRR Art. 4(1)(56) and the draft GL require a realised CCF per facility, with exceptions only for related contracts under an overarching agreement with comparable characteristics. The current practice must be assessed against this requirement before real-data development starts.
**Decision (2026-09-28, Estelle):** investigate first. Next step: establish from the current EAD-CCF documentation and colleagues how restructured facilities are linked today, then assess against Art. 4(1)(56) and the related-contract exception. The prototype computes one realised CCF per facility in the meantime.
