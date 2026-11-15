"""Pure performance / risk metrics on MONTHLY simple returns (decimal).

Conventions: annualisation with 12 periods; drawdown, VaR and CVaR are returned as
POSITIVE loss numbers (0.25 = -25 %); empty input returns NaN. `r` is always the
series of monthly returns (the public signatures keep that short name).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PERIODS_PER_YEAR = 12


def _as_array(values) -> np.ndarray:
    return np.asarray(values, dtype=float)


def cumulative_growth(r) -> float:
    r = _as_array(r)
    return float(np.prod(1 + r)) if r.size else np.nan


def annualized_return(r) -> float:
    r = _as_array(r)
    if r.size == 0:
        return np.nan
    growth = np.prod(1 + r)
    return float(growth ** (PERIODS_PER_YEAR / r.size) - 1) if growth > 0 else -1.0


def real_returns(r, inflation) -> np.ndarray:
    return (1 + _as_array(r)) / (1 + _as_array(inflation)) - 1


def annualized_real_return(r, inflation) -> float:
    return annualized_return(real_returns(r, inflation))


def volatility(r) -> float:
    r = _as_array(r)
    return float(np.std(r, ddof=1) * np.sqrt(PERIODS_PER_YEAR)) if r.size > 1 else np.nan


def drawdown_series(r) -> np.ndarray:
    wealth = np.cumprod(1 + _as_array(r))
    peak = np.maximum.accumulate(np.concatenate([[1.0], wealth]))[1:]
    return 1 - wealth / peak


def max_drawdown(r) -> float:
    r = _as_array(r)
    return float(drawdown_series(r).max()) if r.size else np.nan


def recovery_months(r) -> float:
    """Months from the max-drawdown trough until the previous peak is regained (NaN if never)."""
    r = _as_array(r)
    if r.size == 0:
        return np.nan
    drawdowns = drawdown_series(r)
    if drawdowns.max() <= 0:
        return 0.0
    trough = int(np.argmax(drawdowns))
    after = np.where(drawdowns[trough:] <= 1e-12)[0]
    return float(after[0]) if after.size else np.nan


def max_underwater_months(r) -> int:
    """Longest run of consecutive months below the running peak."""
    drawdowns = drawdown_series(_as_array(r))
    best = current = 0
    for drawdown in drawdowns:
        current = current + 1 if drawdown > 1e-12 else 0
        best = max(best, current)
    return int(best)


def _excess_returns(r, rf) -> np.ndarray:
    return _as_array(r) - _as_array(rf) if np.ndim(rf) else _as_array(r) - rf


def sharpe(r, rf=0.0) -> float:
    excess = _excess_returns(r, rf)
    deviation = np.std(excess, ddof=1) if excess.size > 1 else np.nan
    return float(np.mean(excess) / deviation * np.sqrt(PERIODS_PER_YEAR)) if deviation and deviation > 0 else np.nan


def sortino(r, rf=0.0) -> float:
    excess = _excess_returns(r, rf)
    downside = np.sqrt(np.mean(np.minimum(excess, 0) ** 2)) if excess.size else np.nan
    if not (downside and downside > 0):
        return np.nan
    return float(np.mean(excess) * PERIODS_PER_YEAR / (downside * np.sqrt(PERIODS_PER_YEAR)))


def calmar(r) -> float:
    drawdown = max_drawdown(r)
    return float(annualized_return(r) / drawdown) if drawdown and drawdown > 0 else np.nan


def var_cvar(r, alpha: float = 0.05) -> tuple[float, float]:
    """Historical monthly VaR and CVaR (expected shortfall) at level alpha, as positive losses."""
    r = _as_array(r)
    if r.size == 0:
        return np.nan, np.nan
    quantile = np.quantile(r, alpha, method="lower")
    tail = r[r <= quantile]
    return float(-quantile), float(-tail.mean())


def worst_window_return(r, months: int = 12) -> float:
    """Worst compounded return over any `months` consecutive months (NaN if too short)."""
    r = _as_array(r)
    if r.size < months:
        return np.nan
    log_returns = np.log1p(r)
    cumulative = np.concatenate([[0.0], np.cumsum(log_returns)])
    return float(np.expm1((cumulative[months:] - cumulative[:-months]).min()))


def shortfall_probability(values, target) -> float:
    outcomes = _as_array(values)
    outcomes = outcomes[~np.isnan(outcomes)]
    return float(np.mean(outcomes < target)) if outcomes.size else np.nan


def wealth_path(r, initial: float = 1.0, flows=None) -> np.ndarray:
    """W_t = max(0, W_{t-1} (1 + r_t) + flow_t); flows at month end (positive = contribution)."""
    r = _as_array(r)
    monthly_flows = np.zeros_like(r) if flows is None else _as_array(flows)
    path = np.empty_like(r)
    current = float(initial)
    for i in range(r.size):
        current = max(0.0, current * (1 + r[i]) + monthly_flows[i]) if current > 0 else 0.0
        path[i] = current
    return path


def final_wealth(r, initial: float = 1.0, flows=None) -> float:
    path = wealth_path(r, initial, flows)
    return float(path[-1]) if path.size else float(initial)


def turnover(weights_before: np.ndarray, weights_after: np.ndarray) -> float:
    """One-way turnover = 0.5 * sum |w_after - w_before|."""
    return float(0.5 * np.abs(_as_array(weights_after) - _as_array(weights_before)).sum())


def correlation(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.corr()


def summary(r, inflation=None, rf=None, initial: float = 1.0, flows=None) -> dict:
    """Standard metric bundle used in every result row."""
    r = _as_array(r)
    monthly_inflation = _as_array(inflation) if inflation is not None else np.zeros_like(r)
    risk_free = _as_array(rf) if rf is not None else np.zeros_like(r)
    value_at_risk, expected_shortfall = var_cvar(r)
    deflator = np.cumprod(1 + monthly_inflation)
    path = wealth_path(r, initial, flows)
    return {
        "ann_return": annualized_return(r),
        "ann_real_return": annualized_real_return(r, monthly_inflation),
        "volatility": volatility(r),
        "max_drawdown": max_drawdown(r),
        "recovery_months": recovery_months(r),
        "max_underwater_months": max_underwater_months(r),
        "sharpe": sharpe(r, risk_free),
        "sortino": sortino(r, risk_free),
        "calmar": calmar(r),
        "var_5": value_at_risk,
        "cvar_5": expected_shortfall,
        "worst_12m": worst_window_return(r, 12),
        "final_wealth": float(path[-1]) if path.size else initial,
        "final_real_wealth": float(path[-1] / deflator[-1]) if path.size else initial,
        "depleted": bool(path.size and path[-1] <= 0),
        "n_months": int(r.size),
    }
