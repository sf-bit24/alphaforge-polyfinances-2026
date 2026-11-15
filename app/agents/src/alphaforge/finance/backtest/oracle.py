"""HINDSIGHT oracle: best constant-mix (monthly rebalanced) weights for one window, knowing the future.

NOT INVESTABLE. Its only purpose is reverse engineering ("what would have been optimal
under this profile's constraints?") and measuring how far ex-ante strategies are from
the hindsight optimum. Every output carries hindsight=True.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .backtest import ConstraintProvider, evaluate
from .constraints import ConstraintSet
from .windows import Window

LABEL = "ORACLE (hindsight=True) - non investissable, sert a la retro-ingenierie"


def _penalty(metrics: dict, limits: dict) -> float:
    total = 0.0
    for limit, metric in (("max_vol", "volatility"), ("max_drawdown", "max_drawdown"), ("max_cvar_5", "cvar_5")):
        if limits.get(limit) is not None:
            total += max(0.0, metrics[metric] - limits[limit])
    return 50.0 * total


def _starting_points(constraints: ConstraintSet, n: int, n_random: int, rng: np.random.Generator) -> list[np.ndarray]:
    """Equal weights, a tilt towards each asset, then random Dirichlet mixes, each projected onto the constraints."""
    starts = [constraints.project(np.full(n, 1 / n))]
    for i in range(n):  # tilt towards each asset
        tilt = np.full(n, 0.2 / n)
        tilt[i] += 0.8
        starts.append(constraints.project(tilt))
    for _ in range(n_random):
        starts.append(constraints.project(rng.dirichlet(np.ones(n))))
    return starts


def _best_constant_mix(loss, starts: list[np.ndarray], constraints: ConstraintSet) -> np.ndarray:
    """Admissible weights with the lowest loss among the local optima reached from each starting point."""
    best = None
    for start in starts:
        result = minimize(
            loss,
            start,
            bounds=constraints.bounds(),
            constraints=constraints.scipy_constraints(),
            method="SLSQP",
            options={"ftol": 1e-9, "maxiter": 200},
        )
        weights = constraints.project(result.x)
        value = loss(weights)
        if best is None or value < best[0]:
            best = (value, weights)
    return best[1]


def oracle_window(  # noqa: PLR0913 - public signature (run.py and the engine tests pass these positionally)
    returns: pd.DataFrame,
    inflation: pd.Series,
    window: Window,
    profile: dict,
    provider: ConstraintProvider,
    seed: int = 42,
) -> dict:
    assets = list(returns.columns)
    window_returns = returns.loc[window.start : window.end]
    values = window_returns.values
    window_inflation = inflation.reindex(window_returns.index).values
    risk_free = window_returns[profile["cash_asset"]].values
    constraints = provider.for_window(window)  # look-through exposures: max over the window (conservative)
    limits = profile["risk_limits"]

    def loss(weights: np.ndarray) -> float:
        metrics = evaluate(values @ weights, window_inflation, risk_free, profile)
        score = metrics["score"]
        if not np.isfinite(score):
            score = -1e3
        return -(score - _penalty(metrics, limits))

    rng = np.random.default_rng(seed)
    starts = _starting_points(constraints, len(assets), int(profile["oracle"].get("n_starts", 6)), rng)
    weights = _best_constant_mix(loss, starts, constraints)
    metrics = evaluate(values @ weights, window_inflation, risk_free, profile)
    metrics.update({"turnover_ann": np.nan, "n_rebalances": window.n_months - 1, "fallback_months": 0})
    return {
        "metrics": metrics,
        "weights": dict(zip(assets, np.round(weights, 6).tolist(), strict=True)),
        "hindsight": True,
        "label": LABEL,
        "risk_limits_met": not metrics["risk_breaches"],
        "constraint_violations": constraints.violations(weights),
    }
