"""Print markdown tables for reports/robert.md from the engine traces (latest file per run).
Every table header names the trace file it comes from. Run: uv run --group finance python -I analysis/robert/report_tables.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from common import BT

RUNS = [("robert_long_usd", "non_overlapping", 4), ("robert_long_usd", "rolling", 4),
        ("robert_long_usd_h3", "non_overlapping", 3), ("robert_long_usd_h3", "rolling", 3),
        ("robert_long_usd_h5", "non_overlapping", 5), ("robert_long_usd_h5", "rolling", 5),
        ("robert_usd_gold", "non_overlapping", 4), ("robert_usd_gold", "rolling", 4),
        ("robert_cad", "non_overlapping", 4), ("robert_cad", "rolling", 4), ("robert_cad", "rolling", 3),
        ("robert_cad", "rolling", 5), ("robert_cad_eralimits", "non_overlapping", 4),
        ("robert_cad_eralimits", "rolling", 4)]
SHOW = ["cash_100", "ladder_tbill_2y", "bonds_5y", "bonds_20y", "bonds_ca10y", "eq20_2y", "eq20_5y", "eq20_10y",
        "eq20_20y", "eq20_gold10", "eq30_defensive", "eq30_mix", "sixty_forty", "risk_parity_36m", "trend_30_defensive"]


def latest(d, mode, h):
    fs = sorted(glob.glob(str(BT / "results" / d / f"*_{mode}_h{h}.json")))
    return Path(fs[-1]) if fs else None


def f(x, d=3):
    return "" if x is None or (isinstance(x, float) and pd.isna(x)) else (f"{x:.{d}f}" if isinstance(x, float) else str(x))


def robust_md(t, path, top=6):
    rb = pd.DataFrame(t["robust_selection"]).set_index("strategy")
    keep = list(rb.index[:top]) + [s for s in SHOW if s in rb.index and s not in rb.index[:top]]
    print(f"\n#### {path.parent.name} / {path.name}\n")
    s = t["summary"]
    print(f"Choix robuste : **{s['robust_choice']}** ({s['robust_rule']}). Walk-forward : {s['walk_forward']}\n")
    print("| rang | stratégie | p10 réel | médiane réel | pire réel | pire maxDD | taux violation | P(perte réelle) | éligible |")
    print("|---|---|---|---|---|---|---|---|---|")
    for k in keep:
        r = rb.loc[k]
        print(f"| {int(r['rank'])} | {k} | {f(r['score_p10'])} | {f(r['score_median'])} | {f(r['score_worst'])} | "
              f"{f(r['max_drawdown_worst'])} | {f(r['breach_rate'],2)} | {f(r['shortfall_prob'],2)} | {r['eligible']} |")


def window_md(t, path):
    df = pd.DataFrame(t["results"])
    robust = t["summary"]["robust_choice"]
    print(f"\n#### Par fenêtre : {path.parent.name} / {path.name} (choix robuste = {robust})\n")
    print("| fenêtre | ORACLE poids (>3 %) | ORACLE réel | ORACLE maxDD | meilleure ex-ante (a posteriori) | son réel | "
          f"{robust} réel | {robust} maxDD | recouvr. (mois) | CVaR5 | perte réelle ? |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for w, g in df.groupby("window", sort=False):
        o = g[g["hindsight"]].iloc[0]
        ex = g[~g["hindsight"]].set_index("strategy")
        b = ex["score"].idxmax()
        rc = ex.loc[robust]
        wt = ", ".join(f"{a} {v:.2f}" for a, v in sorted(o["avg_weights"].items(), key=lambda kv: -kv[1]) if v > 0.03)
        print(f"| {w} | {wt} | {f(o['ann_real_return'])} | {f(o['max_drawdown'])} | {b} | {f(ex.at[b, 'ann_real_return'])} | "
              f"{f(rc['ann_real_return'])} | {f(rc['max_drawdown'])} | {f(rc['recovery_months'],0)} | {f(rc['cvar_5'])} | "
              f"{'oui' if rc['missed_target'] else 'non'} |")


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for d, mode, h in RUNS:
        p = latest(d, mode, h)
        if p is None:
            print(f"\n(missing {d} {mode} h{h})")
            continue
        t = json.loads(p.read_text())
        if which in ("all", "robust"):
            robust_md(t, p)
        if which in ("all", "windows") and mode == "non_overlapping" and h == 4 and d in ("robert_long_usd", "robert_cad"):
            window_md(t, p)


if __name__ == "__main__":
    main()
