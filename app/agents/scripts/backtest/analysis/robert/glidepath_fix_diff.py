"""Before/after the engine glidepath fix (engine/backtest.py _progress, 2026-11-14): compare the previous and the
latest trace of each Robert run (robust choice, glidepath row in the robust table, walk-forward) -> trace glidepath_fix.json.
Run: uv run --group finance python -I analysis/robert/glidepath_fix_diff.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from common import BT, write_trace

RUNS = [("robert_long_usd", "non_overlapping_h4"), ("robert_long_usd", "rolling_h4"),
        ("robert_long_usd_h3", "non_overlapping_h3"), ("robert_long_usd_h3", "rolling_h3"),
        ("robert_long_usd_h5", "non_overlapping_h5"), ("robert_long_usd_h5", "rolling_h5"),
        ("robert_usd_gold", "non_overlapping_h4"), ("robert_usd_gold", "rolling_h4"),
        ("robert_cad", "non_overlapping_h4"), ("robert_cad", "rolling_h4"), ("robert_cad", "rolling_h3"),
        ("robert_cad", "rolling_h5"), ("robert_cad_eralimits", "non_overlapping_h4"), ("robert_cad_eralimits", "rolling_h4")]


def summ(path: Path) -> dict:
    t = json.loads(path.read_text())
    rb = pd.DataFrame(t["robust_selection"]).set_index("strategy")
    g = rb.loc["glide_40_to_10"]
    return {"trace": str(path.relative_to(BT)), "engine_sha256": t["engine_sha256"], "robust_choice": t["summary"]["robust_choice"],
            "glide_rank": int(g["rank"]), "glide_p10": float(g["score_p10"]), "glide_median": float(g["score_median"]),
            "glide_maxdd_worst": float(g["max_drawdown_worst"]), "glide_breach_rate": float(g["breach_rate"]),
            "glide_eligible": bool(g["eligible"]), "wf": t["summary"]["walk_forward"],
            "top3": list(rb.index[:3])}


def main():
    out = []
    for d, m in RUNS:
        fs = sorted(glob.glob(str(BT / "results" / d / f"*_{m}.json")))
        if len(fs) < 2:
            print("missing before/after for", d, m)
            continue
        b, a = summ(Path(fs[-2])), summ(Path(fs[-1]))
        out.append({"run": d, "mode": m, "before": b, "after": a,
                    "robust_choice_changed": b["robust_choice"] != a["robust_choice"],
                    "top3_changed": b["top3"] != a["top3"]})
        print(f"{d} {m}: robust {b['robust_choice']} -> {a['robust_choice']} | glide rank {b['glide_rank']}->{a['glide_rank']} "
              f"p10 {b['glide_p10']:.4f}->{a['glide_p10']:.4f} med {b['glide_median']:.4f}->{a['glide_median']:.4f} "
              f"maxDD {b['glide_maxdd_worst']:.3f}->{a['glide_maxdd_worst']:.3f} breach {b['glide_breach_rate']:.2f}->"
              f"{a['glide_breach_rate']:.2f} elig {b['glide_eligible']}->{a['glide_eligible']} | WF mean "
              f"{b['wf']['mean_oos_score']:.4f}->{a['wf']['mean_oos_score']:.4f} p10 {b['wf']['p10_oos_score']:.4f}->"
              f"{a['wf']['p10_oos_score']:.4f} | top3 {b['top3']} -> {a['top3']} | engine {b['engine_sha256']}->{a['engine_sha256']}")
    print("trace:", write_trace("glidepath_fix", out, {"runs": RUNS}))


if __name__ == "__main__":
    main()
