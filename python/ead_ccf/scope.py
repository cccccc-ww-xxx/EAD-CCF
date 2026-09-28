"""Scope of own CCF estimates (decision D011 - regulatory requirement).

* CRR3 Art. 166(8b): own CCF estimates only for undrawn REVOLVING commitments.
  All four synthetic products are revolving; non-revolving commitments would be
  out of scope and receive the standardised CCF (CRR3 Annex I / Art. 111).
* CRR3 Art. 151(8): corporates with annual turnover above EUR 500 million may
  only use the Foundation IRB approach -> no own CCF estimates, standardised CCF.

Out-of-scope facilities are EXCLUDED from the reference data set used for
estimation and receive the standardised CCF in the application step.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def flag_scope(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = df.copy()
    thr = cfg["scope"]["large_corporate_turnover_meur"]
    large = out["segment"].eq("corporate") & (out["annual_turnover_meur"] > thr)
    out["airb_ccf_scope"] = (~large).astype(int)
    out["scope_reason"] = np.where(large, f"large corporate (turnover > EUR {thr}m): F-IRB, SA CCF",
                                   "in scope: revolving, A-IRB eligible")
    return out


def scope_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (df.groupby(["product", "scope_reason"])
              .agg(n_facilities=("facility_id", "size"), sum_limit=("limit_ref", "sum"))
              .reset_index())
