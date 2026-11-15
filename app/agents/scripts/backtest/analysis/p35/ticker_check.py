"""Persona 35 - real-ticker check 2021-11..2026-09 (59 months) of the retained pocket-B strategy, including the
DYNAMIC risk parity (needs 36 months of history -> data loaded from 2011-03, ZST.TO limiting; the evaluated
window is 2021-11..2026-09 only). Engine run_window + basket inflation (s = 0.5), 4 %/yr withdrawals.
Reports nominal CAD, real CAD (CPI CA), nominal USD, real USD (CPI US), real basket. SIMULATION ONLY."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

import common as C
from alphaforge.finance.backtest import metrics as M
from alphaforge.finance.backtest.backtest import ConstraintProvider, run_window
from alphaforge.finance.backtest.data import load_inflation, load_returns
from alphaforge.finance.backtest.profile import load_profile
from alphaforge.finance.backtest.strategies import build_strategy
from alphaforge.finance.backtest.windows import Window

if __name__ == "__main__":
    p = copy.deepcopy(load_profile("p35_B_tickers"))
    p["objective"]["target_real_wealth"] = round(1 - 0.04 * 59 / 12, 4)
    U = p["universe"]
    R = load_returns(U, "2011-03", "2026-09", "CAD")
    infl = C.basket_inflation(0.5, "CAD")
    w = Window(pd.Timestamp("2021-11-30"), pd.Timestamp("2026-09-30"), 59)
    prov = ConstraintProvider(U, p["constraints"])
    rp_static = {"XIU.TO": .13, "SPY": .13, "PG": .06, "JNJ": .04, "XBB.TO": .27, "AGG": .21, "ZST.TO": .02,
                 "UST_TBILL": .02, "GLD": .12}
    specs = [{"name": "risk_parity_36m_tickers", "type": "risk_parity",
              "params": {"lookback": 36, "method": "inverse_vol", "exclude": ["ZST.TO", "UST_TBILL"]}},
             {"name": "rp_static_approx", "type": "static", "params": {"weights": rp_static}},
             {"name": "e40_u50_gold15", "type": "static", "params": {"weights": {"SPY": .17, "XIU.TO": .17, "AGG": .255, "XBB.TO": .255, "GLD": .15}}},
             {"name": "bnc_pondere_usdfi", "type": "static", "params": {"weights": {"XBB.TO": .365, "AGG": .185, "XIU.TO": .135, "SPY": .315}}},
             {"name": "bnc_pondere", "type": "static", "params": {"weights": {"XBB.TO": .55, "XIU.TO": .135, "SPY": .315}}},
             {"name": "bnc_equilibre", "type": "static", "params": {"weights": {"XBB.TO": .40, "XIU.TO": .18, "SPY": .42}}},
             {"name": "cash_zst", "type": "static", "params": {"weights": {"ZST.TO": 1.0}}},
             {"name": "cash_usd_tbill", "type": "static", "params": {"weights": {"UST_TBILL": 1.0}}}]
    fx = C.fx_monthly()
    f = (fx / fx.shift(1) - 1).loc[w.start:w.end].values
    pc = load_inflation("CAD").loc[w.start:w.end].values
    pu = load_inflation("USD").loc[w.start:w.end].values
    out = {}
    for s in specs:
        st = build_strategy(s)
        res = run_window(R, infl, w, st, p, prov, None, None)
        r = res["returns"].values
        m = res["metrics"]
        nom = np.prod(1 + r)
        out[s["name"]] = {"nominal_cad": M.annualized_return(r),
                          "real_cad": float((nom / np.prod(1 + pc)) ** (12 / 59) - 1),
                          "nominal_usd": float((nom / np.prod(1 + f)) ** (12 / 59) - 1),
                          "real_usd": float((nom / np.prod(1 + f) / np.prod(1 + pu)) ** (12 / 59) - 1),
                          "real_basket": m["ann_real_return"], "max_drawdown_cad": m["max_drawdown"],
                          "max_drawdown_usd": M.max_drawdown((1 + r) / (1 + f) - 1),
                          "worst_12m_cad": m["worst_12m"], "recovery_months": m["recovery_months"],
                          "final_real_wealth_4pct": m["final_real_wealth"], "breaches": m["risk_breaches"],
                          "mean_weights": {k: round(float(v), 4) for k, v in res["weights"].mean().items() if v > 1e-4},
                          "usd_share_mean": float(sum(v for k, v in res["weights"].mean().items()
                                                      if k in ("SPY", "PG", "JNJ", "AGG", "UST_TBILL", "GLD"))),
                          "fallback_months": m["fallback_months"]}
        print(s["name"], {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out[s["name"]].items() if k != "mean_weights"})
        print("   ", out[s["name"]]["mean_weights"])
    pth = C.write_trace("ticker_check", out, {"window": w.label, "history_from": "2011-03", "basket_s": 0.5,
                                              "withdrawal": 0.04}, "ticker_check.py")
    print(pth)
