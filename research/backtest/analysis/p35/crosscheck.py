"""Persona 35 - cross-check with the regulatory analysis (B1-B4, B6 inputs) from the latest traces.

- B2: robust selection re-computed with the willingness limit (0.15), the capacity limit (L_cap) and their min,
      using engine.validation.robust_table on the same window rows (breach recomputed = maxDD > limit).
- B3: class-level weights: robust strategy (mean of avg_weights over windows) and ORACLE p10-p90 per class.
- oracle gap in final real wealth units (walk-forward choice vs ORACLE), robust strategy USD share.
Outputs results/p35_analysis/crosscheck.json. SIMULATION ONLY."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

import common as C
from engine.data import load_assets
from engine.validation import robust_table, walk_forward

CAT = load_assets()
CLASS = {"actions_CA_titres": [], "actions_US_titres_proxy_secteurs": ["US_IND_NODUR", "US_IND_HLTH", "PG", "JNJ"],
         "FNB_actions": ["CA_EQ", "US_MKT", "XIU.TO", "SPY"],
         "FNB_oblig_et_encaisse": ["CA_GOV_10Y", "UST_5Y", "UST_10Y", "UST_2Y", "CA_TBILL", "UST_TBILL", "XBB.TO",
                                   "AGG", "ZST.TO"],
         "or": ["GOLD", "GLD"], "crypto": ["BTC-USD", "ETH-USD"]}


def cls(w: dict) -> dict:
    return {c: float(sum(w.get(a, 0) for a in L)) for c, L in CLASS.items()}


def usd(w: dict) -> float:
    return float(sum(v for k, v in w.items() if CAT.at[k, "currency"] == "USD"))


def block(trace: Path, chosen: str | None = None) -> dict:
    t = json.loads(trace.read_text())
    d = pd.DataFrame(t["results"])
    chosen = chosen or t["summary"]["robust_choice"]
    ex = d[(~d.hindsight) & (d.strategy == chosen)]
    W = pd.DataFrame(list(ex.avg_weights)).fillna(0)
    wmean = W.mean().to_dict()
    O = pd.DataFrame([o["weights"] for o in t["oracle"]]).fillna(0) if t["oracle"] else pd.DataFrame()
    oc = pd.DataFrame([cls(r) for r in O.to_dict(orient="records")]) if len(O) else pd.DataFrame()
    ou = pd.Series([usd(r) for r in O.to_dict(orient="records")]) if len(O) else pd.Series(dtype=float)
    res = {"trace": str(trace), "strategy": chosen, "mean_weights": wmean, "class_weights": cls(wmean),
           "usd_share": usd(wmean), "weights_range_over_windows": {a: [float(W[a].min()), float(W[a].max())] for a in W},
           "oracle_class_p10_p90": {c: [float(oc[c].quantile(.1)), float(oc[c].quantile(.9))] for c in oc} if len(oc) else {},
           "oracle_usd_p10_p90": [float(ou.quantile(.1)), float(ou.quantile(.9))] if len(ou) else None}
    if len(O):
        orc = d[d.hindsight].set_index("window")["final_real_wealth"]
        mine = ex.set_index("window")["final_real_wealth"]
        res["oracle_gap_final_real_wealth_mean"] = float((orc - mine).mean())
        res["oracle_gap_final_real_wealth_median"] = float((orc - mine).median())
        wf = pd.DataFrame(t["walk_forward"])
        if len(wf):
            exall = d[~d.hindsight].set_index(["window", "strategy"])["final_real_wealth"]
            ch = np.array([exall[(w, s)] for w, s in zip(wf.window, wf.chosen)])
            res["walk_forward_gap_final_real_wealth_mean"] = float((orc.reindex(wf.window).values - ch).mean())
            res["walk_forward_final_real_wealth_p10"] = float(np.quantile(ch, .1))
    return res


def reselect(trace: Path, limit: float) -> dict:
    t = json.loads(trace.read_text())
    d = pd.DataFrame(t["results"])
    d["n_breaches"] = (d["max_drawdown"] > limit).astype(int)
    r = robust_table(d, 0.10, 0.10)
    top = r.head(5)
    return {"limit": limit, "robust_choice": r.index[0],
            "top5": {s: {"score_p10": float(x.score_p10), "breach_rate": float(x.breach_rate),
                         "max_drawdown_worst": float(x.max_drawdown_worst)} for s, x in top.iterrows()},
            "bnc_eligible": [s for s in r.index if s.startswith("bnc") and bool(r.at[s, "eligible"])],
            "best_bnc": next((s for s in r.index if s.startswith("bnc") and bool(r.at[s, "eligible"])), None)}


if __name__ == "__main__":
    D = json.loads((C.OUT / "derive_b.json").read_text())["results"]
    tr15 = C.latest("p35_B_cad", "*_rolling_h15.json")
    tr20 = C.latest("p35_B_cad", "*_rolling_h20.json")
    trA = C.latest("p35_A_usd", "*_rolling_h0.5.json")
    trT = C.latest("p35_B_tickers", "*.json")
    out = {"B15_robust": block(tr15), "B15_e40_u50_gold15": block(tr15, "e40_u50_gold15"),
           "B15_bnc_pondere_usdfi": block(tr15, "bnc_pondere_usdfi"), "B20_robust": block(tr20),
           "A_robust": block(trA), "tickers_oracle": block(trT, "e40_u50_gold15")}
    out["B2_reselect"] = {}
    for name, tr in (("B15", tr15), ("B20", tr20)):
        out["B2_reselect"][name] = {"willingness_0.15": reselect(tr, D["L_will"]),
                                    "capacity_Lcap": reselect(tr, D["L_cap_most_prudent_96m"]),
                                    "min_of_both": reselect(tr, D["L_final"])}
    trU = C.latest("p35_B_usd1926", "*_rolling_h15.json")
    out["B2_reselect"]["USD1926_15"] = {"willingness_0.15": reselect(trU, D["L_will"]),
                                        "capacity_Lcap": reselect(trU, D["L_cap_most_prudent_96m"])}
    out["B2_reselect"]["A_6m"] = {"capacity_and_AMF1_0.0": reselect(trA, 0.0), "willingness_Q10_0.15": reselect(trA, 0.15),
                                  "tolerance_0.05": reselect(trA, 0.05)}
    trAT = C.latest("p35_A_tickers", "*_rolling_h0.5.json")
    out["B2_reselect"]["A_6m_tickers"] = {"capacity_0.0": reselect(trAT, 0.0), "willingness_0.15": reselect(trAT, 0.15)}
    p = C.write_trace("crosscheck", out, {"traces": [str(x) for x in (tr15, tr20, trA, trT, trU)]}, "crosscheck.py")
    print(json.dumps(C._clean(out), indent=1)[:9000])
