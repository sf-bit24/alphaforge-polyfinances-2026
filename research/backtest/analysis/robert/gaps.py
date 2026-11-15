"""Oracle gap (hindsight cost) of the robust choice and walk-forward choice counts, per run -> trace gaps.json.
Run: .venv/bin/python -I analysis/robert/gaps.py
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


def main():
    out = []
    for d, m in RUNS:
        f = sorted(glob.glob(str(BT / "results" / d / f"*_{m}.json")))[-1]
        t = json.loads(Path(f).read_text())
        df = pd.DataFrame(t["results"])
        rc = t["summary"]["robust_choice"]
        o = df[df.hindsight].set_index("window")["score"]
        r = df[df.strategy == rc].set_index("window")["score"]
        wf = pd.DataFrame(t["walk_forward"])
        row = {"run": d, "mode": m, "trace": str(Path(f).relative_to(BT)), "robust_choice": rc,
               "n_windows": int(len(o)), "gap_mean": float((o - r).mean()), "gap_median": float((o - r).median()),
               "wf_choice_counts": wf["chosen"].value_counts().to_dict() if len(wf) else {},
               "walk_forward": t["summary"]["walk_forward"]}
        out.append(row)
        print(json.dumps(row))
    print("trace:", write_trace("gaps", out, {"runs": RUNS}))


if __name__ == "__main__":
    main()
