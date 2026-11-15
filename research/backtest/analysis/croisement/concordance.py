"""Item 4 - concordance persona x asset class: status (regulatory analysis) | robust weight | ORACLE p10-p90.
Class mapping (common.asset_class): CA_EQ / US_MKT(_XEN) = index ETFs (XIU.TO / SPY / ESGV) -> 'fnb_actions';
US_IND_* (Ken French industries, incl. BusEq = tech basket) = stand-in for individual US stocks -> 'actions_us';
bonds -> 'fnb_oblig'; cash (CA_TBILL ~ ZST.TO, a bond ETF in their table) reported separately; GOLD -> 'or'.
Robust weight = mean over windows of the robust strategy's average weights; ORACLE range = p10-p90 across the
rolling windows of the ORACLE weights (hindsight=True, NOT investable).
Also: Amira's Mom_etf_top3 month-by-month holdings (re-simulated with engine.backtest.run_window on one long
window, same profile) to test "diversification réelle"; Mateo ESGV history coverage. SIMULATION ONLY.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
from engine.backtest import ConstraintProvider, run_window  # noqa: E402
from engine.data import load_assets, load_inflation, load_returns  # noqa: E402
from engine.profile import load_profile  # noqa: E402
from engine.strategies import build_strategy  # noqa: E402
from engine.windows import Window  # noqa: E402

CLASSES = ["actions_ca", "actions_us", "fnb_actions", "fnb_oblig", "encaisse", "or", "crypto"]
INPUTS: list[str] = []


def class_profile(path, strategy):
    INPUTS.append(path)
    df = c.rows(path)
    W = c.strategy_class_weights(df, strategy)
    O = c.strategy_class_weights(df, "ORACLE")
    res = {}
    for k in CLASSES + ["actions_total"]:
        w = W[k] if k in W else pd.Series(np.zeros(len(W)))
        o = O[k] if k in O else pd.Series(np.zeros(len(O)))
        res[k] = {"robust_mean": round(float(w.mean()), 4), "robust_min": round(float(w.min()), 4),
                  "robust_max": round(float(w.max()), 4), "oracle_p10": round(c.q(o, .1), 4),
                  "oracle_median": round(c.q(o, .5), 4), "oracle_p90": round(c.q(o, .9), 4),
                  "oracle_share_windows_gt_5pct": round(float((o > 0.05).mean()), 4)}
    A = pd.DataFrame(list(df[df.strategy == strategy].avg_weights)).fillna(0).mean().round(4)
    return {"trace": path, "strategy": strategy, "n_windows": int(len(W)), "classes": res,
            "assets_mean": {k: float(v) for k, v in A.items() if v > 0}}


def holdings(profile_id, strategy, label):
    p = load_profile(profile_id)
    spec = next(s for s in p["strategies"] if s["name"] == strategy)
    R = load_returns(p["universe"], p["period"]["start"], p["period"]["end"], p["currency"], p["fx_fill"])
    infl = load_inflation(p["currency"])
    R = R.loc[: infl.index.max()]
    months = R.index[14:]                      # leave 14 months of history (12 + skip 1 + 1) -> no fallback
    w = Window(months[0], months[-1], len(months))
    prov = ConstraintProvider(p["universe"], p["constraints"])
    res = run_window(R, infl, w, build_strategy(spec), p, prov, None, None)
    W = res["weights"]
    cls = {a: ("tech_busEq" if a == "US_IND_BUSEQ" else "eq_ca" if a == "CA_EQ" else "eq_us" if a == "US_MKT"
               else c.asset_class(a)) for a in W.columns}
    G = W.T.groupby(pd.Series(cls)).sum().T
    for col in ("eq_ca", "eq_us", "tech_busEq", "fnb_oblig", "encaisse", "or"):
        if col not in G:
            G[col] = 0.0
    eq = G.reindex(columns=["eq_ca", "eq_us", "tech_busEq"]).fillna(0).sum(axis=1)
    held = (G > 0.02).sum(axis=1)
    hhi_assets = 1 / (W ** 2).sum(axis=1)
    out = {"profile": profile_id, "strategy": strategy, "period": w.label, "n_months": int(len(W)),
           "fallback_months": int(res["metrics"]["fallback_months"]),
           "mean_weights_by_group": G.mean().round(4).to_dict(),
           "equity_share_distribution": eq.round(2).value_counts(normalize=True).sort_index().round(4).to_dict(),
           "share_months_100pct_equity": round(float((eq > 0.999).mean()), 4),
           "share_months_0_equity": round(float((eq < 0.001).mean()), 4),
           "share_months_single_group": round(float((held == 1).mean()), 4),
           "share_months_ge_2_groups": round(float((held >= 2).mean()), 4),
           "share_months_ge_3_groups": round(float((held >= 3).mean()), 4),
           "share_months_gold_ge_1_3": round(float((G.get("or", 0) > 0.33).mean()), 4),
           "share_months_cash_ge_1_3": round(float((G.get("encaisse", 0) > 0.33).mean()), 4),
           "share_months_bonds_or_cash_ge_2_3": round(float(((G.get("fnb_oblig", 0) + G.get("encaisse", 0)) > 0.66).mean()), 4),
           "share_months_only_one_equity_market_when_100pct_equity":
               round(float(((eq > 0.999) & ((G[["eq_ca", "eq_us", "tech_busEq"]] > 0.02).sum(axis=1) <= 1)).mean()), 4)
               if {"eq_ca", "eq_us", "tech_busEq"} <= set(G.columns) else None,
           "effective_n_assets_median": round(float(hhi_assets.median()), 3),
           "max_single_asset_weight_median": round(float(W.max(axis=1).median()), 4),
           "turnover_ann": round(float(res["metrics"]["turnover_ann"]), 3),
           "y2022_mean_weights": G.loc["2022-01":"2022-12"].mean().round(4).to_dict(),
           "y2022_return": round(float(np.prod(1 + res["returns"].loc["2022-01":"2022-12"].values) - 1), 4),
           "label": label}
    return out


def esgv_cov():
    A = load_assets()
    e = A.loc["ESGV"]
    R = load_returns(["ESGV", "SPY", "US_MKT"], start="2018-10", currency="USD")
    return {"esgv_start": str(e["start"]), "esgv_end": str(e["end"]), "n_months": int(e["n_months"]),
            "complete_10y_windows_possible": int(e["n_months"]) // 120, "complete_8y_windows_possible": int(e["n_months"]) // 96,
            "corr_esgv_spy_monthly": round(float(R["ESGV"].corr(R["SPY"])), 4),
            "corr_esgv_us_mkt_monthly": round(float(R["ESGV"].corr(R["US_MKT"])), 4),
            "ann_diff_esgv_minus_spy": round(float((1 + R["ESGV"]).prod() ** (12 / len(R)) - (1 + R["SPY"]).prod() ** (12 / len(R))), 4),
            "period": [str(R.index.min().date()), str(R.index.max().date())], "notes": str(e.get("notes", ""))}


def main():
    res = {
        "robert": {"cad_rolling_h4": class_profile(c.ORIG["robert_cad|rolling|4"], "eq20_gold10"),
                   "usd_rolling_h4": class_profile(c.ORIG["robert_long_usd|rolling|4"], "eq20_2y")},
        "mateo": {e: class_profile(c.ORIG[f"mateo_{e}_esg|rolling|10"], "risk_parity_iv36")
                  for e in ("usd_long", "usd_gold", "cad")},
        "amira": {"etf_cad_rolling_h15": class_profile(c.ORIG["amira_etf|rolling|15"], "Mom_etf_top3"),
                  "etf_usd_rolling_h15": class_profile(c.ORIG["amira_etf_long_usd|rolling|15"], "Mom_etf_top3")},
    }
    # same under the willingness limits (x_ reruns), for the oracle range
    for key, (pid, strat, h) in {"robert_cad_w05": ("x_robert_cad_w05", "eq20_gold10", 4),
                                 "mateo_cad_w15": ("x_mateo_cad_esg_w15", "risk_parity_iv36", 10),
                                 "amira_etf_w30": ("x_amira_etf_w30", "Mom_etf_top3", 15)}.items():
        try:
            res.setdefault("willingness_runs", {})[key] = class_profile(c.latest(pid, "rolling", h), strat)
        except FileNotFoundError:
            pass
    res["amira_holdings"] = {
        "cad_Mom_etf_top3": holdings("amira_etf", "Mom_etf_top3", "CAD 1977+, ETF universe"),
        "usd_Mom_etf_top3": holdings("amira_etf_long_usd", "Mom_etf_top3", "USD 1926+, ETF universe"),
        "cad_Trend10_E80": holdings("amira_etf", "Trend10_E80", "CAD 1977+, alternative"),
        "cad_E80_us50_g10_t0": holdings("amira_etf", "E80_us50_g10_t0", "CAD 1977+, static reference"),
        "cad_Mom_etf_top3_core50": holdings("amira_etf", "Mom_etf_top3_core50", "CAD 1977+, momentum with 50 % core"),
        "usd_Trend10_E80": holdings("amira_etf_long_usd", "Trend10_E80", "USD 1926+, alternative")}
    res["mateo_esgv"] = esgv_cov()
    for per in ("robert", "mateo", "amira"):
        for k, v in res[per].items():
            print(per, k, {cl: (d["robust_mean"], d["oracle_p10"], d["oracle_p90"]) for cl, d in v["classes"].items()})
    for k, v in res.get("willingness_runs", {}).items():
        print("W", k, {cl: (d["robust_mean"], d["oracle_p10"], d["oracle_p90"]) for cl, d in v["classes"].items()})
    for k, v in res["amira_holdings"].items():
        print(k, {kk: vv for kk, vv in v.items() if kk not in ("profile",)})
    print(res["mateo_esgv"])
    print(c.write("concordance", res, sorted(set(INPUTS)) + ["data/processed/assets.csv"], {"doc": __doc__}))


if __name__ == "__main__":
    main()
