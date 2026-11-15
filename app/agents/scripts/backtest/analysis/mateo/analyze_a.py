"""Stage A: equity-share sensitivity of static mixes -> derivation of Mateo thresholds.
Reads traces listed in runs_A.json, writes results/mateo_analysis/stageA_grid.csv (+ .json with trace refs)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BT = HERE.parent.parent
OUT = BT / "results" / "mateo_analysis"
OUT.mkdir(parents=True, exist_ok=True)


def rows(trace):
    t = json.loads((BT / trace).read_text())
    return pd.DataFrame(t["results"]), t


def main():
    runs = json.loads((HERE / "runs_A.json").read_text())
    recs = []
    for job, tr in runs.items():
        pid, mode, h = job.split(":")[:3]
        df, t = rows(tr)
        df = df[df.strategy.str.startswith("static_eq")]
        for s, g in df.groupby("strategy"):
            e = int(s.replace("static_eq", "")) / 100
            rr = g["ann_real_return"]
            recs.append({"profile": pid, "mode": mode, "horizon": float(h), "equity_share": e, "n_windows": len(g),
                         "real_p10": rr.quantile(0.10), "real_median": rr.median(), "real_worst": rr.min(),
                         "p_real_below_0": float((rr < 0).mean()),
                         "vol_median": g["volatility"].median(), "vol_p90": g["volatility"].quantile(0.9),
                         "maxdd_median": g["max_drawdown"].median(), "maxdd_p90": g["max_drawdown"].quantile(0.9),
                         "maxdd_worst": g["max_drawdown"].max(),
                         "recovery_p90_months": g["recovery_months"].quantile(0.9),
                         "recovery_never_share": float(g["recovery_months"].isna().mean()),
                         "worst12m_worst": g["worst_12m"].min(),
                         "trace": tr})
    A = pd.DataFrame(recs).sort_values(["profile", "mode", "horizon", "equity_share"])
    A.to_csv(OUT / "stageA_grid.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_rows", 500)
    cols = ["equity_share", "n_windows", "real_p10", "real_median", "real_worst", "p_real_below_0", "vol_median",
            "maxdd_p90", "maxdd_worst", "recovery_p90_months", "recovery_never_share"]
    for (p, m, h), g in A.groupby(["profile", "mode", "horizon"]):
        if h != 10 and m != "rolling":
            continue
        print(f"\n== {p} {m} h{h:g}  {g.trace.iloc[0]}")
        print(g[cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
