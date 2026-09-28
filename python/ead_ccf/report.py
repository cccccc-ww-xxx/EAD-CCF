"""Write figures and the model development documentation (markdown).

Every number in docs/model_documentation.md comes from the pipeline results
dictionary `R` - nothing is typed in by hand (CLAUDE.md section 4).
"""

from __future__ import annotations

from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def md_table(df: pd.DataFrame, fmt: dict | None = None, default: str = "{:.4f}") -> str:
    fmt = fmt or {}
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |",
             "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, (float, np.floating)):
                cells.append("" if pd.isna(v) else fmt.get(c, default).format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _style(ax, title, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=12, pad=10)
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel(ylabel, color=INK2)
    ax.tick_params(colors=INK2)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


# ----------------------------------------------------------------------------
# figures
# ----------------------------------------------------------------------------
def fig_distribution(rds, path):
    v = rds.loc[rds["facility_type"] == "STANDARD", "ccf_realised"].clip(upper=1.5)
    fig, ax = plt.subplots(figsize=(7, 3.6), facecolor=SURFACE)
    ax.hist(v, bins=np.linspace(0, 1.5, 31), color=BLUE, edgecolor=SURFACE, linewidth=2)
    _style(ax, "Realised CCF, standard facilities (values above 150% shown at 150%)",
           "Realised CCF", "Number of facilities")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_yearly(yearly, dt_years, lra_value, path):
    y = yearly[yearly["product"] == "ALL"]
    fig, ax = plt.subplots(figsize=(7, 3.6), facecolor=SURFACE)
    for yr in dt_years:
        ax.axvspan(yr - 0.5, yr + 0.5, color=GRID, zorder=0)
    ax.plot(y["default_year"], y["mean_ccf"], color=BLUE, linewidth=2, marker="o", markersize=5,
            label="Yearly average realised CCF")
    ax.axhline(lra_value, color=ORANGE, linewidth=2, linestyle="--", label="Long-run average")
    _style(ax, "Average realised CCF by default year (shaded = downturn years)",
           "Default year", "Realised CCF")
    ax.legend(frameon=False, labelcolor=INK2, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_deciles(dec, path):
    fig, ax = plt.subplots(figsize=(7, 3.6), facecolor=SURFACE)
    x = dec["bin"].to_numpy()
    ax.bar(x - 0.2, dec["mean_predicted"], width=0.38, color=BLUE, label="Predicted")
    ax.bar(x + 0.2, dec["mean_realised"], width=0.38, color=ORANGE, label="Realised")
    _style(ax, "Out-of-time calibration by prediction decile", "Prediction decile (1 = lowest)",
           "Average CCF")
    ax.set_xticks(x)
    ax.legend(frameon=False, labelcolor=INK2, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ----------------------------------------------------------------------------
# document
# ----------------------------------------------------------------------------
EXPECTED_SIGN = {"utilisation": -1, "grade": 1, "arrears_6m": 1}


def decision_status_table(P: dict) -> str:
    """Read decision IDs, titles and status lines from the decision log."""
    import re
    text = (P["docs"] / "decisions" / "decision_log.md").read_text(encoding="utf-8")
    rows = re.findall(r"^## (D\d{3}) — (.+?)\n\*\*Status: (.+?)\*\*", text, flags=re.M)
    lines = ["| ID | Topic | Status |", "|---|---|---|"]
    lines += [f"| {i} | {t} | {s} |" for i, t, s in rows]
    return "\n".join(lines)


def coef_commentary(fl: pd.DataFrame, alpha: float = 0.05) -> str:
    """Generated (not hand-written) commentary on the fractional-logit estimates."""
    c = fl.set_index("variable")
    lines = []
    for v, s in EXPECTED_SIGN.items():
        got = np.sign(c.loc[v, "coefficient"])
        ok = "as expected" if got == s else "**CONTRARY TO EXPECTATION — investigate**"
        lines.append(f"- `{v}`: expected sign {'+' if s > 0 else '−'}, estimated "
                     f"{'+' if got > 0 else '−'} ({ok}), p = {c.loc[v, 'p_value']:.4f}")
    insig = [v for v in c.index if v != "intercept" and c.loc[v, "p_value"] >= alpha]
    lines.append(f"- Not significant at {alpha:.0%}: {', '.join(insig) if insig else 'none'}. "
                 "Candidates for removal at checkpoint C. (In the synthetic data-generating "
                 "process, `log_limit` and `log_mob` have no true effect, so their "
                 "non-significance is a check that the estimation recovers the truth.)")
    return "\n".join(lines)


def write_all(R: dict, P: dict) -> None:
    cfg = R["config"]
    fig_distribution(R["rds"], P["figures"] / "fig1_ccf_distribution.png")
    lra_port = R["rds"]["ccf_realised"].mean()
    fig_yearly(R["yearly"], R["downturn_years"]["selected"], lra_port,
               P["figures"] / "fig2_yearly_ccf.png")
    fig_deciles(R["deciles_oot"], P["figures"] / "fig3_oot_deciles.png")

    rds = R["rds"]
    n = len(rds)
    ft = rds["facility_type"].value_counts()
    perf = R["performance"]
    sel = R["selected_model"]
    t_oot = R["ttest_oot_calibrated"]
    t_fin = R["ttest_final"]
    app = R["application"]
    tot = app[app["product"] == "TOTAL"].iloc[0]
    dty = R["downturn_years"]
    fl = R["fl_summary_full"]

    def pm(model, sample, col):
        return perf[(perf["model"] == model) & (perf["sample"] == sample)][col].iloc[0]

    doc = f"""# EAD-CCF Model — Development Documentation (PROTOTYPE)

> **Status: PROTOTYPE ON SYNTHETIC DATA — NOT AN APPROVED MODEL.**
> All data in this document is synthetic. The document shows the structure,
> tests and traceability expected for internal validation and ECB review.
> Every number is generated by `python/run_pipeline.py`; nothing is typed by hand.

| Item | Value |
|---|---|
| Model | Own-estimate CCF for undrawn revolving commitments (A-IRB) |
| Portfolio | BNP Paribas Fortis revolving portfolios (prototype scope: 4 synthetic products) |
| Model owner | *to be filled* |
| Developer | *to be filled* |
| Document generated | {date.today().isoformat()} |
| Code version | see git commit hash of this file |
| Random seed | {cfg['seed']} |

---

## 1. Executive summary

- Reference data set: **{n:,} defaulted facilities**, default years {cfg['synthetic']['first_default_year']}–{cfg['synthetic']['last_default_year']}; development sample {R['n_dev']:,}, out-of-time sample (default year ≥ {cfg['split']['oot_first_year']}) {R['n_oot']:,}.
- Realised CCF follows the CRR3 facility-level definition with a 12-month fixed horizon. {ft.get('ROI', 0):,} facilities lie in the region of instability and {ft.get('FULLY_DRAWN', 0):,} were fully drawn at reference date; both use a stabilised denominator (decision D003).
- Selected risk-differentiation model: **{sel}** (method ladder, section 5). Out-of-time MAE {pm(sel,'OOT','MAE'):.4f} vs benchmark {pm('benchmark','OOT','MAE'):.4f}; Spearman {pm(sel,'OOT','spearman'):.3f} vs {pm('benchmark','OOT','spearman'):.3f}.
- Downturn years: data-driven {dty['data_driven']}, macro candidates {dty['macro_candidates']}, selected {dty['selected']}.
- Final CCFs include calibration to the long-run average, an additive downturn add-on, MoC (categories A+B+C) and the CRR3 input floor (50% × SA CCF).
- On the synthetic performing portfolio, IRB EAD is **{tot['ead_irb_over_sa']:.1%}** of standardised EAD; the input floor binds for {tot['share_floor_binding']:.1%} of facilities.
- Out-of-time calibration t-test: {int((t_oot['result']=='UNDERESTIMATION').sum())} of {len(t_oot)} segments show significant underestimation before downturn/MoC; after final adjustments: {int((t_fin['result']=='UNDERESTIMATION').sum())} of {len(t_fin)}.

## 2. Scope and regulatory framework

| Topic | Reference |
|---|---|
| Scope of own CCF estimates (revolving commitments), input floor | CRR (575/2013) as amended by CRR3 (2024/1623), Art. 166 — *verify paragraph numbers* |
| Realised CCF definition | CRR3 Art. 4(1)(56) |
| Own CCF estimation requirements | CRR Art. 179, Art. 182 |
| Detailed CCF methodology | EBA draft Guidelines on CCF estimation, EBA/CP/2025/10 (consultation, July 2025) — **check whether final Guidelines are published** |
| MoC framework, general estimation principles | EBA/GL/2017/16 |
| Assessment methodology | Commission Delegated Regulation (EU) 2022/439 |
| ECB supervisory expectations | ECB Guide to internal models release 4.1 (June 2026) withdrew CCF guidance pending EBA Guidelines |

## 3. Data

### 3.1 Reference data set
One record per defaulted facility with values at the reference date (default date − {cfg['realised_ccf']['horizon_months']} months) and at default. Source: `data/raw/defaults.csv` (synthetic, `python/ead_ccf/synthetic_data.py`).

### 3.2 Data quality checks
{md_table(R['dq'], {'pct_fail': '{:.3f}'})}

Missing ratings are imputed with the development-sample median plus a missing-indicator variable, and trigger MoC category A (section 6.4).

### 3.3 Population by product and facility type
{md_table(R['population'], {'sum_limit_ref': '{:,.0f}', 'sum_drawn_ref': '{:,.0f}', 'sum_ead_default': '{:,.0f}'})}

## 4. Realised CCF

**Definition.** realised CCF = (drawn at default − drawn at reference) / (limit at reference − drawn at reference).

| Facility type | Rule | Treatment (decision D003) |
|---|---|---|
| STANDARD | utilisation < {cfg['realised_ccf']['roi_threshold']:.0%} | raw definition |
| ROI | {cfg['realised_ccf']['roi_threshold']:.0%} ≤ utilisation < 100% | denominator = max(undrawn, {1-cfg['realised_ccf']['roi_threshold']:.0%} × limit) |
| FULLY_DRAWN | undrawn = 0 | denominator = {1-cfg['realised_ccf']['roi_threshold']:.0%} × limit |

Floor: negative CCFs (repayments) are kept for STANDARD facilities and floored at {cfg['realised_ccf']['floor_near_full']:.0%} for ROI / FULLY_DRAWN facilities; cap: {'none — CCFs above 100% are kept' if cfg['realised_ccf']['cap'] is None else cfg['realised_ccf']['cap']} (decision D002). For the fractional-logit fit only, the target is restricted to [0, {cfg['realised_ccf']['model_cap']:.0%}]; calibration to the long-run average uses the unrestricted values, so the restriction does not change the final level.

{md_table(R['ccf_distribution'], {'n': '{:.0f}'})}

![Realised CCF distribution](../outputs/figures/fig1_ccf_distribution.png)

The distribution is bimodal with mass at 0 and at 1, as reported by Tong et al. (2016); normal-error models are therefore not used.

## 5. Risk differentiation

### 5.1 Method ladder
1. Benchmark — long-run average per calibration segment (section 6.0, decision D004).
2. Fractional logit (Papke & Wooldridge, 1996) with robust standard errors — replaces the benchmark only if it improves **both** out-of-time MAE and Spearman correlation.
3. Direct-EAD alternatives (Taplin et al., 2007; Tong et al., 2016) — *not yet implemented, open issue*.
4. Gradient boosting with monotonic constraints — challenger for driver discovery only.

Candidate drivers are restricted to information available at the reference date. `limit_cut_flag` is excluded because the limit cut happens after the reference date (decision D006).

### 5.2 Performance on standard facilities (models calibrated to segment LRA on development sample)
{md_table(perf, {'n': '{:.0f}'})}

**Selected model: {sel}.**

### 5.3 Fractional logit — final estimates (full sample)
{md_table(fl)}

{coef_commentary(fl)}

### 5.4 Gradient-boosting challenger — permutation importance (OOT)
{md_table(R['gbm_importance'])}

Top-3 drivers by permutation importance: {', '.join(R['gbm_importance']['variable'].head(3))}. The challenger is used to check that no important driver or non-linearity is missing from the fractional logit; it is not proposed for production.

## 6. Risk quantification

### 6.0 Segmentation and segmentation tests (checkpoint C, decision D004)
Calibration segments: each utilisation band is split as configured in `segmentation.split_by` ({', '.join(f'{k}: {v}' for k, v in cfg['segmentation']['split_by'].items())}). Splits are kept only where the tests below show a significant difference; the ≥ 95% band is separate for methodological reasons (stabilised denominator, D003). Product remains a driver inside the fractional logit.

**Chosen segments — size**
{md_table(R['seg_counts'], {'n_defaults': '{:.0f}', 'min_per_year': '{:.0f}', 'mean_per_year': '{:.1f}'})}

**Chosen segments — pairwise Welch t-tests (heterogeneity)**
{md_table(R['seg_chosen'])}

**Candidate splits — utilisation bands within product, products within band**
{md_table(R['seg_hetero'], {'n_a': '{:.0f}', 'n_b': '{:.0f}'})}

**Stability of the utilisation ordering by year** (share of default years in which the lower band has the higher average CCF)
{md_table(R['seg_order'], {'n_years': '{:.0f}', 'share_years_order_holds': '{:.0%}'})}

**Rank correlation of yearly segment averages with the full-period ranking**
{md_table(R['seg_rank'], {'default_year': '{:.0f}', 'n_segments': '{:.0f}', 'min_defaults_in_segment': '{:.0f}'})}

### 6.1 Long-run average by segment (both weighting methods)
{md_table(R['lra_full'], {'n_facilities': '{:.0f}', 'n_years': '{:.0f}'})}

Selected method: **{cfg['lra']['method']}** (decision D005). The column `difference` shows the impact of the choice.

![Yearly CCF](../outputs/figures/fig2_yearly_ccf.png)

### 6.2 Calibration factors
{md_table(R['calibration_factors'])}

### 6.3 Downturn
Downturn years: data-driven (top {cfg['downturn']['n_worst_years']} years by average realised CCF) = {dty['data_driven']}; macro candidates = {dty['macro_candidates']}; selected (union) = {dty['selected']}.

{md_table(R['downturn'], {'n_downturn_obs': '{:.0f}', 'fallback_portfolio_ratio': '{:.0f}'})}

### 6.4 Margin of conservatism
{md_table(R['moc'], {'n': '{:.0f}'})}

A = data deficiencies (missing ratings), B = methodological choice (cap at 100% vs none), C = general estimation error (bootstrap {cfg['moc']['bootstrap_samples']} resamples, {cfg['moc']['confidence']:.0%} quantile). **These are simple proxies for the prototype and must be replaced by the approved MoC framework.**

### 6.5 Final CCF by segment
{md_table(R['final_segment'], {'n': '{:.0f}'})}

## 7. Performance testing

### 7.1 Out-of-time calibration test (calibrated model, before downturn and MoC)
{md_table(t_oot, {'n': '{:.0f}'})}

### 7.2 Calibration test of final (conservative) CCFs, full sample
{md_table(t_fin, {'n': '{:.0f}'})}

### 7.3 Decile calibration (out-of-time)
![OOT deciles](../outputs/figures/fig3_oot_deciles.png)

{md_table(R['deciles_oot'], {'n': '{:.0f}', 'bin': '{:.0f}'})}

### 7.4 Stability of drivers (PSI, development vs out-of-time)
{md_table(R['stability'])}

## 8. Application to the performing portfolio

{md_table(app, {'n': '{:,.0f}', 'limit': '{:,.0f}', 'drawn': '{:,.0f}', 'ead_irb': '{:,.0f}', 'ead_sa': '{:,.0f}'})}

## 9. Human judgement and decisions
All methodological choices are logged in `docs/decisions/decision_log.md` with the options considered, regulatory references, the evidence and the human decision. Current status:

{decision_status_table(P)}

## 10. Limitations and open issues
1. Synthetic data only — results say nothing about the real portfolio.
2. Draft EBA Guidelines used as blueprint; final Guidelines may change requirements (e.g. LRA weighting, RoI treatment, fixed-CCF options).
3. Realised CCF computed per facility; related-contract/umbrella treatment and borrower-level aggregation of restructured facilities not yet assessed against Art. 4(1)(56).
4. Additional drawings after default and in-default CCF not implemented.
5. Direct-EAD challengers (rung 3) not implemented.
6. MoC quantification uses simple proxies (D009 interim) until the bank's MoC framework is implemented.
7. Negative realised CCFs are kept for standard facilities (D002); this lowers their long-run average and needs a documented justification (causes of repayments, sensitivity with a 0 floor).
8. SA CCF buckets per product to be verified.
9. SAS implementation written but not yet run in the bank environment; reconciliation not yet performed.

## 11. Reproducibility

| Step | Python | SAS |
|---|---|---|
| Configuration | `config/config.yaml` | `sas/00_config.sas` |
| Synthetic data | `python/ead_ccf/synthetic_data.py` | reads `data/raw/*.csv` |
| Realised CCF, DQ | `python/ead_ccf/realised_ccf.py` | `sas/02_realised_ccf.sas` |
| Segmentation, LRA | `python/ead_ccf/segmentation.py`, `lra.py` | `sas/03_lra.sas` |
| Fractional logit | `python/ead_ccf/models.py` | `sas/04_fractional_logit.sas` |
| Downturn, MoC, floor | `python/ead_ccf/quantification.py` | `sas/05_quantification.sas` |
| Performance tests | `python/ead_ccf/validation.py` | `sas/06_validation.sas` |
| Reconciliation | `python/reconcile.py` | `sas/07_export_recon.sas` |

Environment: {', '.join(f'{k} {v}' for k, v in R['environment'].items())}.

## Annex A — Literature
- Papke, L.E. & Wooldridge, J.M. (1996). Econometric methods for fractional response variables. *Journal of Applied Econometrics*.
- Taplin, R., To, H.M. & Hee, J. (2007). Modeling exposure at default, credit conversion factors and the Basel II Accord. *Journal of Credit Risk*, 3, 75–84.
- Tong, E.N.C., Mues, C., Brown, I. & Thomas, L.C. (2016). Exposure at default models with and without the credit conversion factor. *European Journal of Operational Research*, 252(3), 910–920.
- Gürtler, M., Hibbeln, M.T. & Usselmann, P. (2018). Exposure at default modeling — a theoretical and empirical assessment of estimation approaches and parameter choice. *Journal of Banking & Finance*.
- Wattanawongwan, S., Mues, C., Okhrati, R., Choudhry, T. & So, M.C. (2023). A mixture model for credit card exposure at default using the GAMLSS framework. *International Journal of Forecasting*.
"""
    (P["docs"] / "model_documentation.md").write_text(doc, encoding="utf-8")
