"""Satellite sizing sweeps on REAL tickers (their actual, short histories), CAD investor:
  portfolio_k = (1 - k) * CORE + k * SATELLITE, static, annual rebalancing, 10 bps.
CORE = the derived CAD reference policy (E 80 %, BusEq 30 %, rest half CA_EQ / half US non-tech
industries, 20 % Canada 10y) from make_profiles.core(era="cad").

  single : SATELLITE = one tech-related stock (AAPL MSFT NVDA GOOGL AMZN TSLA SHOP.TO CSU.TO),
           rolling 5 y and 10 y windows, step 3 months
  crypto : SATELLITE = BTC-USD (2014-10+) or 50/50 BTC/ETH (2017-12+), rolling 3/4/5 y, step 1 month

Metric of interest = INCREMENT versus k = 0 in the SAME window (max drawdown, real return, worst 12 m),
so that market regime effects cancel out. Euler risk contribution of the satellite on the full sample.
Small samples, heavy overlap, survivorship bias (names chosen in 2026) -> see report.

    .venv/bin/python -I analysis/amira/sweep_satellite.py [single|crypto|all]
SIMULATION ONLY.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amira_common import NONTECH, RESULTS, rel, run, write_json  # noqa: E402
from make_profiles import core  # noqa: E402
from engine.data import load_returns  # noqa: E402

K_SINGLE = [0.0, 0.02, 0.03, 0.04, 0.05, 0.07, 0.10, 0.15, 0.20, 0.30]
K_CRYPTO = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.075, 0.10, 0.15, 0.20]
NAMES = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "SHOP.TO", "CSU.TO"]
CORE = core(era="cad")
CORE_ASSETS = list(CORE)


def mix(sat: dict, k: float) -> dict:
    w = {a: (1 - k) * v for a, v in CORE.items()}
    for a, v in sat.items():
        w[a] = w.get(a, 0) + k * v
    return {a: round(x, 10) for a, x in w.items() if x > 0}


REBAL = {"frequency": "annual"}
SUFFIX = ""


def prof(pid, sat: dict, ks, start=None):
    uni = CORE_ASSETS + [a for a in sat if a not in CORE_ASSETS] + ["CA_TBILL"]
    return {"id": pid, "currency": "CAD", "horizon_years": 5, "mode": "rolling", "step_months": 3,
            "period": {"start": start, "end": None}, "universe": uni, "cash_asset": "CA_TBILL",
            "objective": {"type": "max_real_return", "target_real_return": 0.0},
            "rebalancing": REBAL, "costs_bps": 10,
            "strategies": [{"name": f"k{int(round(k*1000)):03d}", "type": "static", "params": {"weights": mix(sat, k)}}
                           for k in ks],
            "oracle": {"enabled": False}, "seed": 42}


def increments(rows: pd.DataFrame) -> pd.DataFrame:
    r = rows[~rows["hindsight"]].copy()
    base = r[r["strategy"] == "k000"].set_index("window")
    out = []
    for s, g in r.groupby("strategy"):
        g = g.set_index("window")
        d_dd = g["max_drawdown"] - base.loc[g.index, "max_drawdown"]
        d_rr = g["ann_real_return"] - base.loc[g.index, "ann_real_return"]
        d_12 = g["worst_12m"] - base.loc[g.index, "worst_12m"]
        out.append({"k": int(s[1:]) / 1000, "n_windows": len(g),
                    "d_maxdd_worst": float(d_dd.max()), "d_maxdd_median": float(d_dd.median()),
                    "d_real_p10": float(d_rr.quantile(0.10)), "d_real_median": float(d_rr.median()),
                    "d_worst12m_worst": float(d_12.min()),
                    "maxdd_worst": float(g["max_drawdown"].max()), "real_p10": float(g["ann_real_return"].quantile(0.1)),
                    "dd_window": g["max_drawdown"].idxmax()})
    return pd.DataFrame(out).sort_values("k")


def risk_contrib(sat: dict, ks) -> dict:
    assets = CORE_ASSETS + [a for a in sat if a not in CORE_ASSETS]
    R = load_returns(assets, currency="CAD")
    C = np.cov(R.values.T, ddof=1) * 12
    out = {"period": R.attrs["info"]["effective"]}
    for k in ks:
        w = pd.Series(mix(sat, k)).reindex(assets).fillna(0).values
        pv = w @ C @ w
        rc = w * (C @ w) / pv
        out[f"{k:.3f}"] = {"sat_risk_share": float(sum(rc[assets.index(a)] for a in sat)),
                           "port_vol": float(np.sqrt(pv))}
    sat_r = R[list(sat)].values @ np.array(list(sat.values()))
    wealth = np.cumprod(1 + sat_r)
    out["satellite_full_sample_maxdd"] = float((1 - wealth / np.maximum.accumulate(wealth)).max())
    out["satellite_vol_ann"] = float(sat_r.std(ddof=1) * np.sqrt(12))
    return out


def do(kind: str):
    res_all = {}
    if kind == "single":
        jobs = [(n, {n: 1.0}, K_SINGLE, (5, 10)) for n in NAMES]
    else:
        jobs = [("BTC", {"BTC-USD": 1.0}, K_CRYPTO, (3, 4, 5)),
                ("BTC_ETH", {"BTC-USD": 0.5, "ETH-USD": 0.5}, K_CRYPTO, (3, 4, 5))]
    for label, sat, ks, hs in jobs:
        rc = risk_contrib(sat, ks)
        for h in hs:
            step = 3 if kind == "single" else 1
            try:
                res = run(prof(f"amira_{kind}_{label}", sat, ks), f"amira_sat_{kind}{SUFFIX}", horizon=h, mode="rolling",
                          step_months=step)
            except ValueError as e:  # not enough history for this horizon
                res_all[f"{label}_h{h}"] = {"error": str(e)}
                continue
            inc = increments(res["rows"])
            res_all[f"{label}_h{h}"] = {"trace": rel(res["trace_path"]), "data_info": res["data_info"],
                                        "n_windows": len(res["windows"]), "increments": inc.to_dict(orient="records")}
            print(label, h, rel(res["trace_path"]), len(res["windows"]))
            print(inc.round(4).to_string(index=False))
        res_all[f"{label}_risk_contrib"] = rc
    p = write_json(res_all, RESULTS / f"amira_sat_{kind}{SUFFIX}" / f"sat_{kind}_summary.json",
                   [v["trace"] for v in res_all.values() if isinstance(v, dict) and "trace" in v])
    print("summary:", p)


if __name__ == "__main__":
    k = sys.argv[1] if len(sys.argv) > 1 else "all"
    if len(sys.argv) > 2:  # optional rebalancing override, e.g. "monthly" or "bands:0.01"
        f, _, b = sys.argv[2].partition(":")
        REBAL = {"frequency": f, "band": float(b or 0.05)}
        SUFFIX = "_" + sys.argv[2].replace(":", "")
    for kind in (["single", "crypto"] if k == "all" else [k]):
        do(kind)
