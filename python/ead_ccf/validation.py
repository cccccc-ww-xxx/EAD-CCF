"""Performance testing (EBA draft GL EBA/CP/2025/10 section 6.1; EBA validation
handbook). All tests are run on development AND out-of-time samples.

* accuracy       : MAE, RMSE, R^2 of the CCF; ratio of predicted to realised EAD
* discrimination : Spearman rank correlation between prediction and realised CCF
* calibration    : per segment, one-sided t-test  H0: mean(realised) <= estimate
                   (rejection = significant underestimation). Same logic as the
                   CCF back-testing t-test in the ECB CARMA templates.
* stability      : population stability index (PSI) of key drivers dev vs OOT
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def accuracy_metrics(y: np.ndarray, p: np.ndarray, df: pd.DataFrame, name: str,
                     sample: str) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    ss_res = np.sum((y - p) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    ead_pred = df["drawn_ref"].to_numpy() + p * df["ccf_denominator"].to_numpy()
    return {
        "model": name, "sample": sample, "n": len(y),
        "mean_realised": y.mean(), "mean_predicted": p.mean(),
        "MAE": np.mean(np.abs(y - p)),
        "RMSE": np.sqrt(np.mean((y - p) ** 2)),
        "R2": 1 - ss_res / ss_tot if ss_tot > 0 else np.nan,
        "spearman": stats.spearmanr(y, p).statistic,
        "EAD_pred_over_actual": ead_pred.sum() / df["ead_default"].sum(),
    }


def calibration_ttest(df: pd.DataFrame, estimate: np.ndarray, alpha: float,
                      segment_col: str = "calib_segment") -> pd.DataFrame:
    tmp = pd.DataFrame({"seg": df[segment_col].to_numpy(),
                        "y": df["ccf_realised"].to_numpy(),
                        "est": np.asarray(estimate, float)})
    rows = []
    for seg, g in tmp.groupby("seg"):
        n = len(g)
        diff = g["y"] - g["est"]
        if n < 2 or diff.std(ddof=1) == 0:
            t, pval = np.nan, np.nan
        else:
            t = diff.mean() / (diff.std(ddof=1) / np.sqrt(n))
            pval = 1 - stats.t.cdf(t, df=n - 1)
        rows.append({"segment": seg, "n": n, "mean_realised": g["y"].mean(),
                     "mean_estimate": g["est"].mean(), "t_stat": t, "p_value": pval,
                     "result": ("n/a" if np.isnan(pval) else
                                "UNDERESTIMATION" if pval < alpha else "ok")})
    return pd.DataFrame(rows)


def decile_table(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    tmp = pd.DataFrame({"y": y, "p": p})
    tmp["bin"] = pd.qcut(tmp["p"].rank(method="first"), n_bins, labels=False) + 1
    return (tmp.groupby("bin").agg(n=("y", "size"), mean_predicted=("p", "mean"),
                                   mean_realised=("y", "mean")).reset_index())


def psi(expected: pd.Series, actual: pd.Series, bins: int = 10) -> float:
    edges = np.unique(np.quantile(expected.dropna(), np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:  # discrete variable: use its values
        cats = sorted(set(expected.dropna()) | set(actual.dropna()))
        e = expected.value_counts(normalize=True).reindex(cats, fill_value=0)
        a = actual.value_counts(normalize=True).reindex(cats, fill_value=0)
    else:
        edges[0], edges[-1] = -np.inf, np.inf
        e = pd.cut(expected, edges).value_counts(normalize=True, sort=False)
        a = pd.cut(actual, edges).value_counts(normalize=True, sort=False)
    e, a = e.clip(lower=1e-4), a.clip(lower=1e-4)
    return float(np.sum((a - e) * np.log(a / e)))


def stability_table(dev_X: pd.DataFrame, oot_X: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in dev_X.columns:
        v = psi(dev_X[c], oot_X[c])
        rows.append({"variable": c, "psi": v,
                     "assessment": "stable" if v < 0.10 else "monitor" if v < 0.25 else "shift"})
    return pd.DataFrame(rows)
