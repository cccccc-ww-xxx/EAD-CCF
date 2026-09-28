"""Reconcile the Python and SAS implementations.

    python python/reconcile.py

Compares outputs/python/recon_*.csv with outputs/sas/recon_*.csv (written by
sas/07_export_recon.sas) and writes docs/reconciliation/reconciliation_report.md.

Tolerances (CLAUDE.md section 4 - "reconciled within a stated tolerance"):
* counts                         : exact
* sums, means, shares, quantiles : relative difference <= 1e-6
* fractional-logit coefficients  : absolute difference <= 1e-4 (two different optimisers)
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ead_ccf.config import paths  # noqa: E402

CHECKS = [
    # file, key columns, {column: (type, tolerance)}
    ("recon_population", ["product", "facility_type"],
     {"n_facilities": ("exact", 0), "sum_limit_ref": ("rel", 1e-6),
      "sum_drawn_ref": ("rel", 1e-6), "sum_ead_default": ("rel", 1e-6),
      "mean_ccf_realised": ("rel", 1e-6)}),
    ("recon_ccf_distribution", ["product", "facility_type"],
     {"n": ("exact", 0), "mean": ("rel", 1e-6), "p25": ("abs", 1e-6), "median": ("abs", 1e-6),
      "p75": ("abs", 1e-6), "share_zero": ("abs", 1e-9), "share_ge_one": ("abs", 1e-9),
      "share_negative_raw": ("abs", 1e-9)}),
    ("recon_lra_by_segment", ["calib_segment"],
     {"n_facilities": ("exact", 0), "lra_facility_weighted": ("rel", 1e-6),
      "n_years": ("exact", 0), "lra_yearly_average": ("rel", 1e-6)}),
    ("recon_fractional_logit", ["variable"],
     {"coefficient": ("abs", 1e-4), "robust_se": ("abs", 1e-4)}),
]


def compare(py: pd.DataFrame, sas: pd.DataFrame, keys, cols) -> pd.DataFrame:
    sas = sas.copy()
    sas.columns = [c.strip() for c in sas.columns]
    # SAS column names are case-insensitive; align to Python spelling
    lower = {c.lower(): c for c in py.columns}
    sas = sas.rename(columns={c: lower.get(c.lower(), c) for c in sas.columns})
    for k in keys:
        py[k], sas[k] = py[k].astype(str).str.strip(), sas[k].astype(str).str.strip()
    m = py.merge(sas, on=keys, how="outer", suffixes=("_py", "_sas"), indicator=True)
    rows = []
    for _, r in m.iterrows():
        key = " / ".join(str(r[k]) for k in keys)
        if r["_merge"] != "both":
            rows.append({"key": key, "column": "(row)", "python": "", "sas": "",
                         "difference": "", "status": f"MISSING ({r['_merge']})"})
            continue
        for c, (kind, tol) in cols.items():
            a, b = float(r[f"{c}_py"]), float(r[f"{c}_sas"])
            if kind == "exact":
                d, ok = abs(a - b), a == b
            elif kind == "rel":
                d = abs(a - b) / max(abs(a), 1e-12)
                ok = d <= tol or abs(a - b) <= 1e-12
            else:
                d, ok = abs(a - b), abs(a - b) <= tol
            rows.append({"key": key, "column": c, "python": a, "sas": b,
                         "difference": d, "status": "OK" if ok else "BREAK"})
    return pd.DataFrame(rows)


def main() -> int:
    P = paths()
    out_dir = P["docs"] / "reconciliation"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# Python vs SAS reconciliation\n", f"Run date: {date.today().isoformat()}\n"]
    overall = True
    for name, keys, cols in CHECKS:
        fpy, fsas = P["out_py"] / f"{name}.csv", P["out_sas"] / f"{name}.csv"
        lines.append(f"\n## {name}\n")
        if not fsas.exists():
            lines.append(f"**PENDING** — `{fsas.relative_to(P['root'])}` not found. "
                         "Run `sas/run_all.sas` first.\n")
            overall = False
            continue
        res = compare(pd.read_csv(fpy), pd.read_csv(fsas), keys, cols)
        n_break = int((res["status"] != "OK").sum())
        overall &= n_break == 0
        lines.append(f"Compared values: {len(res)}, breaks: **{n_break}**\n")
        show = res[res["status"] != "OK"] if n_break else res.head(10)
        lines.append(show.to_string(index=False) if len(show) else "(none)")
        lines.append("")
    lines.insert(2, f"\n**Overall result: {'RECONCILED' if overall else 'NOT RECONCILED / PENDING'}**\n")
    (out_dir / "reconciliation_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:4]))
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
