"""Segmentation tests (checkpoint C, decision D004).

A good segmentation has
  1. HETEROGENEITY between segments  -> adjacent segments differ significantly
  2. STABILITY over time             -> the ordering of segments holds year by year
  3. ENOUGH DATA per segment          -> reliable averages

Tests (all on the realised CCF used for estimation):
  * Welch two-sample t-test between neighbouring utilisation bands within each
    product, and between products within each utilisation band
    (the latter also tests whether products could be pooled, e.g. overdraft vs card).
  * Rank stability: share of default years in which the lower utilisation band
    has the higher average CCF (the expected ordering), per product.
  * Spearman correlation between each year's segment ranking and the
    full-period ranking.
  * Minimum number of defaults per segment and per segment-year.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats


def _welch(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return float(t), float(p)


def heterogeneity_tests(df: pd.DataFrame, bands: list[str], alpha: float = 0.05) -> pd.DataFrame:
    rows = []
    # 1) neighbouring utilisation bands within each product
    for prod, g in df.groupby("product"):
        for b1, b2 in zip(bands[:-1], bands[1:]):
            a = g.loc[g["util_band"] == b1, "ccf_realised"].to_numpy()
            b = g.loc[g["util_band"] == b2, "ccf_realised"].to_numpy()
            t, p = _welch(a, b)
            rows.append({"comparison": "band within product", "group": prod,
                         "segment_a": f"{prod}/{b1}", "segment_b": f"{prod}/{b2}",
                         "n_a": len(a), "n_b": len(b), "mean_a": a.mean(), "mean_b": b.mean(),
                         "t_stat": t, "p_value": p})
    # 2) products within each utilisation band (all pairs)
    for band, g in df.groupby("util_band"):
        prods = sorted(g["product"].unique())
        for p1, p2 in combinations(prods, 2):
            a = g.loc[g["product"] == p1, "ccf_realised"].to_numpy()
            b = g.loc[g["product"] == p2, "ccf_realised"].to_numpy()
            t, p = _welch(a, b)
            rows.append({"comparison": "product within band", "group": band,
                         "segment_a": f"{p1}/{band}", "segment_b": f"{p2}/{band}",
                         "n_a": len(a), "n_b": len(b), "mean_a": a.mean(), "mean_b": b.mean(),
                         "t_stat": t, "p_value": p})
    out = pd.DataFrame(rows)
    out["result"] = np.where(out["p_value"] < alpha, "different", "NOT different")
    return out


def ordering_stability(df: pd.DataFrame, bands: list[str]) -> pd.DataFrame:
    """Share of years in which band k has a higher average CCF than band k+1."""
    yearly = df.groupby(["product", "util_band", "default_year"])["ccf_realised"].mean().unstack(1)
    rows = []
    for prod, g in yearly.groupby(level=0):
        for b1, b2 in zip(bands[:-1], bands[1:]):
            both = g[[b1, b2]].dropna()
            rows.append({"product": prod, "higher": b1, "lower": b2, "n_years": len(both),
                         "share_years_order_holds": float((both[b1] > both[b2]).mean())})
    return pd.DataFrame(rows)


def rank_correlation_by_year(df: pd.DataFrame) -> pd.DataFrame:
    full = df.groupby("calib_segment")["ccf_realised"].mean()
    rows = []
    for yr, g in df.groupby("default_year"):
        y = g.groupby("calib_segment")["ccf_realised"].mean().reindex(full.index)
        mask = y.notna()
        rho = stats.spearmanr(full[mask], y[mask]).statistic
        rows.append({"default_year": int(yr), "n_segments": int(mask.sum()),
                     "min_defaults_in_segment": int(g.groupby("calib_segment").size().min()),
                     "spearman_vs_full_period": float(rho)})
    return pd.DataFrame(rows)


def segment_counts(df: pd.DataFrame) -> pd.DataFrame:
    tot = df.groupby("calib_segment").size().rename("n_defaults")
    per_year = df.groupby(["calib_segment", "default_year"]).size()
    return (pd.DataFrame({"n_defaults": tot,
                          "min_per_year": per_year.groupby(level=0).min(),
                          "mean_per_year": per_year.groupby(level=0).mean()})
              .reset_index())


def chosen_segment_tests(df: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """Welch t-test between every pair of the CHOSEN calibration segments."""
    rows = []
    segs = sorted(df["calib_segment"].unique())
    for s1, s2 in combinations(segs, 2):
        a = df.loc[df["calib_segment"] == s1, "ccf_realised"].to_numpy()
        b = df.loc[df["calib_segment"] == s2, "ccf_realised"].to_numpy()
        t, p = _welch(a, b)
        rows.append({"segment_a": s1, "segment_b": s2, "mean_a": a.mean(), "mean_b": b.mean(),
                     "t_stat": t, "p_value": p,
                     "result": "different" if p < alpha else "NOT different"})
    return pd.DataFrame(rows)
