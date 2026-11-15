"""Summarise persona-12 engine traces (latest trace per profile x mode x horizon) into results/p12_analysis/tables.json
and print markdown tables for the report. Reads traces only. SIMULATION ONLY."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

from common import BT, write_trace

CLASSES = {"fnb_actions": ["CA_EQ", "US_MKT"], "titres_proxy_sect": ["US_IND_UTILS", "US_IND_MONEY", "US_IND_BUSEQ", "US_IND_HLTH"],
           "oblig": ["CA_GOV_10Y", "UST_5Y", "UST_10Y", "UST_2Y"], "encaisse": ["CA_TBILL", "UST_TBILL"], "or": ["GOLD"]}


def latest():
    out = {}
    for d in sorted((BT / "results").glob("p12_*")):
        if d.name in ("p12_analysis", "p12_logs"):
            continue
        for f in sorted(d.glob("*.json")):
            stem = f.stem.split("_", 1)[1]          # e.g. rolling_h6
            out[(d.name, stem)] = f                   # sorted -> last = latest
    return out


def cls_weights(w: dict) -> dict:
    return {c: float(sum(w.get(a, 0) for a in A)) for c, A in CLASSES.items()}


def main():
    res = {}
    for (pid, stem), f in latest().items():
        t = json.loads(f.read_text())
        rows = pd.DataFrame(t["results"])
        rob = pd.DataFrame(t["robust_selection"]).set_index("strategy")
        choice = t["summary"]["robust_choice"]
        orc = rows[rows.hindsight]
        ow = pd.DataFrame([cls_weights(w) for w in orc["avg_weights"]]) if len(orc) else pd.DataFrame()
        chosen_rows = rows[(rows.strategy == choice) & (~rows.hindsight)]
        cw = chosen_rows["avg_weights"].apply(cls_weights)
        bnc = rob[rob.index.str.startswith("bnc_")]
        bnc_elig = bnc[bnc.eligible]
        wf = t["walk_forward"]
        key = f"{pid}|{stem}"
        res[key] = {
            "trace": str(f.relative_to(BT)), "n_windows": len(t["windows"]), "data_info": t["data_info"]["effective"],
            "robust_choice": choice, "robust_row": rob.loc[choice].to_dict(),
            "robust_top5": rob.head(5).reset_index()[["strategy", "score_p10", "score_median", "max_drawdown_worst", "breach_rate", "shortfall_prob", "eligible"]].to_dict("records"),
            "chosen_class_weights_mean": pd.DataFrame(list(cw)).mean().to_dict() if len(cw) else {},
            "oracle_class_p10_p90": {c: [float(ow[c].quantile(.1)), float(ow[c].quantile(.9))] for c in ow} if len(ow) else {},
            "oracle_class_median": {c: float(ow[c].median()) for c in ow} if len(ow) else {},
            "bnc": bnc.reset_index()[["strategy", "score_p10", "score_median", "max_drawdown_worst", "breach_rate", "shortfall_prob", "eligible"]].to_dict("records"),
            "bnc_best_eligible": bnc_elig.index[0] if len(bnc_elig) else None,
            "bnc_best_p10_ignoring_limits": bnc["score_p10"].idxmax(),
            "walk_forward_summary": t["summary"]["walk_forward"],
            "walk_forward_choices": pd.Series([w["chosen"] for w in wf]).value_counts().to_dict() if wf else {},
            "eq100_rows": rob.loc[[s for s in rob.index if s.startswith("eq100")]].reset_index()[["strategy", "score_p10", "score_median", "max_drawdown_worst", "breach_rate", "shortfall_prob"]].to_dict("records"),
            "per_window": [
                {"window": w, "oracle_w": {a: round(x, 2) for a, x in (orc[orc.window == w]["avg_weights"].iloc[0].items() if len(orc[orc.window == w]) else []) if x > .03},
                 "oracle_score": float(orc[orc.window == w]["score"].iloc[0]) if len(orc[orc.window == w]) else None,
                 "oracle_maxdd": float(orc[orc.window == w]["max_drawdown"].iloc[0]) if len(orc[orc.window == w]) else None,
                 "best_ex_ante": rows[(rows.window == w) & (~rows.hindsight)].sort_values("score").iloc[-1]["strategy"],
                 "best_ex_ante_score": float(rows[(rows.window == w) & (~rows.hindsight)]["score"].max()),
                 "chosen_score": float(chosen_rows[chosen_rows.window == w]["score"].iloc[0]),
                 "chosen_real": float(chosen_rows[chosen_rows.window == w]["ann_real_return"].iloc[0]),
                 "chosen_maxdd": float(chosen_rows[chosen_rows.window == w]["max_drawdown"].iloc[0]),
                 "chosen_final_real_wealth": float(chosen_rows[chosen_rows.window == w]["final_real_wealth"].iloc[0]),
                 "chosen_missed": bool(chosen_rows[chosen_rows.window == w]["missed_target"].iloc[0])}
                for w in t["windows"]] if stem.startswith("non_overlapping") else None,
        }
        r = res[key]
        print(f"\n## {key}  ({r['trace']}) n={r['n_windows']} choice={choice} p10={r['robust_row']['score_p10']:.4f} "
              f"med={r['robust_row']['score_median']:.4f} ddw={r['robust_row']['max_drawdown_worst']:.3f} br={r['robust_row']['breach_rate']:.2f} sf={r['robust_row']['shortfall_prob']}")
        print("  top5:", [(x["strategy"], round(x["score_p10"], 4), x["eligible"]) for x in r["robust_top5"]])
        print("  chosen cls:", {k: round(v, 3) for k, v in r["chosen_class_weights_mean"].items()})
        print("  oracle p10-p90:", {k: [round(a, 2) for a in v] for k, v in r["oracle_class_p10_p90"].items()})
        print("  bnc best eligible:", r["bnc_best_eligible"], "| ignoring limits:", r["bnc_best_p10_ignoring_limits"])
        print("  bnc:", [(x["strategy"], round(x["score_p10"], 4), round(x["max_drawdown_worst"], 3), round(x["breach_rate"], 2), x["shortfall_prob"]) for x in r["bnc"]])
        print("  eq100:", [(x["strategy"], round(x["score_p10"], 4), round(x["max_drawdown_worst"], 3), round(x["breach_rate"], 2), x["shortfall_prob"]) for x in r["eq100_rows"]])
        print("  WF:", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r["walk_forward_summary"].items()}, r["walk_forward_choices"])
    print(write_trace("tables", res, {"source": "latest engine trace per profile x mode x horizon"}))


if __name__ == "__main__":
    main()
