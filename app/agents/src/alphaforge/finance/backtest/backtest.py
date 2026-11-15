"""Monthly backtest of one strategy on one window (ex-ante: decisions use only past data)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .constraints import ConstraintSet
from .metrics import summary
from .strategies import Context, Strategy
from .windows import Window


class ConstraintProvider:
    """Builds (and caches) the ConstraintSet valid at a decision date.

    Constraints only change over time through time-varying look-through exposures
    (US_MKT industry shares); the exposure used for a decision in month t is the one
    observed at the end of month t-1.
    """

    def __init__(self, assets: list[str], config: dict):
        self.assets, self.config = assets, config
        self.dynamic = any("exposure" in group for group in config.get("groups") or [])
        self._static = None if self.dynamic else ConstraintSet(assets, config)
        self._cache: dict = {}

    def at(self, prev_month: pd.Timestamp | None) -> ConstraintSet:
        if not self.dynamic:
            return self._static
        if prev_month not in self._cache:
            self._cache[prev_month] = ConstraintSet(self.assets, self.config, date=prev_month)
        return self._cache[prev_month]

    def for_window(self, window: Window) -> ConstraintSet:
        if not self.dynamic:
            return self._static
        return ConstraintSet(self.assets, self.config, window=(window.start, window.end))


def flows_vector(profile: dict, inflation: np.ndarray) -> np.ndarray:
    flows = profile["flows"]
    base = np.full(len(inflation), float(flows.get("monthly", 0.0)))
    if flows.get("indexed_to_inflation", True):
        base = base * np.cumprod(1 + inflation)
    return base


def objective_score(metrics: dict, profile: dict) -> float:
    objective = profile["objective"]
    kind = objective["type"]
    if kind == "max_real_return":
        return metrics["ann_real_return"]
    if kind == "max_sharpe":
        return metrics["sharpe"]
    if kind == "max_return_over_cvar":
        return metrics["ann_return"] / max(metrics["cvar_5"], 1e-3)
    if kind == "min_shortfall":
        if objective.get("target_real_wealth") is not None:
            return metrics["final_real_wealth"] / float(objective["target_real_wealth"]) - 1
        return metrics["ann_real_return"] - float(objective["target_real_return"])
    raise ValueError(kind)


def missed_target(metrics: dict, profile: dict) -> bool | None:
    objective = profile["objective"]
    if objective.get("target_real_wealth") is not None:
        return bool(metrics["final_real_wealth"] < float(objective["target_real_wealth"]))
    if objective.get("target_real_return") is not None:
        return bool(metrics["ann_real_return"] < float(objective["target_real_return"]))
    return None


def risk_breaches(metrics: dict, profile: dict) -> list[str]:
    limits = profile["risk_limits"]
    breaches = []
    if limits.get("max_vol") is not None and metrics["volatility"] > limits["max_vol"]:
        breaches.append(f"vol {metrics['volatility']:.3f} > {limits['max_vol']}")
    if limits.get("max_drawdown") is not None and metrics["max_drawdown"] > limits["max_drawdown"]:
        breaches.append(f"maxDD {metrics['max_drawdown']:.3f} > {limits['max_drawdown']}")
    if limits.get("max_cvar_5") is not None and metrics["cvar_5"] > limits["max_cvar_5"]:
        breaches.append(f"CVaR5 {metrics['cvar_5']:.3f} > {limits['max_cvar_5']}")
    return breaches


def evaluate(portfolio_returns: np.ndarray, inflation: np.ndarray, risk_free: np.ndarray, profile: dict) -> dict:
    flows = flows_vector(profile, inflation)
    initial = float(profile["flows"].get("initial", 1.0))
    metrics = summary(portfolio_returns, inflation=inflation, rf=risk_free, initial=initial, flows=flows)
    metrics["score"] = objective_score(metrics, profile)
    metrics["missed_target"] = missed_target(metrics, profile)
    metrics["risk_breaches"] = risk_breaches(metrics, profile)
    return metrics


def _due(freq: str, i: int) -> bool:
    return {"monthly": True, "quarterly": i % 3 == 0, "annual": i % 12 == 0, "never": i == 0, "bands": True}[freq]


def _progress(freq: str, i: int, n: int) -> float:
    """Window progress seen by a decision taken in month i (0 = first decision, 1 = last one).

    Measured against the LAST scheduled decision month, not against n: otherwise a glidepath
    rebalanced annually over 120 months would trade for the last time at i=108 (progress 0.9)
    and never reach its end weights. With `never` there is a single decision -> progress 0.
    """
    last = max(j for j in range(n) if _due(freq, j))
    return i / last if last > 0 else 0.0


@dataclass
class _WindowRun:
    """Month-by-month simulation of one strategy on one window, with its trading counters."""

    returns: pd.DataFrame
    inflation: pd.Series
    window: Window
    strategy: Strategy
    profile: dict
    provider: ConstraintProvider
    cache: dict | None
    fallback: np.ndarray | None

    def __post_init__(self) -> None:
        self.assets = list(self.returns.columns)
        self.cash = self.profile["cash_asset"]
        rebalancing = self.strategy.rebalancing or self.profile["rebalancing"]
        self.frequency, self.band = rebalancing.get("frequency", "annual"), float(rebalancing.get("band", 0.05))
        self.cost_rate = float(self.profile.get("costs_bps", 0.0)) / 1e4
        self.months = self.returns.loc[self.window.start : self.window.end].index
        if len(self.months) != self.window.n_months:
            raise ValueError(f"window {self.window.label} not fully covered by data")
        self.first_position = self.returns.index.get_loc(self.window.start)
        self.turnover_sum, self.fallback_months, self.rebalances, self.drift_months = 0.0, 0, 0, 0
        self.in_fallback = False

    def _target(self, i: int, position: int, previous: pd.Timestamp | None) -> tuple[np.ndarray, bool]:
        """Projected target of month i and whether the strategy fell back. Cached across windows unless the target
        depends on the window's progress."""
        date = self.returns.index[position]
        key = (self.strategy.name, date)
        cacheable = self.cache is not None and not self.strategy.window_dependent
        if cacheable and key in self.cache:
            return self.cache[key]
        constraints = self.provider.at(previous)
        progress = _progress(self.frequency, i, len(self.months))
        context = Context(self.assets, self.cash, constraints, date, progress=progress, fallback=self.fallback)
        target = constraints.project(self.strategy.target(self.returns.iloc[:position], context))
        is_fallback = bool(context.info.get("fallback"))
        if cacheable:
            self.cache[key] = (target, is_fallback)
        return target, is_fallback

    def _decide(
        self, i: int, position: int, previous: pd.Timestamp | None, drift: np.ndarray | None
    ) -> tuple[np.ndarray, float, bool]:
        """Weights held in a decision month: the target, or the drifted weights while they stay inside the band.
        Returns (weights, trading cost, traded)."""
        target, is_fallback = self._target(i, position, previous)
        if drift is None:
            weights = target
        elif self.frequency == "bands" and np.max(np.abs(drift - target)) <= self.band:
            weights = drift
        else:
            weights = target
        if weights is not target:
            return weights, 0.0, False
        self.in_fallback = is_fallback
        if drift is None:
            return weights, 0.0, True
        traded_weight = np.abs(weights - drift).sum()
        self.turnover_sum += 0.5 * traded_weight
        self.rebalances += 1
        return weights, self.cost_rate * traded_weight, True

    def simulate(self) -> dict:
        n = len(self.months)
        values = self.returns.values
        portfolio = np.empty(n)
        drift = None
        history = np.empty((n, len(self.assets)))
        traded = np.zeros(n, dtype=bool)
        for i in range(n):
            position = self.first_position + i
            previous = self.returns.index[position - 1] if position > 0 else None
            if drift is None or _due(self.frequency, i):
                weights, cost, traded[i] = self._decide(i, position, previous, drift)
            else:
                weights, cost = drift, 0.0
            self.fallback_months += int(self.in_fallback)
            if not traded[i] and not self.provider.at(previous).is_feasible(weights, 1e-4):
                self.drift_months += 1  # constraints hold at trades; drifted weights may leave the set in between
            month_returns = values[position]
            gross = float(weights @ month_returns)
            portfolio[i] = gross - cost
            history[i] = weights
            drift = weights * (1 + month_returns) / (1 + gross) if (1 + gross) > 0 else weights
        return self._results(portfolio, traded, history)

    def _results(self, portfolio: np.ndarray, traded: np.ndarray, history: np.ndarray) -> dict:
        months = self.months
        inflation = self.inflation.reindex(months).values
        risk_free = self.returns.loc[months, self.cash].values
        metrics = evaluate(portfolio, inflation, risk_free, self.profile)
        metrics.update(
            {
                "turnover_ann": self.turnover_sum / (len(months) / 12),
                "n_rebalances": self.rebalances,
                "fallback_months": self.fallback_months,
                "drift_months_outside_constraints": self.drift_months,
            }
        )
        return {
            "metrics": metrics,
            "returns": pd.Series(portfolio, index=months),
            "traded": pd.Series(traded, index=months),
            "weights": pd.DataFrame(history, index=months, columns=self.assets),
        }


def run_window(  # noqa: PLR0913 - public signature (run.py, oracle and lookahead tests pass these positionally)
    returns: pd.DataFrame,
    inflation: pd.Series,
    window: Window,
    strategy: Strategy,
    profile: dict,
    provider: ConstraintProvider,
    cache: dict | None = None,
    fallback: np.ndarray | None = None,
) -> dict:
    """Simulate `strategy` over `window`. `returns` must contain history before the window (used by the
    strategy) and the window itself. Returns metrics + weight history."""
    return _WindowRun(returns, inflation, window, strategy, profile, provider, cache, fallback).simulate()
