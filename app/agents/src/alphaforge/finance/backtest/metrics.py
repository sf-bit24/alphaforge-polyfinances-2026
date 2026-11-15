"""Pure performance / risk metrics on MONTHLY simple returns (decimal).

Conventions: annualisation with 12 periods; drawdown, VaR and CVaR are returned as
POSITIVE loss numbers (0.25 = -25 %); empty input returns NaN.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

P = 12


def _a(r) -> np.ndarray:
    return np.asarray(r, dtype=float)


def cumulative_growth(r) -> float:
    r = _a(r)
    return float(np.prod(1 + r)) if r.size else np.nan


def annualized_return(r) -> float:
    r = _a(r)
    if r.size == 0:
        return np.nan
    g = np.prod(1 + r)
    return float(g ** (P / r.size) - 1) if g > 0 else -1.0


def real_returns(r, inflation) -> np.ndarray:
    return (1 + _a(r)) / (1 + _a(inflation)) - 1


def annualized_real_return(r, inflation) -> float:
    return annualized_return(real_returns(r, inflation))


def volatility(r) -> float:
    r = _a(r)
    return float(np.std(r, ddof=1) * np.sqrt(P)) if r.size > 1 else np.nan


def drawdown_series(r) -> np.ndarray:
    w = np.cumprod(1 + _a(r))
    peak = np.maximum.accumulate(np.concatenate([[1.0], w]))[1:]
    return 1 - w / peak


def max_drawdown(r) -> float:
    r = _a(r)
    return float(drawdown_series(r).max()) if r.size else np.nan


def recovery_months(r) -> float:
    """Months from the max-drawdown trough until the previous peak is regained (NaN if never)."""
    r = _a(r)
    if r.size == 0:
        return np.nan
    dd = drawdown_series(r)
    if dd.max() <= 0:
        return 0.0
    trough = int(np.argmax(dd))
    after = np.where(dd[trough:] <= 1e-12)[0]
    return float(after[0]) if after.size else np.nan


def max_underwater_months(r) -> int:
    """Longest run of consecutive months below the running peak."""
    dd = drawdown_series(_a(r))
    best = cur = 0
    for x in dd:
        cur = cur + 1 if x > 1e-12 else 0
        best = max(best, cur)
    return int(best)


def sharpe(r, rf=0.0) -> float:
    ex = _a(r) - _a(rf) if np.ndim(rf) else _a(r) - rf
    s = np.std(ex, ddof=1) if ex.size > 1 else np.nan
    return float(np.mean(ex) / s * np.sqrt(P)) if s and s > 0 else np.nan


def sortino(r, rf=0.0) -> float:
    ex = _a(r) - _a(rf) if np.ndim(rf) else _a(r) - rf
    dd = np.sqrt(np.mean(np.minimum(ex, 0) ** 2)) if ex.size else np.nan
    return float(np.mean(ex) * P / (dd * np.sqrt(P))) if dd and dd > 0 else np.nan


def calmar(r) -> float:
    mdd = max_drawdown(r)
    return float(annualized_return(r) / mdd) if mdd and mdd > 0 else np.nan


def var_cvar(r, alpha: float = 0.05) -> tuple[float, float]:
    """Historical monthly VaR and CVaR (expected shortfall) at level alpha, as positive losses."""
    r = _a(r)
    if r.size == 0:
        return np.nan, np.nan
    q = np.quantile(r, alpha, method="lower")
    tail = r[r <= q]
    return float(-q), float(-tail.mean())


def worst_window_return(r, months: int = 12) -> float:
    """Worst compounded return over any `months` consecutive months (NaN if too short)."""
    r = _a(r)
    if r.size < months:
        return np.nan
    lg = np.log1p(r)
    c = np.concatenate([[0.0], np.cumsum(lg)])
    return float(np.expm1((c[months:] - c[:-months]).min()))


def shortfall_probability(values, target) -> float:
    v = _a(values)
    v = v[~np.isnan(v)]
    return float(np.mean(v < target)) if v.size else np.nan


def wealth_path(r, initial: float = 1.0, flows=None) -> np.ndarray:
    """W_t = max(0, W_{t-1} (1 + r_t) + flow_t); flows at month end (positive = contribution)."""
    r = _a(r)
    f = np.zeros_like(r) if flows is None else _a(flows)
    w = np.empty_like(r)
    cur = float(initial)
    for i in range(r.size):
        cur = max(0.0, cur * (1 + r[i]) + f[i]) if cur > 0 else 0.0
        w[i] = cur
    return w


def final_wealth(r, initial: float = 1.0, flows=None) -> float:
    w = wealth_path(r, initial, flows)
    return float(w[-1]) if w.size else float(initial)


def turnover(weights_before: np.ndarray, weights_after: np.ndarray) -> float:
    """One-way turnover = 0.5 * sum |w_after - w_before|."""
    return float(0.5 * np.abs(_a(weights_after) - _a(weights_before)).sum())


def correlation(df: pd.DataFrame) -> pd.DataFrame:
    return df.corr()


def summary(r, inflation=None, rf=None, initial: float = 1.0, flows=None, target_real_return=None) -> dict:
    """Standard metric bundle used in every result row."""
    r = _a(r)
    infl = _a(inflation) if inflation is not None else np.zeros_like(r)
    rf_ = _a(rf) if rf is not None else np.zeros_like(r)
    v, cv = var_cvar(r)
    deflator = np.cumprod(1 + infl)
    w = wealth_path(r, initial, flows)
    out = {
        "ann_return": annualized_return(r),
        "ann_real_return": annualized_real_return(r, infl),
        "volatility": volatility(r),
        "max_drawdown": max_drawdown(r),
        "recovery_months": recovery_months(r),
        "max_underwater_months": max_underwater_months(r),
        "sharpe": sharpe(r, rf_),
        "sortino": sortino(r, rf_),
        "calmar": calmar(r),
        "var_5": v,
        "cvar_5": cv,
        "worst_12m": worst_window_return(r, 12),
        "final_wealth": float(w[-1]) if w.size else initial,
        "final_real_wealth": float(w[-1] / deflator[-1]) if w.size else initial,
        "depleted": bool(w.size and w[-1] <= 0),
        "n_months": int(r.size),
    }
    if target_real_return is not None:
        out["missed_target"] = bool(out["ann_real_return"] < target_real_return)
    return out
