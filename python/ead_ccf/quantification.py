"""Risk quantification: calibration to the long-run average, downturn,
margin of conservatism (MoC) and the CRR3 input floor.

Order of application (EBA draft GL EBA/CP/2025/10 chapters 7, 9, 10):

    model prediction
      -> calibrated to segment long-run average           (calibration factor)
      -> + downturn add-on = downturn CCF - LRA           (add-on >= 0)
      -> + margin of conservatism                         (MoC = A + B + C >= 0)
      -> floored at 50% x standardised CCF                 (CRR3 input floor)

All MoC quantifications here are SIMPLE, TRANSPARENT PROXIES for a synthetic
prototype. Each needs to be replaced by the bank's approved MoC framework.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_DT_OBS = 30


# ----------------------------------------------------------------------------
# Calibration
# ----------------------------------------------------------------------------
def calibration_factors(dev: pd.DataFrame, pred_dev: np.ndarray, lra: pd.Series) -> pd.Series:
    """Multiplicative factor per segment so that mean(prediction) = LRA on dev."""
    tmp = pd.DataFrame({"seg": dev["calib_segment"].to_numpy(), "pred": pred_dev})
    mean_pred = tmp.groupby("seg")["pred"].mean()
    return (lra.reindex(mean_pred.index) / mean_pred).rename("calibration_factor")


# ----------------------------------------------------------------------------
# Downturn
# ----------------------------------------------------------------------------
def identify_downturn_years(df: pd.DataFrame, cfg: dict) -> dict:
    yearly = df.groupby("default_year")["ccf_realised"].mean().sort_values(ascending=False)
    n = cfg["downturn"]["n_worst_years"]
    worst = sorted(int(y) for y in yearly.index[:n])
    macro = cfg["downturn"]["macro_downturn_years"]
    return {"data_driven": worst, "macro_candidates": macro,
            "overlap": sorted(set(worst) & set(macro)),
            "selected": sorted(set(worst) | set(macro))}


def downturn_by_segment(df: pd.DataFrame, lra: pd.Series, dt_years: list[int]) -> pd.DataFrame:
    """Downturn CCF = max(LRA, average realised CCF in downturn years).
    The downturn effect is applied as an ADDITIVE add-on (downturn CCF - LRA).
    A multiplicative factor (downturn / LRA) breaks down when the LRA is close
    to zero or negative, which happens once negative CCFs are kept (D002).

    Segments with fewer than MIN_DT_OBS downturn observations fall back to the
    portfolio-level downturn/LRA ratio (flagged)."""
    in_dt = df["default_year"].isin(dt_years)
    port_ratio = df.loc[in_dt, "ccf_realised"].mean() / df["ccf_realised"].mean()
    rows = []
    for seg, lra_val in lra.items():
        s = df[(df["calib_segment"] == seg) & in_dt]["ccf_realised"]
        if len(s) >= MIN_DT_OBS:
            dt, fb = float(s.mean()), 0
        else:
            dt, fb = float(lra_val * port_ratio), 1
        dt_final = max(dt, float(lra_val))
        rows.append({"calib_segment": seg, "lra": float(lra_val), "n_downturn_obs": len(s),
                     "downturn_observed": dt, "fallback_portfolio_ratio": fb,
                     "downturn_ccf": dt_final,
                     "downturn_addon": dt_final - float(lra_val)})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Margin of conservatism
# ----------------------------------------------------------------------------
def margin_of_conservatism(df: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Per segment:
    A  data deficiencies   : |LRA(all) - LRA(records with complete rating)|
    B  methodological      : |LRA(uncapped) - LRA(realised CCF capped at 100%)|
    C  estimation error    : bootstrap quantile(conf) - bootstrap mean of the LRA
    """
    B_ = cfg["moc"]["bootstrap_samples"]
    q = cfg["moc"]["confidence"]
    rows = []
    for seg, g in df.groupby("calib_segment"):
        v = g["ccf_realised"].to_numpy()
        lra_all = v.mean()
        complete = g.loc[g["grade_ref"].notna(), "ccf_realised"]
        moc_a = abs(lra_all - complete.mean()) if len(complete) else 0.0
        moc_b = abs(lra_all - np.minimum(v, 1.0).mean())
        idx = rng.integers(0, len(v), size=(B_, len(v)))
        boot = v[idx].mean(axis=1)
        moc_c = max(np.quantile(boot, q) - boot.mean(), 0.0)
        rows.append({"calib_segment": seg, "n": len(v), "lra": lra_all,
                     "moc_A_data": moc_a, "moc_B_method": moc_b, "moc_C_estimation": moc_c,
                     "moc_total": moc_a + moc_b + moc_c})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Final CCF and application
# ----------------------------------------------------------------------------
def final_ccf(df: pd.DataFrame, pred_raw: np.ndarray, calib: pd.Series,
              dt: pd.DataFrame, moc: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Final facility-level CCF. For ROI/FULLY_DRAWN, pred_raw is ignored and the
    segment LRA is used (calibration factor 1 on the LRA itself)."""
    out = pd.DataFrame(index=df.index)
    out["calib_segment"] = df["calib_segment"]
    seg = df["calib_segment"]
    lra = dt.set_index("calib_segment")["lra"]
    is_std = df["facility_type"].eq("STANDARD").to_numpy() if "facility_type" in df else \
        df["util_band"].ne(cfg["segmentation"]["band_labels"][-1]).to_numpy()

    out["ccf_model"] = np.where(is_std, pred_raw, seg.map(lra))
    out["calibration_factor"] = np.where(is_std, seg.map(calib).fillna(1.0), 1.0)
    out["ccf_calibrated"] = out["ccf_model"] * out["calibration_factor"]
    out["downturn_addon"] = seg.map(dt.set_index("calib_segment")["downturn_addon"]).fillna(0.0)
    out["ccf_downturn"] = out["ccf_calibrated"] + out["downturn_addon"]
    out["moc"] = seg.map(moc.set_index("calib_segment")["moc_total"]).fillna(0.0)
    out["ccf_before_floor"] = out["ccf_downturn"] + out["moc"]
    sa = df["product"].map({k: v["sa_ccf"] for k, v in cfg["products"].items()})
    out["input_floor"] = 0.5 * sa
    out["ccf_final"] = np.maximum(out["ccf_before_floor"], out["input_floor"])
    out["floor_binding"] = (out["ccf_final"] > out["ccf_before_floor"]).astype(int)
    return out


def apply_standardised(perf: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Out-of-scope facilities (D011): EAD with the standardised CCF."""
    undrawn = (perf["limit_ref"] - perf["drawn_ref"]).clip(lower=0)
    sa = perf["product"].map({k: v["sa_ccf"] for k, v in cfg["products"].items()})
    out = perf[["facility_id", "product", "calib_segment", "limit_ref", "drawn_ref"]].copy()
    out["ccf_final"] = sa.to_numpy()
    out["floor_binding"] = 0
    out["ead_sa"] = perf["drawn_ref"] + sa * undrawn
    out["ead_irb"] = out["ead_sa"]
    out["ccf_approach"] = "F-IRB (standardised CCF)"
    return out


def apply_to_portfolio(perf: pd.DataFrame, final: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """EAD for performing facilities: drawn + CCF x (stabilised) undrawn.
    Also returns the standardised-approach EAD for comparison."""
    thr = cfg["realised_ccf"]["roi_threshold"]
    undrawn = (perf["limit_ref"] - perf["drawn_ref"]).clip(lower=0)
    util = perf["drawn_ref"] / perf["limit_ref"]
    denom = np.where(util >= thr, np.maximum(undrawn, (1 - thr) * perf["limit_ref"]), undrawn)
    sa = perf["product"].map({k: v["sa_ccf"] for k, v in cfg["products"].items()})
    out = perf[["facility_id", "product", "calib_segment", "limit_ref", "drawn_ref"]].copy()
    out["ccf_final"] = final["ccf_final"].to_numpy()
    out["floor_binding"] = final["floor_binding"].to_numpy()
    out["ead_irb"] = perf["drawn_ref"] + out["ccf_final"] * denom
    out["ead_sa"] = perf["drawn_ref"] + sa * undrawn
    return out
