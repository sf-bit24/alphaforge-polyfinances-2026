"""B2 - willingness (AMF Q10) vs capacity (derived in the persona reports): rerun of the robust selection under the
lowest limit (31-103CP). Same universes / strategies / selection rules as the retained version of each report:
  Robert : per run, engine rule (best p10, breach_rate <= 0.10)                          [reports/robert.md 5.2]
  Mateo  : cross-era (usd_long, usd_gold, cad ; ESG ; rolling 10y): breach <= 0.25 in EVERY era, max worst p10
                                                                                          [reports/mateo.md 4]
  Amira  : per run best p10 with breach <= 0.10, then minimax regret over the 6 ETF runs  [reports/amira.md 4]
Also checks that non-oracle rows are identical between the original and the rerun traces (limits only change the
breach count and the oracle penalty). SIMULATION ONLY.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

INPUTS: list[str] = []


def rd(path):
    INPUTS.append(path)
    return c.rows(path)


def same_rows(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    ka = a[~a.hindsight].set_index(["window", "strategy"])["score"]
    kb = b[~b.hindsight].set_index(["window", "strategy"])["score"]
    j = ka.to_frame("a").join(kb.to_frame("b"), how="inner")
    d = (j.a - j.b).abs()
    return {"n_common": int(len(j)), "max_abs_diff": float(d.max()) if len(d) else None,
            "strategies_with_diff": sorted({s for (w, s), x in d.items() if x > 1e-12})}


def summarize(df: pd.DataFrame, strat: str, rt: pd.DataFrame) -> dict:
    W = c.strategy_class_weights(df, strat)
    r = rt.loc[strat]
    return {"strategy": strat, "p10": float(r["score_p10"]), "median": float(r["score_median"]),
            "worst": float(r["score_worst"]), "maxdd_worst": float(r["max_drawdown_worst"]),
            "breach_rate": float(r["breach_rate"]), "p_real_loss": float(r["shortfall_prob"]),
            "equity_avg": float(W["actions_total"].mean()), "gold_avg": float(W.get("or", pd.Series([0])).mean()),
            "cash_avg": float(W.get("encaisse", pd.Series([0])).mean())}


def oracle_equity(df: pd.DataFrame) -> dict:
    W = c.strategy_class_weights(df, "ORACLE")
    o = df[df.strategy == "ORACLE"]
    return {"equity_p10": c.q(W["actions_total"], .1), "equity_median": c.q(W["actions_total"], .5),
            "equity_p90": c.q(W["actions_total"], .9),
            "oracle_score_median": float(o.score.median()), "oracle_risk_limits_met_share":
            float(o["risk_limits_met"].astype(float).mean()) if "risk_limits_met" in o else None}


def per_run(df, max_breach):
    rt = c.rtable(df, max_breach)
    elig = rt[rt.eligible]
    top = [summarize(df, s, rt) for s in elig.index[:3]]
    return {"n_strategies": int(len(rt)), "n_eligible": int(len(elig)), "eligible": list(elig.index),
            "robust": top[0] if top else None, "next": top[1:], "oracle": oracle_equity(df),
            "table": rt[["score_p10", "score_median", "max_drawdown_worst", "breach_rate", "shortfall_prob",
                         "eligible"]].round(5).reset_index().to_dict(orient="records")}


def robert():
    out = {}
    variants = {"capacite_0.23": None, "volonte_0.05": "x_{}_w05", "amf1_q3_0.00": "x_{}_amf1"}
    for prof in ("robert_cad", "robert_long_usd"):
        for mode in ("non_overlapping", "rolling"):
            orig = rd(c.ORIG[f"{prof}|{mode}|4"])
            for v, pat in variants.items():
                if pat is None:
                    df, path = orig, c.ORIG[f"{prof}|{mode}|4"]
                else:
                    try:
                        path = c.latest(pat.format(prof), mode, 4)
                    except FileNotFoundError:
                        continue
                    df = rd(path)
                res = per_run(df, 0.10)
                res["trace"] = path
                if pat is not None:
                    res["check_vs_original"] = same_rows(orig, df)
                out[f"{prof}|{mode}|{v}"] = res
    return out


def mateo():
    eras = ("usd_long", "usd_gold", "cad")
    out = {}
    for v, pat in {"capacite_0.20": None, "volonte_0.15": "x_mateo_{}_esg_w15"}.items():
        recs, per_era = [], {}
        for e in eras:
            op = c.ORIG[f"mateo_{e}_esg|rolling|10"]
            orig = rd(op)
            path = op if pat is None else c.latest(pat.format(e), "rolling", 10)
            df = orig if pat is None else rd(path)
            rt = c.rtable(df, None)
            for s, r in rt.iterrows():
                W = c.strategy_class_weights(df, s)
                recs.append({"era": e, "strategy": s, "p10": r["score_p10"], "breach": r["breach_rate"],
                             "maxdd_worst": r["max_drawdown_worst"], "p_real_loss": r["shortfall_prob"],
                             "equity_avg": W["actions_total"].mean(), "gold_avg": W.get("or", pd.Series([0])).mean()})
            per_era[e] = {"trace": path, "cad_like_rule_choice_breach_le_0.25": per_run(df, 0.25)["robust"],
                          "oracle": oracle_equity(df)}
            if pat is not None:
                per_era[e]["check_vs_original"] = same_rows(orig, df)
        D = pd.DataFrame(recs)
        agg = D.groupby("strategy").agg(min_p10=("p10", "min"), max_breach=("breach", "max"),
                                        worst_dd=("maxdd_worst", "max"), max_p_real_loss=("p_real_loss", "max"),
                                        equity_avg=("equity_avg", "mean"), gold_avg=("gold_avg", "mean"))
        agg["eligible"] = agg.max_breach <= 0.25
        agg = agg.sort_values(["eligible", "min_p10"], ascending=False)
        piv = D.pivot_table(index="strategy", columns="era", values="p10")
        brk = D.pivot_table(index="strategy", columns="era", values="breach")
        out[v] = {"retained": agg.index[0] if agg.eligible.iloc[0] else None,
                  "n_eligible_all_eras": int(agg.eligible.sum()),
                  "agg": agg.round(5).reset_index().to_dict(orient="records"),
                  "p10_by_era": piv.round(5).reset_index().to_dict(orient="records"),
                  "breach_by_era": brk.round(4).reset_index().to_dict(orient="records"), "per_era": per_era}
    return out


def amira():
    runs = [(p, m, h) for p in ("amira_etf", "amira_etf_long_usd")
            for (m, h) in (("non_overlapping", 15), ("rolling", 15), ("rolling", 20))]
    out = {}
    for v in ("original_0.40_ancien_moteur", "controle_0.40_moteur_actuel", "sensibilite_0.30"):
        P, E, per = {}, {}, {}
        for p, m, h in runs:
            key = f"{p}|{m}|h{h}"
            op = c.ORIG[f"{p}|{m}|{h}"]
            orig = rd(op)
            if v.startswith("original"):
                path, df = op, orig
            elif v.startswith("controle"):
                path = c.latest(p, m, h)
                df = rd(path)
            else:
                path = c.latest(f"x_{p}_w30", m, h)
                df = rd(path)
            rt = c.rtable(df, 0.10)
            P[key], E[key] = rt["score_p10"], rt["eligible"]
            pr = per_run(df, 0.10)
            pr["trace"] = path
            pr["mom_etf_top3"] = summarize(df, "Mom_etf_top3", rt) | {"eligible": bool(rt.loc["Mom_etf_top3", "eligible"])}
            if path != op:
                pr["check_vs_original"] = same_rows(orig, df)
            per[key] = pr
        Pm, Em = pd.DataFrame(P), pd.DataFrame(E).fillna(False).astype(bool)
        best = Pm.where(Em).max()
        regret = best - Pm
        ok = [s for s in Pm.dropna().index if Em.loc[s].all()]
        tab = pd.DataFrame({"worst_regret": regret.loc[ok].max(axis=1), "mean_regret": regret.loc[ok].mean(axis=1),
                            "min_p10": Pm.loc[ok].min(axis=1)}).sort_values("worst_regret")
        out[v] = {"retained_minimax_regret": tab.index[0] if len(tab) else None,
                  "n_eligible_all_runs": len(ok), "table": tab.round(5).reset_index().to_dict(orient="records"),
                  "best_eligible_p10_per_run": best.round(5).to_dict(), "per_run": per}
    return out


def main():
    res = {"robert": robert(), "mateo": mateo(), "amira": amira()}
    # console summary
    for k, v in res["robert"].items():
        r = v["robust"]
        print("ROBERT", k, r["strategy"], round(r["p10"], 4), "eq", round(r["equity_avg"], 3), "P(loss)",
              round(r["p_real_loss"], 3), "n_elig", v["n_eligible"], v.get("check_vs_original", {}).get("max_abs_diff"))
    for k, v in res["mateo"].items():
        print("MATEO", k, v["retained"], v["n_eligible_all_eras"], v["agg"][:4])
    for k, v in res["amira"].items():
        print("AMIRA", k, v["retained_minimax_regret"], v["table"][:3])
    print(c.write("will_vs_cap", res, sorted(set(INPUTS)),
                  {"rules": __doc__, "willingness": {"robert_Q10": 0.05, "robert_Q3_literal_AMF1": 0.0,
                                                      "mateo_Q10": 0.15, "amira_Q10": "> 0.30 (does not bind)",
                                                      "amira_sensitivity_AMF4_palier": 0.30},
                   "capacity": {"robert_H4": [0.23, "CVaR5 0.036"], "mateo_H10": [0.20, "vol 0.10"],
                                "amira_H15": 0.40}}))


if __name__ == "__main__":
    main()
