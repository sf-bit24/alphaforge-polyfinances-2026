"""Item 3 - public BNC target portfolios (00-cadre.md: Prudent 80/6/14 ... Actions 0/30/70, % fixed income /
CA equity / global equity) backtested under each persona's limits (capacity and willingness), CAD 1977+ on
CA_GOV_10Y / CA_EQ / US_MKT (US_MKT = stand-in for 'actions mondiales', no ex-US index in the data), annual
rebalancing, 10 bps; and on the real tickers XBB.TO / XIU.TO / SPY, 2021-11 -> 2026-09 (one 59-month window).
Robust BNC = best p10 of the real annualized return among BNC portfolios with breach_rate <= the persona's
tolerance (Robert 0.10, Mateo 0.25, Amira 0.10). Compared, on the same windows, with the persona's robust strategy.
SIMULATION ONLY - BNC portfolios are proxies built from public target weights, not the funds' returns.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
from engine.data import load_lookthrough  # noqa: E402

BNC = ["bnc_prudent", "bnc_conservateur", "bnc_pondere", "bnc_equilibre", "bnc_croissance", "bnc_actions"]
US_SHARE = {"bnc_prudent": .14, "bnc_conservateur": .21, "bnc_pondere": .315, "bnc_equilibre": .42,
            "bnc_croissance": .56, "bnc_actions": .70}
EQ_SHARE = {"bnc_prudent": .20, "bnc_conservateur": .30, "bnc_pondere": .45, "bnc_equilibre": .60,
            "bnc_croissance": .80, "bnc_actions": 1.0}
PERSONA = {
    "robert": {"h": 4, "tol": 0.10, "assigned": ["bnc_conservateur"],
               "variants": {"capacite": "x_bnc_robert_cap", "capacite_oblig_courtes": "x_bnc_robert_cap_court",
                            "volonte": "x_bnc_robert_w05"},
               "robust_ref": ("robert_cad", "eq20_gold10")},
    "mateo": {"h": 10, "tol": 0.25, "assigned": ["bnc_equilibre", "bnc_pondere"],
              "variants": {"capacite": "x_bnc_mateo_cap", "volonte": "x_bnc_mateo_w15"},
              "robust_ref": ("mateo_cad_esg", "risk_parity_iv36")},
    "amira": {"h": 15, "tol": 0.10, "assigned": ["bnc_croissance"],
              "variants": {"capacite": "x_bnc_amira_cap", "sensibilite_0.30": "x_bnc_amira_w30"},
              "robust_ref": ("amira_etf", "Mom_etf_top3")},
}
LIMITS = {"robert": {"capacite": {"max_drawdown": .23, "max_cvar_5": .036}, "volonte": {"max_drawdown": .05, "max_cvar_5": .036}},
          "mateo": {"capacite": {"max_vol": .10, "max_drawdown": .20}, "volonte": {"max_vol": .10, "max_drawdown": .15}},
          "amira": {"capacite": {"max_drawdown": .40}, "sensibilite_0.30": {"max_drawdown": .30}}}
INPUTS: list[str] = []


def breach_types(df, s):
    g = df[(df.strategy == s) & (~df.hindsight)]
    cnt = Counter()
    for b in g.risk_breaches.fillna(""):
        for part in [x.strip() for x in str(b).split(";") if x.strip()]:
            cnt[part.split()[0]] += 1
    return {k: round(v / len(g), 4) for k, v in cnt.items()}


def main():
    out = {}
    lt = load_lookthrough()
    tech = lt["US_IND_BUSEQ"] if "US_IND_BUSEQ" in lt else lt.iloc[:, 0]
    for per, cfg in PERSONA.items():
        out[per] = {}
        for var, pid in cfg["variants"].items():
            for mode in ("non_overlapping", "rolling"):
                path = c.latest(pid, mode, cfg["h"])
                INPUTS.append(path)
                df = c.rows(path)
                rt = c.rtable(df, cfg["tol"])
                b = rt.loc[[s for s in rt.index if s in BNC]]  # keep the robust ordering
                elig = b[b.eligible]
                ref_key = f"{cfg['robust_ref'][0]}|{mode}|{cfg['h']}"
                ref = None
                if ref_key in c.ORIG:
                    rdf = c.rows(c.ORIG[ref_key])
                    INPUTS.append(c.ORIG[ref_key])
                    same_w = sorted(rdf.window.unique()) == sorted(df.window.unique())
                    rs = rdf[(rdf.strategy == cfg["robust_ref"][1]) & (~rdf.hindsight)]
                    ref = {"strategy": cfg["robust_ref"][1], "trace": c.ORIG[ref_key], "same_windows": same_w,
                           "p10": float(rs.score.quantile(.1)), "median": float(rs.score.median()),
                           "maxdd_worst": float(rs.max_drawdown.max())}
                out[per][f"{var}|{mode}"] = {
                    "trace": path,
                    "robust_bnc": elig.index[0] if len(elig) else None,
                    "assigned": cfg["assigned"],
                    "assigned_rank_among_bnc": {a: int(list(b.index).index(a)) + 1 for a in cfg["assigned"]},
                    "table": [{"strategy": s, "p10": round(float(r.score_p10), 5), "median": round(float(r.score_median), 5),
                               "maxdd_worst": round(float(r.max_drawdown_worst), 4), "breach_rate": round(float(r.breach_rate), 4),
                               "breach_types": breach_types(df, s), "p_real_loss": round(float(r.shortfall_prob), 4),
                               "eligible": bool(r.eligible)} for s, r in b.iterrows()],
                    "cash_100": {"p10": float(rt.loc["cash_100", "score_p10"]), "p_real_loss": float(rt.loc["cash_100", "shortfall_prob"])},
                    "persona_robust_same_windows": ref}
    # constraint compliance notes (static BNC weights vs persona hard constraints)
    out["constraints"] = {
        "mateo_equity_band_0.40_0.80": {s: EQ_SHARE[s] for s in BNC if not (0.40 <= EQ_SHARE[s] <= 0.80)},
        "amira_tech_lookthrough_le_0.30": {
            s: {"at_2026_09": round(US_SHARE[s] * float(tech.iloc[-1]), 4),
                "max_1977_2026": round(US_SHARE[s] * float(tech.loc["1977-01":].max()), 4),
                "share_months_over_0.30_since_1977": round(float((US_SHARE[s] * tech.loc["1977-01":] > 0.30).mean()), 4)}
            for s in BNC},
        "lookthrough_busEq_last": [str(tech.index[-1].date()), round(float(tech.iloc[-1]), 4)],
        "note": "BNC portfolios contain no gold, no crypto and no single stocks (00-cadre.md)."}
    # real tickers
    tp = c.latest("x_bnc_tickers", "non_overlapping", 4.9167)
    INPUTS.append(tp)
    td = c.rows(tp)
    real = {}
    for s, g in td[~td.hindsight].groupby("strategy"):
        r = g.iloc[0]
        m = {"window": r.window, "ann_real_return": round(float(r.ann_real_return), 4),
             "ann_return": round(float(r.ann_return), 4) if "ann_return" in r else None,
             "vol": round(float(r.volatility), 4), "maxdd": round(float(r.max_drawdown), 4), "cvar5": round(float(r.cvar_5), 4),
             "worst_12m": round(float(r.worst_12m), 4) if "worst_12m" in r else None}
        m["within_limits"] = {f"{p}|{v}": all(m[{"max_drawdown": "maxdd", "max_vol": "vol", "max_cvar_5": "cvar5"}[k]] <= x
                                              for k, x in L.items())
                              for p, d in LIMITS.items() for v, L in d.items()}
        real[s] = m
    out["tickers_2021_11_2026_09"] = {"trace": tp, "metrics": real}
    for per in PERSONA:
        for k, v in out[per].items():
            print(per, k, "robust BNC:", v["robust_bnc"], "| assigned rank:", v["assigned_rank_among_bnc"],
                  "| ref", None if not v["persona_robust_same_windows"] else
                  (v["persona_robust_same_windows"]["same_windows"], round(v["persona_robust_same_windows"]["p10"], 4)))
            for row in v["table"]:
                print("   ", row["strategy"], row["p10"], row["maxdd_worst"], row["breach_rate"], row["breach_types"], row["eligible"])
    print(out["constraints"])
    for s, m in real.items():
        print(s, m)
    print(c.write("bnc", out, sorted(set(INPUTS)), {"doc": __doc__, "limits": LIMITS}))


if __name__ == "__main__":
    main()
