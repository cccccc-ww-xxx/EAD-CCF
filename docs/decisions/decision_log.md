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
**Status: PROPOSED**

- Negative realised CCFs (repayments between reference date and default) are floored at 0 for estimation. Raw values are kept (`ccf_raw`, `flag_negative_raw`).
- No cap: CCFs above 100% (over-limit drawing) are kept, because capping would underestimate EAD.
- For the fractional-logit fit only, the target is capped at 100% (the method needs a target in [0, 1]); calibration to the long-run average uses the **uncapped** values, so the cap does not reduce the final estimate.
- The impact of "cap vs no cap" is quantified as MoC category B.

**References:** draft GL section 5.5. **Decision:** _pending_

## D003 — Region of instability and fully drawn facilities
**Status: PROPOSED**

Near-fully-drawn facilities have a tiny undrawn amount, so the raw CCF explodes (example: limit 1,000, drawn 995, extra drawing 30 → CCF 600%). Fully drawn revolving facilities are in scope of IRB-CCF under the draft GL, but the raw CCF is undefined.

| Option | Pros | Cons |
|---|---|---|
| **Stabilised denominator: max(undrawn, 5% × limit) for utilisation ≥ 95%** | One consistent formula; bounded values; EAD = drawn + CCF × stabilised undrawn is applicable to fully drawn facilities | The 95% / 5% choice is a judgement; must be justified |
| Separate "limit-based" factor (extra drawing / limit) | Intuitive | Two parameters to maintain; not a CCF in the CRR sense |
| Exclude and apply fixed conservative CCF | Simple | Loses information; possibly excessive conservatism |

**Proposal:** stabilised denominator (`realised_ccf.roi_threshold = 0.95`); separate calibration segment for these facilities; sensitivity to the threshold to be shown at checkpoint B.
**References:** CRR Art. 4(1)(56); draft GL sections 4.1, 5.5. **Decision:** _pending_

## D004 — Segmentation (benchmark and calibration segments)
**Status: PROPOSED**

Segment = product × utilisation band at reference date (< 50%, 50–95%, ≥ 95%). Utilisation is the strongest driver in the literature and in the data; product reflects different limit-management policies. To be reviewed at checkpoint C (homogeneity and heterogeneity tests, minimum number of observations per segment).
**References:** draft GL chapter 6. **Decision:** _pending_

## D005 — Long-run average weighting
**Status: PROPOSED**

| Option | Source | Effect |
|---|---|---|
| **Facility-weighted average of all realised CCFs** | draft GL section 7.1 | Years with many defaults (typically downturns) weigh more |
| Arithmetic average of yearly averages | Former ECB Guide to internal models (CCF chapter withdrawn in release 4.1, June 2026) | Each year weighs the same |

Industry responses to the consultation flagged this inconsistency. Both are computed in section 6.1 of the model documentation; the `difference` column shows the impact.
**Proposal:** facility-weighted, following the draft GL; revisit when the final GL is published. **Decision:** _pending_

## D006 — Eligible risk drivers
**Status: PROPOSED**

Only information known **at the reference date** may be used. `limit_cut_flag` (bank cut the limit between reference date and default) is a strong driver in the data but would leak future information, so it is excluded. It remains useful to explain back-testing results and to monitor limit-management policy (CRR Art. 182(1)(h)).
**Decision:** _pending_

## D007 — Estimation sample for final quantification
**Status: PROPOSED**

Models are developed on the development sample and tested out-of-time (default years ≥ 2022). After successful OOT testing, the final long-run average, calibration, downturn and MoC use the **full** observation period, as the draft GL requires all relevant data to be used for the long-run average.
**Decision:** _pending_

## D008 — Downturn period identification
**Status: PROPOSED**

Downturn years = union of (i) the two years with the highest average realised CCF and (ii) macro-economic candidate years (2012–2013 euro-area crisis, 2020 COVID-19). Downturn CCF = max(LRA, average realised CCF in downturn years) per segment; segments with fewer than 30 downturn observations use the portfolio-level ratio. To be aligned with the bank's downturn framework for LGD.
**References:** draft GL chapter 10. **Decision:** _pending_

## D009 — Margin of conservatism
**Status: PROPOSED (placeholder)**

Prototype proxies: A = impact of missing ratings, B = impact of the cap choice (D002), C = bootstrap estimation error (90% quantile). Must be replaced by the bank's approved MoC framework (EBA/GL/2017/16 section 4.4; draft GL chapter 9).
**Decision:** _pending_

## D010 — Facility-level realised CCF vs borrower-level aggregation
**Status: OPEN ISSUE**

Current practice combines restructured facilities at borrower level. CRR Art. 4(1)(56) and the draft GL require a realised CCF per facility, with exceptions only for related contracts under an overarching agreement with comparable characteristics. The current practice must be assessed against this requirement before real-data development starts.
**Decision:** _pending_
