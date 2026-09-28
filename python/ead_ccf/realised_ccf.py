"""Realised CCF per facility per default.

Definition (CRR3 Art. 4(1)(56), EBA draft GL EBA/CP/2025/10 section 5.5):

    realised CCF = (drawn at default - drawn at reference date)
                   / (limit at reference date - drawn at reference date)

Facility types at the reference date:

* STANDARD    utilisation < roi_threshold   -> raw CCF is stable
* ROI         roi_threshold <= util < 1      -> "region of instability": the
              undrawn amount is tiny, so raw CCFs explode
* FULLY_DRAWN undrawn amount = 0             -> raw CCF undefined

PROPOSED treatment (see docs/decisions/D003): for ROI and FULLY_DRAWN
facilities the denominator is stabilised to (1 - roi_threshold) x limit, i.e.
the extra drawing is expressed relative to a minimum "notional undrawn".
The raw CCF is kept alongside for transparency.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_realised_ccf(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rc = cfg["realised_ccf"]
    thr = rc["roi_threshold"]
    out = df.copy()

    out["undrawn_ref"] = (out["limit_ref"] - out["drawn_ref"]).clip(lower=0)
    out["utilisation_ref"] = out["drawn_ref"] / out["limit_ref"]
    out["extra_drawing"] = out["ead_default"] - out["drawn_ref"]

    out["facility_type"] = np.select(
        [out["undrawn_ref"] <= 0, out["utilisation_ref"] >= thr],
        ["FULLY_DRAWN", "ROI"], default="STANDARD")

    # raw CCF (undefined for fully drawn)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["ccf_raw"] = np.where(out["undrawn_ref"] > 0,
                                  out["extra_drawing"] / out["undrawn_ref"], np.nan)

    # stabilised denominator for ROI / FULLY_DRAWN
    notional = (1 - thr) * out["limit_ref"]
    out["ccf_denominator"] = np.where(out["facility_type"] == "STANDARD",
                                      out["undrawn_ref"],
                                      np.maximum(out["undrawn_ref"], notional))
    ccf = out["extra_drawing"] / out["ccf_denominator"]

    # floor on the realised CCF used for estimation (D002: depends on facility type)
    std = out["facility_type"] == "STANDARD"
    if rc.get("floor_standard") is not None:
        ccf = ccf.where(~std, ccf.clip(lower=rc["floor_standard"]))
    if rc.get("floor_near_full") is not None:
        ccf = ccf.where(std, ccf.clip(lower=rc["floor_near_full"]))
    if rc.get("cap") is not None:
        ccf = ccf.clip(upper=rc["cap"])
    out["ccf_realised"] = ccf

    # target for the fractional logit only, restricted to [0, model_cap]
    out["ccf_model_target"] = ccf.clip(0, rc["model_cap"])

    out["flag_negative_raw"] = (out["extra_drawing"] < 0).astype(int)
    out["flag_above_one"] = (out["ccf_realised"] > 1).astype(int)
    return out


def data_quality_checks(df: pd.DataFrame) -> pd.DataFrame:
    """Basic technical/logical checks on the reference data set.

    Returns one row per check with the number and share of failing records.
    """
    n = len(df)
    checks = {
        "DQ01 missing facility_id": df["facility_id"].isna(),
        "DQ02 duplicate facility_id": df["facility_id"].duplicated(keep=False),
        "DQ03 limit_ref <= 0": df["limit_ref"] <= 0,
        "DQ04 drawn_ref < 0": df["drawn_ref"] < 0,
        "DQ05 drawn_ref > limit_ref": df["drawn_ref"] > df["limit_ref"] + 0.01,
        "DQ06 ead_default < 0": df["ead_default"] < 0,
        "DQ07 reference_date >= default_date":
            pd.to_datetime(df["reference_date"]) >= pd.to_datetime(df["default_date"]),
        "DQ08 missing grade_ref": df["grade_ref"].isna(),
        "DQ09 grade_ref outside 1-12": df["grade_ref"].notna() & ~df["grade_ref"].between(1, 12),
        "DQ10 missing ead_default": df["ead_default"].isna(),
    }
    rows = [{"check": k, "n_fail": int(v.sum()), "pct_fail": round(100 * v.sum() / n, 3)}
            for k, v in checks.items()]
    return pd.DataFrame(rows)


def population_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Counts by facility type and product - reconciled against SAS."""
    g = (df.groupby(["product", "facility_type"])
           .agg(n_facilities=("facility_id", "count"),
                sum_limit_ref=("limit_ref", "sum"),
                sum_drawn_ref=("drawn_ref", "sum"),
                sum_ead_default=("ead_default", "sum"),
                mean_ccf_realised=("ccf_realised", "mean"))
           .reset_index())
    return g
