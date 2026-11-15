"""Anti-sycophancy test: add a 0..X % pocket of a heavily-mediatised stock to Robert's robust portfolio.

For each hype ticker (real data only, its own available period), each pocket size x and each horizon
(3/4/5 y, rolling windows step 1 month), simulate  (1-x) * BASE + x * TICKER  with the engine
(run_profile, static strategies, annual rebalancing, 10 bps) in CAD, Canadian CPI.

Derivation of the maximum pocket (proposal to be validated by the team):
  L*  = Robert's loss capacity derived in derive_thresholds.py (maxDD* for H = 4 y, conservative era).
  (a) path rule   : largest x whose WORST in-window max drawdown stays <= L* AND whose worst monthly
                    CVaR5 stays <= CVaR* (the two derived risk limits), every smaller x also admissible.
  (b) stress rule : budget B = L* - worst maxDD of BASE alone on the same windows; the pocket is assumed
                    to lose its own worst historical drawdown D_H at the same time -> x_stress = B / D_H.
  (c) total-loss  : same budget, pocket goes to zero (covers survivorship bias: failed hype stocks are
                    not in the universe)                                    -> x_zero = B / 1.
  Citable number = min(a, b) per ticker and horizon, then min over H = 3/4/5 y; (c) is reported as the
  survivorship-robust reference (failed hype stocks are absent from the universe).
Usage: .venv/bin/python -I analysis/robert/hype_pocket.py '{"XIU.TO":0.1,"SPY":0.1,"XBB.TO":0.4,"CA_TBILL":0.4}'
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from common import BT, write_trace
from engine import metrics as M
from engine.data import load_inflation, load_returns
from engine.profile import DEFAULTS, _merge, validate
from engine.run import run_profile

HYPE = ["TSLA", "NVDA", "SHOP.TO"]
POCKETS = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30, 0.50]
L_STAR = 0.23           # derive_thresholds.json, eras.usd_1926 h4 (0.227, rounded)
CVAR_STAR = 0.036


def main(base: dict):
    cash = "CA_TBILL" if "CA_TBILL" in base else next(iter(base))
    infl = load_inflation("CAD")
    out = {}
    for h in HYPE:
        uni = list(dict.fromkeys([*base, h]))
        R = load_returns(uni, currency="CAD")
        R = R.loc[: infl.index.max()]
        r_h = load_returns([h], currency="CAD")[h].values   # full own history of the ticker (CAD)
        D_H = M.max_drawdown(r_h)
        strategies = []
        for x in POCKETS:
            w = {a: (1 - x) * v for a, v in base.items()}
            w[h] = w.get(h, 0) + x
            strategies.append({"name": f"pocket_{int(round(x * 100)):02d}", "type": "static", "params": {"weights": w}})
        res_h = {"period": R.attrs["info"]["effective"], "n_months": len(R), "hype_own_history": load_returns([h], currency="CAD").attrs["info"]["effective"], "hype_full_maxdd": D_H,
                 "hype_full_vol": M.volatility(r_h), "hype_worst_12m": M.worst_window_return(r_h, 12), "by_horizon": {}}
        for H in (3, 4, 5):
            if len(R) < 12 * H + 1:
                continue
            p = _merge(DEFAULTS, {
                "id": f"robert_hype_{h.replace('.', '_')}", "currency": "CAD", "horizon_years": H, "mode": "rolling",
                "step_months": 1, "universe": uni, "cash_asset": cash, "period": {"start": None, "end": None},
                "objective": {"type": "min_shortfall", "target_real_return": 0.0},
                "risk_limits": {"max_vol": None, "max_drawdown": L_STAR, "max_cvar_5": CVAR_STAR},
                "rebalancing": {"frequency": "annual", "band": 0.05}, "costs_bps": 10, "strategies": strategies,
                "selection": {"quantile": 0.10, "max_breach_rate": None, "min_past_windows": 3},
                "oracle": {"enabled": False, "n_starts": 1}})
            p = validate(p)
            r = run_profile(p, out_dir=BT / "results" / "robert_hype", verbose=False)
            rows = r["rows"]
            g = rows.groupby("strategy")
            tab = pd.DataFrame({
                "pocket": [int(s.split("_")[1]) / 100 for s in g.size().index],
                "n_windows": g.size().values,
                "maxdd_worst": g["max_drawdown"].max().values,
                "maxdd_median": g["max_drawdown"].median().values,
                "real_p10": g["ann_real_return"].quantile(0.10).values,
                "real_median": g["ann_real_return"].median().values,
                "p_real_loss": g["missed_target"].apply(lambda s: s.astype(float).mean()).values,
                "p_dd_above_Lstar": g["max_drawdown"].apply(lambda s: float((s > L_STAR).mean())).values,
                "cvar5_worst": g["cvar_5"].max().values,
                "worst_12m_worst": g["worst_12m"].min().values,
            }).sort_values("pocket")
            base_dd = float(tab.loc[tab.pocket == 0, "maxdd_worst"].iloc[0])
            def admissible(cond):  # monotone: every smaller pocket must also satisfy cond
                x = 0.0
                for _, row in tab.iterrows():
                    if cond(row):
                        x = row["pocket"]
                    else:
                        break
                return x
            x_dd = admissible(lambda r_: r_["maxdd_worst"] <= L_STAR)
            x_cvar = admissible(lambda r_: r_["cvar5_worst"] <= CVAR_STAR)
            x_path = min(x_dd, x_cvar)
            B = max(0.0, L_STAR - base_dd)
            res_h["by_horizon"][f"h{H}"] = {
                "trace": r["trace_path"], "table": tab.to_dict(orient="records"), "base_maxdd_worst": base_dd,
                "base_cvar5_worst": float(tab.loc[tab.pocket == 0, "cvar5_worst"].iloc[0]),
                "budget_B": B, "x_path_dd": x_dd, "x_path_cvar": x_cvar, "x_path": x_path,
                "x_stress": B / D_H if D_H > 0 else None, "x_zero": B,
                "x_citable": min(x_path, B / D_H) if D_H > 0 else x_path}
            print(f"\n== {h} H={H}y period {res_h['period']} D_H={D_H:.3f} base_dd={base_dd:.3f} B={B:.3f} "
                  f"x_dd={x_dd} x_cvar={x_cvar} x_path={x_path} x_stress={B / D_H:.3f} x_zero={B:.3f}")
            print(tab.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        res_h["x_citable_min_over_horizons"] = min(v["x_citable"] for v in res_h["by_horizon"].values())
        print(f"** {h}: citable max pocket = {res_h['x_citable_min_over_horizons']}")
        out[h] = res_h
    path = write_trace("hype_pocket", {"base": base, "L_star": L_STAR, "cvar_star": CVAR_STAR, "tickers": out},
                       {"pockets": POCKETS, "horizons": [3, 4, 5], "rolling_step_months": 1, "currency": "CAD",
                        "rebalancing": "annual", "costs_bps": 10})
    print("trace:", path)


if __name__ == "__main__":
    main(json.loads(sys.argv[1]))
