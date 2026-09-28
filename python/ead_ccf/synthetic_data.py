"""Generate SYNTHETIC reference and application data for the EAD-CCF prototype.

No real client data is used anywhere in this project. The generator is built so
that the data shows the features the EBA draft CCF Guidelines (EBA/CP/2025/10)
and the literature care about:

* bimodal realised CCFs with mass at 0 and at 1 (Tong et al., 2016)
* negative CCFs (repayments) and CCFs above 100% (over-limit drawing)
* near-fully-drawn facilities in the "region of instability" and fully drawn
  facilities (both in scope of IRB-CCF under the draft GL)
* CCF that falls with utilisation and rises with obligor risk and arrears
* limit cuts by the bank before default (lower CCF)
* higher drawdowns in downturn years
* a few missing rating grades (to illustrate margin of conservatism category A)

Because we KNOW the data-generating process, the pipeline can be checked for
whether it recovers the true drivers - something impossible on real data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PRODUCT_MIX = {"RET_OVD": 0.35, "RET_CARD": 0.30, "SME_CRL": 0.20, "CORP_RCF": 0.15}

# log-normal parameters (mu, sigma) of the limit at reference date, per product
LIMIT_PARAMS = {
    "RET_OVD": (np.log(2_500), 0.6),
    "RET_CARD": (np.log(3_500), 0.5),
    "SME_CRL": (np.log(60_000), 0.8),
    "CORP_RCF": (np.log(1_500_000), 0.9),
}

# beta(a, b) for utilisation of partially drawn defaulted facilities
UTIL_BETA_DEFAULTED = {
    "RET_OVD": (2.2, 1.8),
    "RET_CARD": (2.5, 1.5),
    "SME_CRL": (1.8, 2.0),
    "CORP_RCF": (1.5, 2.5),
}

# product effects on the CCF level (logit scale)
PRODUCT_EFFECT = {"RET_OVD": 0.30, "RET_CARD": 0.20, "SME_CRL": 0.0, "CORP_RCF": -0.35}


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _draw_common(rng, n, products, defaulted: bool):
    """Characteristics shared by defaulted and performing facilities."""
    limit = np.array([rng.lognormal(*LIMIT_PARAMS[p]) for p in products])
    limit = np.round(limit, -1).clip(min=500)

    if defaulted:
        grade = rng.choice(np.arange(1, 13), size=n,
                           p=np.array([1, 1, 2, 3, 4, 6, 9, 12, 15, 17, 16, 14]) / 100)
        arrears = rng.binomial(1, 0.30, n)
    else:
        grade = rng.choice(np.arange(1, 13), size=n,
                           p=np.array([6, 9, 12, 14, 14, 13, 11, 8, 6, 4, 2, 1]) / 100)
        arrears = rng.binomial(1, 0.04, n)

    mob = np.round(rng.gamma(2.5, 24, n)).astype(int).clip(3, 360)
    return limit, grade, arrears, mob


def generate_defaults(cfg: dict) -> pd.DataFrame:
    """Defaulted facilities with values at reference date and at default."""
    s = cfg["synthetic"]
    rng = np.random.default_rng(cfg["seed"])
    n = s["n_defaults"]

    products = rng.choice(list(PRODUCT_MIX), size=n, p=list(PRODUCT_MIX.values()))
    years = np.arange(s["first_default_year"], s["last_default_year"] + 1)
    dt_years = set(s["downturn_years_dgp"])
    year_w = np.array([1.5 if y in dt_years else 1.0 for y in years])
    default_year = rng.choice(years, size=n, p=year_w / year_w.sum())
    default_date = pd.to_datetime(default_year.astype(str) + "-01-01") + pd.to_timedelta(
        rng.integers(0, 365, n), unit="D")
    horizon = cfg["realised_ccf"]["horizon_months"]
    reference_date = default_date - pd.DateOffset(months=horizon)
    downturn = np.isin(default_year, list(dt_years)).astype(int)

    limit, grade, arrears, mob = _draw_common(rng, n, products, defaulted=True)

    # --- utilisation at reference date: fully drawn / RoI / partially drawn
    util_type = rng.choice(["full", "roi", "partial"], size=n, p=[0.10, 0.08, 0.82])
    util = np.empty(n)
    for i, (t, p) in enumerate(zip(util_type, products)):
        if t == "full":
            util[i] = 1.0
        elif t == "roi":
            util[i] = rng.uniform(0.95, 0.9999)
        else:
            util[i] = min(rng.beta(*UTIL_BETA_DEFAULTED[p]), 0.9499)
    drawn_ref = np.round(limit * util, 2)
    undrawn_ref = limit - drawn_ref

    limit_cut = rng.binomial(1, 0.08, n)
    prod_eff = np.array([PRODUCT_EFFECT[p] for p in products])
    g = grade - 8.0

    # --- true CCF for partially drawn facilities (three-part mixture)
    p_full = _sigmoid(-1.9 - 1.2 * util + 0.15 * g + 0.6 * arrears
                      + 0.5 * downturn - 1.5 * limit_cut + 0.5 * prod_eff)
    p_zero = _sigmoid(-1.3 + 1.4 * util - 0.10 * g - 0.3 * arrears
                      + 0.9 * limit_cut - 0.3 * downturn)
    mu = _sigmoid(-0.2 - 1.3 * (util - 0.5) + 0.12 * g + 0.4 * arrears
                  + 0.4 * downturn - 0.7 * limit_cut + prod_eff)
    phi = 4.0
    mid = rng.beta(mu * phi, (1 - mu) * phi)

    u = rng.uniform(size=n)
    is_full = u < p_full
    is_zero = (~is_full) & (rng.uniform(size=n) < p_zero)
    ccf = mid.copy()
    # zero / negative part: 60% exactly zero, 40% repayment
    neg = rng.uniform(size=n) < 0.40
    ccf[is_zero & ~neg] = 0.0
    repay = -rng.uniform(0, 0.6, n) * drawn_ref / np.maximum(undrawn_ref, 1e-9)
    ccf[is_zero & neg] = np.maximum(repay[is_zero & neg], -1.5)
    # full-draw part: 80% exactly limit, 20% over-limit (not after a limit cut)
    over = (rng.uniform(size=n) < 0.20) & (limit_cut == 0)
    ccf[is_full] = 1.0
    ccf[is_full & over] = 1.0 + rng.exponential(0.08, n)[is_full & over]

    ead_default = drawn_ref + ccf * undrawn_ref

    # --- RoI and fully drawn: generate the extra drawing relative to the LIMIT
    near = util_type != "partial"
    kind = rng.choice(["repay", "flat", "overdraw"], size=n, p=[0.40, 0.25, 0.35])
    addon = np.where(kind == "repay", -rng.uniform(0, 0.10, n),
             np.where(kind == "flat", 0.0,
                      rng.exponential(0.035 + 0.03 * downturn + 0.01 * arrears, n)))
    ead_default[near] = drawn_ref[near] + addon[near] * limit[near]

    ead_default = np.round(np.maximum(ead_default, 0.0), 2)
    limit_def = np.where(limit_cut == 1, np.round(limit * rng.uniform(0.5, 0.9, n), -1), limit)
    limit_def = np.maximum(limit_def, np.minimum(ead_default, limit))

    # --- obligors: ~15% of corporate facilities share an obligor with another facility
    obligor_id = np.array([f"OBL{100000 + i}" for i in range(n)])
    corp_idx = np.where(np.isin(products, ["SME_CRL", "CORP_RCF"]))[0]
    share = rng.choice(corp_idx, size=int(0.15 * len(corp_idx)), replace=False)
    for i in share:
        obligor_id[i] = obligor_id[rng.choice(corp_idx)]

    grade = grade.astype(float)
    grade[rng.uniform(size=n) < 0.02] = np.nan  # missing ratings (MoC category A)

    df = pd.DataFrame({
        "facility_id": [f"FAC{1000000 + i}" for i in range(n)],
        "obligor_id": obligor_id,
        "product": products,
        "segment": [cfg["products"][p]["segment"] for p in products],
        "reference_date": reference_date.strftime("%Y-%m-%d"),
        "default_date": default_date.strftime("%Y-%m-%d"),
        "default_year": default_year,
        "limit_ref": limit,
        "drawn_ref": drawn_ref,
        "grade_ref": grade,
        "months_on_book": mob,
        "arrears_flag_6m": arrears,
        "limit_cut_flag": limit_cut,
        "limit_default": limit_def,
        "ead_default": ead_default,
    })
    return df.sort_values(["default_date", "facility_id"]).reset_index(drop=True)


def generate_performing(cfg: dict) -> pd.DataFrame:
    """Performing (non-defaulted) facilities at the application date."""
    s = cfg["synthetic"]
    rng = np.random.default_rng(cfg["seed"] + 1)
    n = s["n_performing"]
    products = rng.choice(list(PRODUCT_MIX), size=n, p=list(PRODUCT_MIX.values()))
    limit, grade, arrears, mob = _draw_common(rng, n, products, defaulted=False)
    util_type = rng.choice(["full", "roi", "partial"], size=n, p=[0.04, 0.04, 0.92])
    util = np.where(util_type == "full", 1.0,
                    np.where(util_type == "roi", rng.uniform(0.95, 0.9999, n),
                             np.minimum(rng.beta(1.6, 3.2, n), 0.9499)))
    return pd.DataFrame({
        "facility_id": [f"PFC{2000000 + i}" for i in range(n)],
        "product": products,
        "segment": [cfg["products"][p]["segment"] for p in products],
        "application_date": s["application_date"],
        "limit_ref": limit,
        "drawn_ref": np.round(limit * util, 2),
        "grade_ref": grade.astype(float),
        "months_on_book": mob,
        "arrears_flag_6m": arrears,
        "limit_cut_flag": 0,
    })
