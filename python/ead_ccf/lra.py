"""Long-run average (LRA) realised CCF.

Two weighting methods are computed side by side because the texts differ:

* facility_weighted - average of all realised CCFs in the observation period,
                      each facility weight 1 (EBA draft GL EBA/CP/2025/10, section 7.1)
* yearly_average    - arithmetic average of the yearly average realised CCFs
                      (historical ECB Guide to internal models expectation; the CCF
                      chapter was withdrawn in release 4.1, June 2026)

The chosen method is set in config (lra.method) and justified in docs/decisions/D005.
"""

from __future__ import annotations

import pandas as pd


def lra_by_segment(df: pd.DataFrame, segment_col: str = "calib_segment",
                   value_col: str = "ccf_realised") -> pd.DataFrame:
    fw = (df.groupby(segment_col)
            .agg(n_facilities=(value_col, "size"),
                 lra_facility_weighted=(value_col, "mean"))
            .reset_index())
    yearly = df.groupby([segment_col, "default_year"])[value_col].mean().reset_index()
    ya = (yearly.groupby(segment_col)
                .agg(n_years=("default_year", "nunique"), lra_yearly_average=(value_col, "mean"))
                .reset_index())
    out = fw.merge(ya, on=segment_col, how="left")
    out["difference"] = out["lra_facility_weighted"] - out["lra_yearly_average"]
    return out


def yearly_series(df: pd.DataFrame, value_col: str = "ccf_realised") -> pd.DataFrame:
    """Average realised CCF per default year (portfolio and per product)."""
    port = df.groupby("default_year")[value_col].agg(["size", "mean"]).reset_index()
    port.columns = ["default_year", "n_facilities", "mean_ccf"]
    port["product"] = "ALL"
    prod = df.groupby(["product", "default_year"])[value_col].agg(["size", "mean"]).reset_index()
    prod.columns = ["product", "default_year", "n_facilities", "mean_ccf"]
    return pd.concat([port[prod.columns], prod], ignore_index=True)


def selected_lra(lra_table: pd.DataFrame, cfg: dict) -> pd.Series:
    col = {"facility_weighted": "lra_facility_weighted",
           "yearly_average": "lra_yearly_average"}[cfg["lra"]["method"]]
    return lra_table.set_index("calib_segment")[col]
