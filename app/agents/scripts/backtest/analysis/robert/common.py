"""Shared helpers for Robert's analysis scripts (imports the shared engine, never modifies it).

SIMULATION ONLY - historical reconstructions, not forecasts, not financial advice.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from alphaforge.finance.backtest import metrics as M
from alphaforge.finance.backtest.data import data_version
from alphaforge.finance.backtest.run import DISCLAIMER, _clean, engine_hash

BT = Path(__file__).resolve().parents[2]          # app/agents/scripts/backtest
OUT = BT / "results" / "robert_analysis"
OUT.mkdir(parents=True, exist_ok=True)


def write_trace(name: str, payload: dict, params: dict) -> Path:
    """Write a JSON trace with data/engine hashes (same provenance fields as engine.run)."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace = {"run_id": name, "created_utc": stamp, "disclaimer": DISCLAIMER, "engine_sha256": engine_hash(),
             "data_version": data_version(), "script": str(Path(__file__).parent.name), "params": params,
             "results": payload}
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(_clean(trace), indent=1, default=str))
    return p


def underwater_episodes(r: np.ndarray) -> list[dict]:
    """Drawdown episodes: start index (first month below peak), trough, recovery (None if censored)."""
    dd = M.drawdown_series(r)
    eps, i, n = [], 0, len(dd)
    while i < n:
        if dd[i] > 1e-12:
            s = i
            while i < n and dd[i] > 1e-12:
                i += 1
            seg = dd[s:i]
            eps.append({"start": s, "trough": s + int(np.argmax(seg)), "depth": float(seg.max()),
                        "end": i if i < n else None, "months": i - s, "censored": i >= n})
        else:
            i += 1
    return eps


def longest_underwater(r: np.ndarray) -> tuple[int, bool]:
    eps = underwater_episodes(r)
    if not eps:
        return 0, False
    e = max(eps, key=lambda x: x["months"])
    return int(e["months"]), bool(e["censored"])


def rolling_real(port: np.ndarray, infl: np.ndarray, months: int) -> np.ndarray:
    """Annualised real return of every rolling window of `months` (step 1 month)."""
    real = np.log1p(port) - np.log1p(infl)
    c = np.concatenate([[0.0], np.cumsum(real)])
    tot = c[months:] - c[:-months]
    return np.expm1(tot * 12 / months)


def rolling_maxdd(port: np.ndarray, months: int, step: int = 1) -> np.ndarray:
    return np.array([M.max_drawdown(port[i:i + months]) for i in range(0, len(port) - months + 1, step)])
