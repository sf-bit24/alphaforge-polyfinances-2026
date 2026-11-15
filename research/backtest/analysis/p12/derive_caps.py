"""Derive caps for 'satellite' / 'limite' classes of persona 12 by sensitivity (PROPOSALS to validate).

Rule (readable): a satellite / limited sleeve may not worsen the base portfolio's maximum drawdown by more than
TOL (1 pt; 2 pt reported) in the WORST case across the candidate assets of the class. Cap = largest tested weight
satisfying the rule. The sleeve is funded pro rata from the base weights. Base = public BNC target mixes
(Croissance for accumulation, Equilibre for decumulation) on the longest common history of each test.
Gold (satellite, diversifier) gets an extra decumulation criterion: weight that does not lower the worst-case
30-year perfect withdrawal rate (CAD 1977+) / 40-year (USD 1975+).
SIMULATION ONLY - survivorship bias: the names were chosen in 2026.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np

from common import bnc_weights, era_data, port_returns, pwr_all, write_trace
from engine import metrics as M
from engine.data import load_returns

XS = [0, .01, .02, .03, .05, .07, .10, .15, .20]
TOL = (0.01, 0.02)
CA_NAMES = ["RY.TO", "TD.TO", "MFC.TO", "ENB.TO", "CNQ.TO", "CNR.TO", "FTS.TO", "ATD.TO", "CSU.TO", "SHOP.TO"]
US_NAMES = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "JNJ", "PG", "XOM"]
SECTORS = ["US_IND_UTILS", "US_IND_MONEY", "US_IND_BUSEQ", "US_IND_HLTH", "US_IND_ENRGY", "US_IND_NODUR"]


def tilt(base: dict, asset: str, x: float) -> dict:
    w = {a: v * (1 - x) for a, v in base.items()}
    w[asset] = w.get(asset, 0) + x
    return w


def curve(base_fn, assets, cands, currency, start=None):
    """For each candidate: delta maxDD and delta worst-12m vs x, on the candidate's own common history."""
    out = {}
    for c in cands:
        R = load_returns(assets + [c], start=start, currency=currency)
        b = base_fn()
        r0 = port_returns(R, b)
        dd0, w0 = M.max_drawdown(r0), M.worst_window_return(r0, 12)
        rows = []
        for x in XS:
            r = port_returns(R, tilt(b, c, x))
            rows.append({"x": x, "max_dd": M.max_drawdown(r), "d_max_dd": M.max_drawdown(r) - dd0,
                         "worst12": M.worst_window_return(r, 12), "d_worst12": M.worst_window_return(r, 12) - w0,
                         "ann_return": M.annualized_return(r)})
        out[c] = {"period": [str(R.index[0].date()), str(R.index[-1].date())], "n_months": len(R),
                  "base_max_dd": dd0, "rows": rows}
    return out


def cap_from(curves, tol):
    caps = []
    for x in XS:
        worst = max(next(r["d_max_dd"] for r in c["rows"] if r["x"] == x) for c in curves.values())
        if worst <= tol + 1e-12:
            caps.append(x)
        else:
            break
    return max(caps) if caps else 0.0


def main():
    res = {}
    bases = {"accumulation": "Croissance", "decumulation": "Equilibre"}
    tick = ["XBB.TO", "XIU.TO", "SPY"]
    for pocket, bn in bases.items():
        fn = lambda bn=bn: bnc_weights(bn, "XBB.TO", "XIU.TO", "SPY")
        ca = curve(fn, tick, CA_NAMES, "CAD")
        us = curve(fn, tick, US_NAMES, "CAD")
        lng_fn = lambda bn=bn: bnc_weights(bn, "CA_GOV_10Y", "CA_EQ", "US_MKT")
        sec = curve(lng_fn, ["CA_GOV_10Y", "CA_EQ", "US_MKT"], SECTORS, "CAD", "1977-01")
        usd_fn = lambda bn=bn: {"UST_10Y": BNCF(bn), "US_MKT": 1 - BNCF(bn)}
        sec_usd = curve(usd_fn, ["UST_10Y", "US_MKT"], SECTORS, "USD", "1926-08")
        btc = curve(fn, tick, ["BTC-USD", "ETH-USD"], "CAD")
        res[pocket] = {"base": bn,
                       "single_ca": {"curves": ca, "cap": {str(t): cap_from(ca, t) for t in TOL}},
                       "single_us": {"curves": us, "cap": {str(t): cap_from(us, t) for t in TOL}},
                       "sector_cad1977": {"curves": sec, "cap": {str(t): cap_from(sec, t) for t in TOL}},
                       "sector_usd1926": {"curves": sec_usd, "cap": {str(t): cap_from(sec_usd, t) for t in TOL}},
                       "crypto": {"curves": btc, "cap": {str(t): cap_from(btc, t) for t in TOL}}}
        print(pocket, {k: v["cap"] for k, v in res[pocket].items() if isinstance(v, dict)})
    # gold: decumulation criterion on worst-case PWR
    gold = {}
    for name, cur, start, fi, H, eq in (("cad_1977", "CAD", "1977-01", "CA_GOV_10Y", 30, {"CA_EQ": .18 / .6, "US_MKT": .42 / .6}),
                                         ("usd_1975", "USD", "1975-01", "UST_10Y", 40, {"US_MKT": 1.0})):
        assets = list(eq) + [fi, "GOLD"]
        R, infl = era_data(assets, cur, start)
        rows = []
        for e in (0.4, 0.6):
            for g in (0, .05, .10, .15, .20, .30):
                w = {a: v * e * (1 - g) for a, v in eq.items()}
                w[fi] = (1 - e) * (1 - g)
                w["GOLD"] = g
                r = port_returns(R, w)
                p = pwr_all(r, infl.values, 12 * H)
                rows.append({"equity_before_gold": e, "gold": g, "max_dd": M.max_drawdown(r), "pwr_min": float(p.min()),
                             "pwr_p10": float(np.quantile(p, .1)), "n_windows": len(p)})
        caps = {}
        for e in (0.4, 0.6):
            sub = [r for r in rows if r["equity_before_gold"] == e]
            r0 = sub[0]
            ok = [r["gold"] for r in sub if r["pwr_min"] >= r0["pwr_min"] - 1e-9 and r["max_dd"] <= r0["max_dd"] + 0.01]
            caps[str(e)] = max(ok)
        gold[name] = {"period": [str(R.index[0].date()), str(R.index[-1].date())], "H": H, "rows": rows, "cap": caps}
        print("gold", name, caps)
    res["gold"] = gold
    print(write_trace("derive_caps", res, {"xs": XS, "tol": TOL, "rule": __doc__}))


def BNCF(bn):
    from common import BNC
    return BNC[bn][0]


if __name__ == "__main__":
    main()
