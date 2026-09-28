"""Run the full EAD-CCF prototype pipeline on synthetic data.

    python python/run_pipeline.py

Every table and chart in docs/model_documentation.md is produced by this run.
Reconciliation files for the SAS comparison go to outputs/python/recon_*.csv.
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ead_ccf import lra, models, quantification, realised_ccf, report, segmentation, validation
from ead_ccf.config import load_config, paths
from ead_ccf.synthetic_data import generate_defaults, generate_performing


def main() -> dict:
    cfg = load_config()
    P = paths()
    rng = np.random.default_rng(cfg["seed"])
    R: dict = {"config": cfg}

    # ---------------------------------------------------------------- 1. data
    defaults = generate_defaults(cfg)
    performing = generate_performing(cfg)
    defaults.to_csv(P["raw"] / "defaults.csv", index=False)
    performing.to_csv(P["raw"] / "performing.csv", index=False)
    print(f"[1] synthetic data: {len(defaults):,} defaults, {len(performing):,} performing")

    # ---------------------------------------------------- 2. realised CCF + DQ
    R["dq"] = realised_ccf.data_quality_checks(defaults)
    rds = realised_ccf.compute_realised_ccf(defaults, cfg)
    rds = segmentation.assign_segments(rds, cfg)
    rds.to_csv(P["derived"] / "rds_realised_ccf.csv", index=False)
    R["population"] = realised_ccf.population_summary(rds)
    R["ccf_distribution"] = ccf_distribution(rds)
    R["rds"] = rds
    print("[2] realised CCF computed")

    # ----------------------------------------------------------------- 3. LRA
    R["yearly"] = lra.yearly_series(rds)
    R["lra_full"] = lra.lra_by_segment(rds)
    dev, oot = segmentation.split_dev_oot(rds, cfg)
    R["n_dev"], R["n_oot"] = len(dev), len(oot)
    lra_dev = lra.selected_lra(lra.lra_by_segment(dev), cfg)
    print("[3] long-run averages computed")

    # ----------------------------------------------- 4. risk differentiation
    std_dev = dev[dev["facility_type"] == "STANDARD"]
    std_oot = oot[oot["facility_type"] == "STANDARD"]
    fb = models.FeatureBuilder().fit(std_dev)
    Xd, Xo = fb.transform(std_dev), fb.transform(std_oot)
    yd_fit = std_dev["ccf_model_target"].to_numpy()

    bench = models.SegmentBenchmark().fit(dev)
    fl = models.FractionalLogit().fit(Xd, yd_fit)
    gbm = models.GBMChallenger().fit(Xd, yd_fit, seed=cfg["seed"])
    R["fl_summary_dev"] = fl.summary()
    R["gbm_importance"] = gbm.importance(Xo, std_oot["ccf_model_target"].to_numpy(), cfg["seed"])

    preds = {}
    for name, m in [("fractional_logit", fl), ("gbm_challenger", gbm)]:
        pdv, pot = m.predict(Xd), m.predict(Xo)
        cf = quantification.calibration_factors(std_dev, pdv, lra_dev)
        preds[name] = (pdv * std_dev["calib_segment"].map(cf).fillna(1).to_numpy(),
                       pot * std_oot["calib_segment"].map(cf).fillna(1).to_numpy())
    preds["benchmark"] = (bench.predict(std_dev), bench.predict(std_oot))

    rows = []
    for name, (pdv, pot) in preds.items():
        rows.append(validation.accuracy_metrics(std_dev["ccf_realised"], pdv, std_dev, name, "DEV"))
        rows.append(validation.accuracy_metrics(std_oot["ccf_realised"], pot, std_oot, name, "OOT"))
    R["performance"] = pd.DataFrame(rows)

    # method ladder: fractional logit replaces the benchmark only if it beats it OOT
    perf = R["performance"].set_index(["model", "sample"])
    fl_wins = (perf.loc[("fractional_logit", "OOT"), "MAE"] < perf.loc[("benchmark", "OOT"), "MAE"]
               and perf.loc[("fractional_logit", "OOT"), "spearman"]
               > perf.loc[("benchmark", "OOT"), "spearman"])
    R["selected_model"] = "fractional_logit" if fl_wins else "benchmark"

    R["deciles_oot"] = validation.decile_table(std_oot["ccf_realised"].to_numpy(),
                                               preds[R["selected_model"]][1])
    oot_est = pd.Series(oot["calib_segment"].map(lra_dev).to_numpy(), index=oot.index)
    oot_est.loc[std_oot.index] = preds[R["selected_model"]][1]
    R["ttest_oot_calibrated"] = validation.calibration_ttest(oot, oot_est.to_numpy(),
                                                             cfg["validation"]["ttest_alpha"])
    R["stability"] = validation.stability_table(Xd, Xo)
    print(f"[4] models fitted - selected: {R['selected_model']}")

    # ------------------------------------ 5. final quantification (full sample)
    lra_all = lra.selected_lra(R["lra_full"], cfg)
    std_all = rds[rds["facility_type"] == "STANDARD"]
    fb_all = models.FeatureBuilder().fit(std_all)
    X_all = fb_all.transform(std_all)
    fl_all = models.FractionalLogit().fit(X_all, std_all["ccf_model_target"].to_numpy())
    R["fl_summary_full"] = fl_all.summary()
    if not (fl.converged_ and fl_all.converged_):
        raise RuntimeError("Fractional logit did not converge - stop and investigate")

    def raw_pred(df):
        out = np.full(len(df), np.nan)
        mask = (df["drawn_ref"] / df["limit_ref"] < cfg["realised_ccf"]["roi_threshold"]).to_numpy()
        if R["selected_model"] == "fractional_logit":
            out[mask] = fl_all.predict(fb_all.transform(df[mask]))
        else:
            out[mask] = df.loc[mask, "calib_segment"].map(lra_all).to_numpy()
        return out

    calib = quantification.calibration_factors(std_all, raw_pred(std_all), lra_all)
    R["downturn_years"] = quantification.identify_downturn_years(rds, cfg)
    R["downturn"] = quantification.downturn_by_segment(rds, lra_all, R["downturn_years"]["selected"])
    R["moc"] = quantification.margin_of_conservatism(rds, cfg, rng)
    R["calibration_factors"] = calib.rename_axis("calib_segment").reset_index()

    final_rds = quantification.final_ccf(rds, raw_pred(rds), calib, R["downturn"], R["moc"], cfg)
    R["final_segment"] = segment_final_table(final_rds)
    R["ttest_final"] = validation.calibration_ttest(rds, final_rds["ccf_final"].to_numpy(),
                                                    cfg["validation"]["ttest_alpha"])

    perf_seg = segmentation.assign_segments(performing, cfg)
    perf_seg["facility_type"] = np.where(
        perf_seg["drawn_ref"] >= perf_seg["limit_ref"], "FULLY_DRAWN",
        np.where(perf_seg["drawn_ref"] / perf_seg["limit_ref"] >= cfg["realised_ccf"]["roi_threshold"],
                 "ROI", "STANDARD"))
    final_perf = quantification.final_ccf(perf_seg, raw_pred(perf_seg), calib,
                                          R["downturn"], R["moc"], cfg)
    app = quantification.apply_to_portfolio(perf_seg, final_perf, cfg)
    app.to_csv(P["derived"] / "application_ead.csv", index=False)
    R["application"] = application_summary(app)
    print("[5] quantification and application done")

    # ------------------------------------------- 6. reconciliation extracts
    R["population"].to_csv(P["out_py"] / "recon_population.csv", index=False)
    R["ccf_distribution"].to_csv(P["out_py"] / "recon_ccf_distribution.csv", index=False)
    R["lra_full"].to_csv(P["out_py"] / "recon_lra_by_segment.csv", index=False)
    R["fl_summary_full"].to_csv(P["out_py"] / "recon_fractional_logit.csv", index=False)
    for key in ["dq", "performance", "downturn", "moc", "final_segment", "ttest_oot_calibrated",
                "ttest_final", "stability", "gbm_importance", "application", "yearly"]:
        R[key].to_csv(P["out_py"] / f"{key}.csv", index=False)

    R["environment"] = {"python": platform.python_version(), "numpy": np.__version__,
                        "pandas": pd.__version__}
    import scipy, sklearn
    R["environment"].update({"scipy": scipy.__version__, "scikit-learn": sklearn.__version__})
    (P["out_py"] / "run_metadata.json").write_text(json.dumps(
        {"environment": R["environment"], "selected_model": R["selected_model"],
         "downturn_years": R["downturn_years"], "seed": cfg["seed"]}, indent=2))

    # --------------------------------------------------------- 7. document
    report.write_all(R, P)
    print("[6] documentation written to docs/model_documentation.md")
    return R


def ccf_distribution(rds: pd.DataFrame) -> pd.DataFrame:
    # quantile method "averaged_inverted_cdf" = SAS default PCTLDEF=5, so the
    # numbers reconcile exactly with PROC UNIVARIATE / PROC MEANS
    def q(v, x):
        return float(np.quantile(v, x, method="averaged_inverted_cdf"))

    def f(g):
        v = g["ccf_realised"].to_numpy()
        return pd.Series({"n": len(v), "mean": v.mean(), "p25": q(v, 0.25),
                          "median": q(v, 0.5), "p75": q(v, 0.75),
                          "share_zero": (v == 0).mean(), "share_ge_one": (v >= 1).mean(),
                          "share_negative_raw": g["flag_negative_raw"].mean()})
    parts = [f(g).rename((p, t)) for (p, t), g in rds.groupby(["product", "facility_type"])]
    out = pd.DataFrame(parts)
    out.index = pd.MultiIndex.from_tuples(out.index, names=["product", "facility_type"])
    return out.reset_index()


def segment_final_table(final: pd.DataFrame) -> pd.DataFrame:
    return (final.groupby("calib_segment")
                 .agg(n=("ccf_final", "size"), ccf_model=("ccf_model", "mean"),
                      ccf_calibrated=("ccf_calibrated", "mean"),
                      downturn_addon=("downturn_addon", "mean"), moc=("moc", "mean"),
                      input_floor=("input_floor", "mean"), ccf_final=("ccf_final", "mean"),
                      share_floor_binding=("floor_binding", "mean"))
                 .reset_index())


def application_summary(app: pd.DataFrame) -> pd.DataFrame:
    g = (app.groupby("product")
            .agg(n=("facility_id", "size"), limit=("limit_ref", "sum"), drawn=("drawn_ref", "sum"),
                 mean_ccf_final=("ccf_final", "mean"), share_floor_binding=("floor_binding", "mean"),
                 ead_irb=("ead_irb", "sum"), ead_sa=("ead_sa", "sum"))
            .reset_index())
    tot = pd.DataFrame([{"product": "TOTAL", "n": g["n"].sum(), "limit": g["limit"].sum(),
                         "drawn": g["drawn"].sum(), "mean_ccf_final": app["ccf_final"].mean(),
                         "share_floor_binding": app["floor_binding"].mean(),
                         "ead_irb": g["ead_irb"].sum(), "ead_sa": g["ead_sa"].sum()}])
    g = pd.concat([g, tot], ignore_index=True)
    g["ead_irb_over_sa"] = g["ead_irb"] / g["ead_sa"]
    return g


if __name__ == "__main__":
    main()
