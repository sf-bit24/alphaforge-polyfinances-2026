"""Per-window metrics of ONE strategy next to the ORACLE and the best ex-ante strategy, from an engine trace.
    .venv/bin/python -I analysis/amira/per_window_strategy.py <trace.json> <strategy>
Prints a markdown table (values copied from the trace, no new simulation)."""
from __future__ import annotations

import json
import sys

import pandas as pd

tr = json.load(open(sys.argv[1]))
s = sys.argv[2]
rows = pd.DataFrame(tr["results"])
orc = {o["window"]: o for o in tr["oracle"]}
print(f"Trace `{sys.argv[1]}` — stratégie {s}\n")
print("| fenêtre | ORACLE (poids principaux) | ORACLE réel % | meilleure ex-ante (réel %) | " + s +
      " réel % | vol % | maxDD % | recouvr. (mois) | CVaR5 mens. % | réel < 0 ? | écart ORACLE pt |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for w in tr["windows"]:
    r = rows[(rows.window == w) & (~rows.hindsight)].set_index("strategy")
    b = r["score"].idxmax()
    x = r.loc[s]
    o = orc[w]
    top = "; ".join(f"{a} {v:.2f}" for a, v in sorted(o["weights"].items(), key=lambda kv: -kv[1])[:3] if v > 0.005)
    rec = "non récupéré" if x["recovery_months"] is None or pd.isna(x["recovery_months"]) else int(x["recovery_months"])
    print(f"| {w} | {top} | {100*o['metrics']['ann_real_return']:.1f} | {b} ({100*r.at[b,'ann_real_return']:.1f}) | "
          f"{100*x['ann_real_return']:.1f} | {100*x['volatility']:.1f} | {100*x['max_drawdown']:.1f} | {rec} | "
          f"{100*x['cvar_5']:.1f} | {'oui' if x['missed_target'] else 'non'} | "
          f"{100*(o['metrics']['ann_real_return']-x['ann_real_return']):.1f} |")
