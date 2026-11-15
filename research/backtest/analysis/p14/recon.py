"""Persona 14 - reconciliation of our monthly CAD metrics (engine data, 2021-12..2026-09 returns, i.e. base 2021-11-30)
with the regulatory analysis' daily CAD metrics (analyse/relation-profils-actifs/quant/metriques_titres_cad.csv,
2021-11-12..2026-11-12, produced by quant/stats_classes.py). READ ONLY on the other folder. SIMULATION ONLY.
Also: CNQ.TO with the engine's 2022-08 special-dividend correction undone (to size its effect).
Output: results/p14_analysis/recon.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as K  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import metrics as M  # noqa: E402
from engine.data import load_returns  # noqa: E402

THEIRS = Path("/mnt/c/Users/User/Desktop/ecole/hackoton/analyse/relation-profils-actifs/quant/metriques_titres_cad.csv")
TICK = ["CNQ.TO", "ENB.TO", "XOM", "SPY", "XBB.TO", "XIU.TO", "ZST.TO", "GLD"]


def stats(r: pd.Series) -> dict:
    y22 = r[r.index.year == 2022]
    return {"cagr": M.annualized_return(r.values), "vol": M.volatility(r.values), "maxdd": M.max_drawdown(r.values),
            "ret_2022": float((1 + y22).prod() - 1), "n_months": len(r)}


def main():
    th = pd.read_csv(THEIRS).set_index("Ticker")
    v = json.loads((K.HERE / "data_ext" / "data_version.json").read_text())
    fix = v.get("qa", {}).get("cnq_fix_2022_08_22", {})
    rows = []
    R = load_returns(TICK, "2021-12", "2026-09", "CAD")
    for t in TICK + ["CNQ.TO (sans correction)"]:
        if t.endswith("(sans correction)"):
            r = R["CNQ.TO"].copy()
            d = pd.Timestamp("2022-08-31")
            r.loc[d] = (1 + r.loc[d]) * (1 + fix["day_adj_close_return"]) / (1 + fix["day_true_total_return"]) - 1
            base = "CNQ.TO"
        else:
            r, base = R[t], t
        s = stats(r)
        o = th.loc[base]
        rows.append({"ticker": t, **{f"ours_{k}": x for k, x in s.items()},
                     "theirs_cagr": o["CAGR"], "theirs_vol": o["Vol"], "theirs_maxdd": -o["MaxDD"], "theirs_ret_2022": o["Rdt 2022"],
                     "theirs_peak": o["Pic"], "theirs_trough": o["Creux"]})
    df = pd.DataFrame(rows)
    for k in ("cagr", "vol", "maxdd", "ret_2022"):
        df[f"diff_{k}"] = df[f"ours_{k}"] - df[f"theirs_{k}"]
    df.to_csv(K.OUT / "recon.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(df.round(4).to_string())
    print("cnq fix", fix)


if __name__ == "__main__":
    main()
