# Data dictionary (synthetic data)

## `data/raw/defaults.csv` — reference data set, one row per defaulted facility

| Column | Type | Description |
|---|---|---|
| facility_id | text | Facility identifier (synthetic) |
| obligor_id | text | Obligor identifier; ~15% of corporate facilities share an obligor |
| product | text | RET_OVD, RET_CARD, SME_CRL, CORP_RCF |
| segment | text | retail / corporate |
| reference_date | date | Default date − 12 months (fixed horizon, decision D001) |
| default_date | date | Date of default |
| default_year | int | Year of default (drives dev/OOT split and long-run average) |
| limit_ref | num | Committed limit at reference date |
| drawn_ref | num | Drawn amount at reference date |
| grade_ref | num | Rating grade at reference date, 1 (best) – 12 (worst); ~2% missing |
| months_on_book | int | Facility age at reference date |
| arrears_flag_6m | 0/1 | Any arrears in the 6 months before reference date |
| limit_cut_flag | 0/1 | Bank cut the limit between reference date and default — **not a driver** (D006) |
| limit_default | num | Limit at default |
| ead_default | num | Drawn amount at default (realised EAD) |
| annual_turnover_meur | num | Obligor annual turnover in EUR million (corporate only); > 500 = large corporate, F-IRB, out of scope (D011) |

## `data/raw/performing.csv` — application portfolio at 2025-12-31

Same characteristics as above at the application date, without default information (incl. `annual_turnover_meur`).

## Derived fields (`data/derived/rds_realised_ccf.csv`)

| Column | Description |
|---|---|
| undrawn_ref | max(limit_ref − drawn_ref, 0) |
| utilisation_ref | drawn_ref / limit_ref |
| extra_drawing | ead_default − drawn_ref |
| facility_type | STANDARD / ROI / FULLY_DRAWN (D003) |
| ccf_raw | extra_drawing / undrawn_ref (undefined when undrawn = 0) |
| ccf_denominator | undrawn_ref, or max(undrawn_ref, 5% × limit) for ROI / fully drawn |
| ccf_realised | extra_drawing / ccf_denominator; negatives kept for STANDARD, floored at 0 for ROI / FULLY_DRAWN; no cap (D002) |
| ccf_model_target | ccf_realised capped to [0, 1] — fractional-logit target only |
| util_band, calib_segment | Utilisation band and calibration segment: RETAIL/U1_lt50, CORPORATE/U1_lt50, ALL/U2_50_95, ALL/U3_ge95 (D004) |

## What the synthetic data-generating process contains

Known drivers: utilisation (−), rating grade (+), arrears (+), product, downturn years
2012, 2013, 2020 (+), limit cut (−). **No effect**: limit size, months on book.
Because the truth is known, the documentation checks whether the estimation recovers it.
