"""Risk-differentiation models (method ladder, CLAUDE.md section 9).

Rung 1  Benchmark         : segment long-run average (no drivers).
Rung 2  Fractional logit  : Papke & Wooldridge (1996) quasi-likelihood logit on the
                            realised CCF capped to [0, 1]; robust (sandwich) SEs.
                            Implemented from scratch (Newton-Raphson in numpy) so
                            every step is auditable and mirrors SAS PROC NLMIXED.
Rung 4  GBM challenger    : scikit-learn HistGradientBoostingRegressor with
                            monotonic constraints; used for driver discovery only.

Only STANDARD facilities (utilisation < RoI threshold) are modelled with drivers.
ROI / FULLY_DRAWN facilities always use their segment long-run average.

IMPORTANT: only information known AT THE REFERENCE DATE may be a driver.
`limit_cut_flag` happens between reference date and default, so it is NOT used
(it would leak future information) - see docs/decisions/D006.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance

BASE_PRODUCT = "RET_OVD"
PRODUCTS = ["RET_OVD", "RET_CARD", "SME_CRL", "CORP_RCF"]


# ----------------------------------------------------------------------------
# Feature engineering
# ----------------------------------------------------------------------------
class FeatureBuilder:
    """Turns raw fields into model features. Imputation values are learned on the
    development sample and reused unchanged on OOT / application data."""

    def fit(self, df: pd.DataFrame) -> "FeatureBuilder":
        self.grade_median_ = float(df["grade_ref"].median())
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        X = pd.DataFrame(index=df.index)
        X["utilisation"] = (df["drawn_ref"] / df["limit_ref"]).clip(0, 1)
        X["log_limit"] = np.log(df["limit_ref"])
        X["grade_missing"] = df["grade_ref"].isna().astype(int)
        X["grade"] = df["grade_ref"].fillna(self.grade_median_)
        X["arrears_6m"] = df["arrears_flag_6m"].astype(int)
        X["log_mob"] = np.log1p(df["months_on_book"])
        for p in PRODUCTS:
            if p != BASE_PRODUCT:
                X[f"prod_{p}"] = (df["product"] == p).astype(int)
        return X


# ----------------------------------------------------------------------------
# Rung 1 - benchmark
# ----------------------------------------------------------------------------
class SegmentBenchmark:
    def fit(self, df: pd.DataFrame, target: str = "ccf_realised") -> "SegmentBenchmark":
        self.table_ = df.groupby("calib_segment")[target].mean()
        self.overall_ = float(df[target].mean())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return df["calib_segment"].map(self.table_).fillna(self.overall_).to_numpy()


# ----------------------------------------------------------------------------
# Rung 2 - fractional logit (Papke & Wooldridge, 1996)
# ----------------------------------------------------------------------------
class FractionalLogit:
    """Maximises sum[y*log(p) + (1-y)*log(1-p)], p = 1/(1+exp(-Xb)), y in [0,1]."""

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "FractionalLogit":
        self.columns_ = ["intercept"] + list(X.columns)
        Z = np.column_stack([np.ones(len(X)), X.to_numpy(dtype=float)])
        y = np.asarray(y, dtype=float)

        # Newton-Raphson (same technique as SAS PROC NLMIXED TECH=NEWRAP).
        # The quasi-log-likelihood is concave, so Newton converges quickly.
        b = np.zeros(Z.shape[1])
        self.converged_ = False
        for self.n_iter_ in range(1, 101):
            p = 1 / (1 + np.exp(-(Z @ b)))
            grad = Z.T @ (y - p)
            hess = (Z * (p * (1 - p))[:, None]).T @ Z
            step = np.linalg.solve(hess, grad)
            b = b + step
            if np.max(np.abs(step)) < 1e-10:
                self.converged_ = True
                break
        self.coef_ = b

        # robust sandwich covariance: A^-1 B A^-1
        p = 1 / (1 + np.exp(-(Z @ self.coef_)))
        A = (Z * (p * (1 - p))[:, None]).T @ Z
        s = Z * (y - p)[:, None]
        B = s.T @ s
        Ainv = np.linalg.inv(A)
        self.cov_ = Ainv @ B @ Ainv
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        Z = np.column_stack([np.ones(len(X)), X[self.columns_[1:]].to_numpy(dtype=float)])
        return 1 / (1 + np.exp(-(Z @ self.coef_)))

    def summary(self) -> pd.DataFrame:
        se = np.sqrt(np.diag(self.cov_))
        z = self.coef_ / se
        return pd.DataFrame({
            "variable": self.columns_,
            "coefficient": self.coef_,
            "robust_se": se,
            "z_value": z,
            "p_value": 2 * (1 - stats.norm.cdf(np.abs(z))),
        })


# ----------------------------------------------------------------------------
# Rung 4 - gradient boosting challenger
# ----------------------------------------------------------------------------
MONOTONE = {"utilisation": -1, "grade": 1, "arrears_6m": 1}


class GBMChallenger:
    def fit(self, X: pd.DataFrame, y: np.ndarray, seed: int) -> "GBMChallenger":
        cst = [MONOTONE.get(c, 0) for c in X.columns]
        self.model_ = HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.05, max_depth=3, min_samples_leaf=50,
            l2_regularization=1.0, monotonic_cst=cst, random_state=seed)
        self.model_.fit(X, y)
        self.columns_ = list(X.columns)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.clip(self.model_.predict(X[self.columns_]), 0, None)

    def importance(self, X: pd.DataFrame, y: np.ndarray, seed: int) -> pd.DataFrame:
        r = permutation_importance(self.model_, X[self.columns_], y, n_repeats=10,
                                   random_state=seed, scoring="neg_mean_absolute_error")
        return (pd.DataFrame({"variable": self.columns_,
                              "mae_increase": r.importances_mean,
                              "std": r.importances_std})
                .sort_values("mae_increase", ascending=False).reset_index(drop=True))
