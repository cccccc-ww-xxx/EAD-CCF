"""Segmentation used for the benchmark model and for calibration.

Segment = product x utilisation band at reference date (docs/decisions/D004).
The last utilisation band (>= roi_threshold, incl. fully drawn) is always its
own pool because the realised CCF there uses the stabilised denominator.
"""

from __future__ import annotations

import pandas as pd


def assign_segments(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    s = cfg["segmentation"]
    out = df.copy()
    util = (out["drawn_ref"] / out["limit_ref"]).clip(0, 1)
    out["util_band"] = pd.cut(util, bins=s["utilisation_bands"], labels=s["band_labels"],
                              right=False).astype(str)
    out["calib_segment"] = out["product"] + "/" + out["util_band"]
    return out


def split_dev_oot(df: pd.DataFrame, cfg: dict):
    """Development sample vs out-of-time sample, by default year."""
    oot = cfg["split"]["oot_first_year"]
    return df[df["default_year"] < oot].copy(), df[df["default_year"] >= oot].copy()
