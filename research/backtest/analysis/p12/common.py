"""Shared helpers for persona 12 (Julien & Mei-Lin, FIRE) analyses. Imports the engine, never modifies it.

SIMULATION ONLY - historical reconstructions, not forecasts, not financial advice.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import metrics as M
from engine.data import data_version, load_inflation, load_returns
from engine.run import DISCLAIMER, _clean, engine_hash

BT = Path(__file__).resolve().parents[2]          # research/backtest
OUT = BT / "results" / "p12_analysis"
OUT.mkdir(parents=True, exist_ok=True)

# Eras (asset universes). Proxies documented in data/SOURCES.md / README.md.
ERA_USD = dict(name="usd_1926", currency="USD", start="1926-08",
               eq={"US_MKT": 1.0}, legs=["UST_TBILL", "UST_2Y", "UST_5Y", "UST_10Y"], gold=None, cash="UST_TBILL")
ERA_CAD = dict(name="cad_1977", currency="CAD", start="1977-01",
               eq={"CA_EQ": 0.3, "US_MKT": 0.7}, legs=["CA_TBILL", "CA_GOV_10Y", "UST_5Y"], gold="GOLD", cash="CA_TBILL")

# Public BNC target portfolios (00-cadre.md, brochure 2025-10): % fixed income / CA equity / global equity.
BNC = {"Prudent": (0.80, 0.06, 0.14), "Conservateur": (0.70, 0.09, 0.21), "Pondere": (0.55, 0.135, 0.315),
       "Equilibre": (0.40, 0.18, 0.42), "Croissance": (0.20, 0.24, 0.56), "Actions": (0.00, 0.30, 0.70)}


def bnc_weights(name: str, fi: str, ca: str, glob: str) -> dict:
    f, c, g = BNC[name]
    w: dict = {}
    for a, x in ((fi, f), (ca, c), (glob, g)):
        if x > 0:
            w[a] = w.get(a, 0.0) + x
    return w


def write_trace(name: str, payload: dict, params: dict) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace = {"run_id": name, "created_utc": stamp, "disclaimer": DISCLAIMER, "engine_sha256": engine_hash(),
             "data_version": data_version(), "script": "analysis/p12", "params": params, "results": payload}
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(_clean(trace), indent=1, default=str))
    return p


def era_data(assets: list[str], currency: str, start: str, end=None):
    R = load_returns(assets, start=start, end=end, currency=currency)
    infl = load_inflation(currency).reindex(R.index)
    ok = infl.notna()
    R, infl = R[ok], infl[ok]
    return R, infl


def port_returns(R: pd.DataFrame, w: dict) -> np.ndarray:
    """Constant mix rebalanced monthly (simplification, declared)."""
    v = np.zeros(len(R))
    for a, x in w.items():
        v = v + x * R[a].values
    return v


def pwr_all(r: np.ndarray, infl: np.ndarray, months: int) -> np.ndarray:
    """Perfect withdrawal rate (PWR) of every rolling window (step 1 month) of `months`.

    Annual withdrawal = rate x initial wealth, paid monthly (rate/12) at month end, indexed to CPI from the
    window start. Wealth after month t: W_t = G_t (1 - (rate/12) sum_{s<=t} c_s / G_s), with G = cumulative
    growth and c = CPI index (c_1 = 1 + infl_1). Exhaustion before the end <=> rate > PWR, where
    PWR = 12 / sum_{s<=N} c_s / G_s (W_t/G_t decreases in t). Vectorised with prefix sums of I/V.
    """
    lv = np.concatenate([[0.0], np.cumsum(np.log1p(r))])
    li = np.concatenate([[0.0], np.cumsum(np.log1p(infl))])
    x = np.exp(li[1:] - lv[1:])                       # I_s / V_s, s = 1..n
    S = np.concatenate([[0.0], np.cumsum(x)])
    n = len(r)
    i = np.arange(n - months + 1)
    tot = np.exp(lv[i] - li[i]) * (S[i + months] - S[i])
    return 12.0 / tot


def simulate(R: np.ndarray, infl: np.ndarray, starts: np.ndarray, months: int, rate: float, weights_fn,
             flex_cut: float = 0.0) -> dict:
    """Month-by-month wealth with indexed withdrawals, vectorised over window starts (initial wealth 1).

    weights_fn(k) -> weight vector for month k of the window (glidepath allowed; monthly rebalancing).
    flex_cut: after a 12-month block whose real portfolio return was negative, the next 12 monthly withdrawals
    are cut by flex_cut (spending flexibility rule, tested as a sensitivity).
    Returns exhausted flags, months survived, final real wealth.
    """
    m = len(starts)
    W = np.ones(m)
    cpi = np.ones(m)
    alive = np.ones(m, bool)
    survived = np.full(m, months)
    cut = np.zeros(m)
    blk_real = np.zeros(m)
    for k in range(months):
        t = starts + k
        rp = R[t] @ weights_fn(k)
        cpi = cpi * (1 + infl[t])
        blk_real += np.log1p(rp) - np.log1p(infl[t])
        W = W * (1 + rp) - rate / 12 * cpi * (1 - cut)
        newly = alive & (W <= 0)
        survived[newly] = k + 1
        alive &= W > 0
        W = np.where(alive, W, 0.0)
        if (k + 1) % 12 == 0:
            cut = np.where(blk_real < 0, flex_cut, 0.0)
            blk_real[:] = 0
    return {"exhausted": ~alive, "months_survived": survived, "final_real": W / cpi}


def first_k_real(r: np.ndarray, infl: np.ndarray, months: int, k: int) -> np.ndarray:
    """Annualised real return of the first k months of every rolling window of `months`."""
    real = np.log1p(r) - np.log1p(infl)
    c = np.concatenate([[0.0], np.cumsum(real)])
    n = len(r) - months + 1
    return np.expm1((c[k:k + n] - c[:n]) * 12 / k)


def longest_underwater(r: np.ndarray) -> tuple[int, bool]:
    dd = M.drawdown_series(r)
    best, cur, cens = 0, 0, False
    for i, d in enumerate(dd):
        if d > 1e-12:
            cur += 1
            if cur > best:
                best, cens = cur, i == len(dd) - 1
        else:
            cur = 0
    return best, cens


def fmt(x, d=3):
    return "" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{d}f}"
