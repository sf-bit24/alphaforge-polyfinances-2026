"""Ticker translation check on the real period 2021-11..2026-09 (CAD) with the engine's run_window/oracle_window.
Two flow variants: decumulation (1.3 M$, 4 % indexed withdrawals) and accumulation (640 k$, +9 908 $/month H1).
History before 2021-11 (from 2014-10, BTC-USD limiting) is visible to the estimation-based strategies.
SIMULATION ONLY - one 59-month window: illustration, NOT evidence of sustainability over 50 years."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

from common import write_trace
from alphaforge.finance.backtest.backtest import ConstraintProvider, run_window
from alphaforge.finance.backtest.data import load_inflation, load_returns
from alphaforge.finance.backtest.oracle import oracle_window
from alphaforge.finance.backtest.profile import load_profile
from alphaforge.finance.backtest.strategies import build_strategy
from alphaforge.finance.backtest.windows import Window


def main():
    base = load_profile("p12_tickers")
    R = load_returns(base["universe"], start="2014-10", end="2026-09", currency="CAD")
    infl = load_inflation("CAD")
    w = Window(pd.Timestamp("2021-11-30"), pd.Timestamp("2026-09-30"), len(R.loc["2021-11-30":"2026-09-30"]))
    out = {"window": w.label, "n_months": w.n_months, "data_info": R.attrs["info"], "variants": {}}
    for var, flows, obj in (("decumulation_4pct", {"initial": 1300000.0, "monthly": -52000 / 12, "indexed_to_inflation": True},
                             {"type": "min_shortfall", "target_real_return": 0.03153, "target_real_wealth": None}),
                            ("accumulation_H1", {"initial": 640000.0, "monthly": 9908.0, "indexed_to_inflation": True},
                             {"type": "min_shortfall", "target_real_return": None, "target_real_wealth": 1300000.0})):
        p = copy.deepcopy(base)
        p["flows"], p["objective"] = flows, obj
        prov = ConstraintProvider(p["universe"], p["constraints"])
        fb = prov.at(R.index[-1]).project(np.array([p["fallback_weights"].get(a, 0) for a in p["universe"]]))
        rows = {}
        for s in p["strategies"]:
            res = run_window(R, infl, w, build_strategy(s), p, prov, {}, fb)
            m = res["metrics"]
            r = res["returns"]
            rows[s["name"]] = {"ann_real_return": m["ann_real_return"], "max_drawdown": m["max_drawdown"],
                               "volatility": m["volatility"], "final_real_wealth": m["final_real_wealth"],
                               "score": m["score"], "ret_2022": float(np.prod(1 + r["2022-01":"2022-12"].values) - 1),
                               "avg_weights": {a: round(float(x), 3) for a, x in res["weights"].mean().items() if x > 0.005},
                               "breach": m["risk_breaches"]}
        o = oracle_window(R, infl, w, p, prov, seed=42)
        rows["ORACLE"] = {"hindsight": True, "ann_real_return": o["metrics"]["ann_real_return"],
                          "max_drawdown": o["metrics"]["max_drawdown"], "final_real_wealth": o["metrics"]["final_real_wealth"],
                          "score": o["metrics"]["score"], "weights": {a: x for a, x in o["weights"].items() if x > 0.005}}
        out["variants"][var] = rows
        print(var)
        for k, v in rows.items():
            print(f"  {k:24s} real {v['ann_real_return']:.4f} dd {v['max_drawdown']:.3f} FRW {v['final_real_wealth']:,.0f} "
                  f"2022 {v.get('ret_2022', float('nan')):.3f}")
    print(write_trace("tickers_2021_2026", out, {"profile": "profiles/p12_tickers.yaml", "doc": __doc__}))


if __name__ == "__main__":
    main()
