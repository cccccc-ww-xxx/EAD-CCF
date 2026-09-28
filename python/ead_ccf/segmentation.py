"""Segmentation used for the benchmark model and for calibration.

Each facility gets a utilisation band at the reference date. Each band is then
split by product, by retail/corporate, or pooled, as set in
config segmentation.split_by (decision D004). The last band (>= RoI threshold,
incl. fully drawn) is always separate because its realised CCF uses the
stabilised denominator (D003).

Current setting (D004 approved): RETAIL/U1_lt50, CORPORATE/U1_lt50,
ALL/U2_50_95, ALL/U3_ge95.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def assign_segments(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    s = cfg["segmentation"]
    out = df.copy()
    util = (out["drawn_ref"] / out["limit_ref"]).clip(0, 1)
    out["util_band"] = pd.cut(util, bins=s["utilisation_bands"], labels=s["band_labels"],
                              right=False).astype(str)
    split = out["util_band"].map(s["split_by"])
    prefix = np.select([split.eq("product"), split.eq("segment")],
                       [out["product"], out["segment"].str.upper()], default="ALL")
    out["calib_segment"] = pd.Series(prefix, index=out.index) + "/" + out["util_band"]
    return out


def split_dev_oot(df: pd.DataFrame, cfg: dict):
    """Development sample vs out-of-time sample, by default year."""
    oot = cfg["split"]["oot_first_year"]
    return df[df["default_year"] < oot].copy(), df[df["default_year"] >= oot].copy()
