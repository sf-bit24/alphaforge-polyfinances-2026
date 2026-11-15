"""Ex-ante allocation strategies.

Contract: `target(history, context) -> weights` where `history` contains ONLY monthly returns
strictly before the decision month (the backtester slices it; tests/test_lookahead.py
checks that changing future data never changes a decision). The returned weights are
then projected onto the profile's admissible set by the backtester.

If fewer than `min_history` months are available the strategy returns the profile's
`fallback_weights` (or equal weights) and the backtester counts the month as a fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .constraints import ConstraintSet


@dataclass
class Context:
    assets: list[str]
    cash_asset: str
    constraints: ConstraintSet
    date: pd.Timestamp  # decision month (its return is NOT in history)
    progress: float = 0.0  # 0 at the first decision of the window, 1 at the last scheduled one
    fallback: np.ndarray | None = None
    info: dict = field(default_factory=dict)

    @property
    def cash_index(self) -> int:
        return self.assets.index(self.cash_asset)


def _weight_vector(assets: list[str], weights: dict) -> np.ndarray:
    return np.array([float(weights.get(asset, 0.0)) for asset in assets])


def _equal_weights(context: Context) -> np.ndarray:
    return np.full(len(context.assets), 1 / len(context.assets))


def ledoit_wolf(returns: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf (2004) shrinkage of the sample covariance towards a scaled identity."""
    n_months, n_assets = returns.shape
    centered = returns - returns.mean(axis=0)
    sample = centered.T @ centered / n_months
    scale = np.trace(sample) / n_assets  # mu
    distance = np.sum((sample - scale * np.eye(n_assets)) ** 2)  # d^2
    error = sum(np.sum((np.outer(row, row) - sample) ** 2) for row in centered) / n_months**2  # b^2
    error = min(error, distance)
    shrinkage = error / distance if distance > 0 else 1.0  # delta
    return shrinkage * scale * np.eye(n_assets) + (1 - shrinkage) * sample


def _solve(objective, start: np.ndarray, constraints: ConstraintSet) -> np.ndarray:
    result = minimize(
        objective,
        start,
        bounds=constraints.bounds(),
        constraints=constraints.scipy_constraints(),
        method="SLSQP",
        options={"ftol": 1e-10, "maxiter": 300},
    )
    return result.x if result.success or constraints.is_feasible(result.x, 1e-5) else start


class Strategy:
    type = "base"
    rebalance_default = None  # None -> use profile rebalancing

    def __init__(self, name: str, params: dict | None = None, rebalancing: dict | None = None):
        self.name = name
        self.params = params or {}
        self.rebalancing = rebalancing
        self.min_history = int(self.params.get("min_history", self.params.get("lookback", 0)))
        self.window_dependent = False  # True if target depends on window progress (no cross-window cache)

    def target(self, history: pd.DataFrame, context: Context) -> np.ndarray:
        if len(history) < self.min_history:
            context.info["fallback"] = True
            return context.fallback if context.fallback is not None else _equal_weights(context)
        context.info["fallback"] = False
        return self._target(history, context)

    def _target(self, history, context):  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "type": self.type, "params": self.params, "rebalancing": self.rebalancing}


class Static(Strategy):
    """Fixed policy weights, rebalanced per the profile/strategy rebalancing rule."""

    type = "static"

    def _target(self, history, context):
        return _weight_vector(context.assets, self.params["weights"])


class SixtyForty(Strategy):
    """Equity share split equally among `equity` assets, the rest equally among `bonds`."""

    type = "sixty_forty"

    def _target(self, history, context):
        equity, bonds = self.params["equity"], self.params["bonds"]
        equity_share = float(self.params.get("equity_share", 0.6))
        weights = {asset: equity_share / len(equity) for asset in equity}
        for asset in bonds:
            weights[asset] = weights.get(asset, 0) + (1 - equity_share) / len(bonds)
        return _weight_vector(context.assets, weights)


class Glidepath(Strategy):
    """Linear interpolation from `start_weights` to `end_weights` as the horizon elapses."""

    type = "glidepath"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.window_dependent = True

    def _target(self, history, context):
        start = _weight_vector(context.assets, self.params["start_weights"])
        end = _weight_vector(context.assets, self.params["end_weights"])
        return (1 - context.progress) * start + context.progress * end


def _equal_risk_contribution(returns: np.ndarray, selected: np.ndarray, inverse_vol: np.ndarray) -> np.ndarray:
    """Weights whose risk contributions are equal among the `selected` assets (SLSQP from the inverse-vol mix)."""
    covariance = ledoit_wolf(returns)[np.ix_(selected, selected)]

    def contribution_dispersion(weights):
        variance = weights @ covariance @ weights
        contributions = weights * (covariance @ weights) / variance
        return np.sum((contributions - 1 / selected.sum()) ** 2)

    start = inverse_vol[selected] / inverse_vol[selected].sum()
    result = minimize(
        contribution_dispersion,
        start,
        bounds=[(1e-6, 1)] * selected.sum(),
        constraints=[{"type": "eq", "fun": lambda weights: weights.sum() - 1}],
        method="SLSQP",
    )
    weights = np.zeros(len(inverse_vol))
    weights[selected] = result.x
    return weights


class RiskParity(Strategy):
    """Inverse-volatility (default) or equal-risk-contribution weights on a trailing window."""

    type = "risk_parity"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lookback = int(self.params.get("lookback", 36))
        self.min_history = int(self.params.get("min_history", self.lookback))

    def _target(self, history, context):
        recent = history.iloc[-self.lookback :].values
        excluded = self.params.get("exclude", [])
        included = np.array([asset not in excluded for asset in context.assets]) & (context.constraints.ub > 0)
        vol = recent.std(axis=0, ddof=1)
        vol = np.where(vol > 1e-8, vol, np.nan)
        weights = np.where(included, 1 / vol, 0.0)
        weights = np.nan_to_num(weights)
        if self.params.get("method", "inverse_vol") == "erc":
            weights = _equal_risk_contribution(recent, included & (weights > 0), weights)
        return weights / weights.sum()


class MinVariance(Strategy):
    """Minimum variance under the profile constraints; Ledoit-Wolf covariance on a trailing window."""

    type = "min_variance"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lookback = int(self.params.get("lookback", 60))
        self.min_history = int(self.params.get("min_history", self.lookback))

    def _target(self, history, context):
        covariance = ledoit_wolf(history.iloc[-self.lookback :].values) * 12
        start = context.constraints.project(_equal_weights(context))
        return _solve(lambda x: x @ covariance @ x, start, context.constraints)


class MaxSharpe(Strategy):
    """Max ex-ante Sharpe: trailing mean excess return (shrunk to the cross-sectional mean) / LW vol."""

    type = "max_sharpe"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lookback = int(self.params.get("lookback", 60))
        self.min_history = int(self.params.get("min_history", self.lookback))

    def _mean_and_covariance(self, history, context):
        """Annualised mean excess return over cash, shrunk towards its cross-sectional mean, and LW covariance."""
        recent = history.iloc[-self.lookback :]
        excess = recent.sub(recent[context.cash_asset], axis=0).values
        mean = excess.mean(axis=0) * 12
        shrink = float(self.params.get("mu_shrink", 0.5))
        mean = (1 - shrink) * mean + shrink * mean.mean()
        return mean, ledoit_wolf(recent.values) * 12

    def _target(self, history, context):
        mean, covariance = self._mean_and_covariance(history, context)
        start = context.constraints.project(_equal_weights(context))
        return _solve(lambda x: -(mean @ x) / np.sqrt(x @ covariance @ x + 1e-12), start, context.constraints)


class MeanVariance(MaxSharpe):
    """Mean-variance utility mu.w - (risk_aversion/2) w'Cw with shrunk mu and Ledoit-Wolf C."""

    type = "mean_variance"

    def _target(self, history, context):
        mean, covariance = self._mean_and_covariance(history, context)
        risk_aversion = float(self.params.get("risk_aversion", 4.0))
        start = context.constraints.project(_equal_weights(context))
        return _solve(lambda x: -(mean @ x) + 0.5 * risk_aversion * (x @ covariance @ x), start, context.constraints)


class TrendFilter(Strategy):
    """Base weights; any risky asset whose total-return index is below its `ma_months` moving
    average at the end of the previous month has its weight moved to the cash asset."""

    type = "trend_filter"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ma_months = int(self.params.get("ma_months", 10))
        self.min_history = int(self.params.get("min_history", self.ma_months))

    def _target(self, history, context):
        weights = _weight_vector(context.assets, self.params["base_weights"])
        total_return_index = (1 + history.iloc[-self.ma_months :]).cumprod()
        below = total_return_index.iloc[-1] < total_return_index.mean()
        cash = context.cash_index
        for i, asset in enumerate(context.assets):
            if i != cash and asset not in self.params.get("always_hold", []) and bool(below[asset]):
                weights[cash] += weights[i]
                weights[i] = 0.0
        return weights


class Momentum(Strategy):
    """Relative momentum: equal weight on the `top_k` assets of `candidates` with the best trailing
    `lookback`-month return (skipping `skip` recent months); with `absolute=True` an asset whose
    momentum is below cash is replaced by cash. Optional `core_weights` are held permanently and
    the momentum sleeve gets the remainder."""

    type = "momentum"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lookback = int(self.params.get("lookback", 12))
        self.skip = int(self.params.get("skip", 0))
        self.min_history = int(self.params.get("min_history", self.lookback + self.skip))

    def _target(self, history, context):
        candidates = self.params.get("candidates") or [asset for asset in context.assets if asset != context.cash_asset]
        recent = history.iloc[len(history) - self.lookback - self.skip : len(history) - self.skip]
        momentum = (1 + recent).prod() - 1
        core = _weight_vector(context.assets, self.params.get("core_weights", {}))
        sleeve = 1 - core.sum()
        top_k = int(self.params.get("top_k", 2))
        ranked = momentum[candidates].sort_values(ascending=False).index[:top_k]
        weights = core.copy()
        for asset in ranked:
            position = context.assets.index(asset)
            if self.params.get("absolute", True) and momentum[asset] < momentum[context.cash_asset]:
                position = context.cash_index
            weights[position] += sleeve / top_k
        return weights


REGISTRY = {
    strategy.type: strategy
    for strategy in (
        Static,
        SixtyForty,
        Glidepath,
        RiskParity,
        MinVariance,
        MaxSharpe,
        MeanVariance,
        TrendFilter,
        Momentum,
    )
}


def build_strategy(spec: dict) -> Strategy:
    return REGISTRY[spec["type"]](spec["name"], spec.get("params"), spec.get("rebalancing"))
