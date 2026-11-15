"""Ex-ante allocation strategies.

Contract: `target(hist, ctx) -> weights` where `hist` contains ONLY monthly returns
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
    cs: ConstraintSet
    date: pd.Timestamp            # decision month (its return is NOT in hist)
    progress: float = 0.0         # 0 at the first decision of the window, 1 at the last scheduled one
    fallback: np.ndarray | None = None
    info: dict = field(default_factory=dict)

    @property
    def cash_idx(self) -> int:
        return self.assets.index(self.cash_asset)


def _vec(assets, weights: dict) -> np.ndarray:
    return np.array([float(weights.get(a, 0.0)) for a in assets])


def ledoit_wolf(x: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf (2004) shrinkage of the sample covariance towards a scaled identity."""
    t, n = x.shape
    xc = x - x.mean(axis=0)
    s = xc.T @ xc / t
    mu = np.trace(s) / n
    d2 = np.sum((s - mu * np.eye(n)) ** 2)
    b2 = sum(np.sum((np.outer(r, r) - s) ** 2) for r in xc) / t ** 2
    b2 = min(b2, d2)
    delta = b2 / d2 if d2 > 0 else 1.0
    return delta * mu * np.eye(n) + (1 - delta) * s


def _solve(fun, x0, cs: ConstraintSet) -> np.ndarray:
    res = minimize(fun, x0, bounds=cs.bounds(), constraints=cs.scipy_constraints(), method="SLSQP",
                   options={"ftol": 1e-10, "maxiter": 300})
    w = res.x if res.success or cs.is_feasible(res.x, 1e-5) else x0
    return w


class Strategy:
    type = "base"
    rebalance_default = None  # None -> use profile rebalancing

    def __init__(self, name: str, params: dict | None = None, rebalancing: dict | None = None):
        self.name = name
        self.params = params or {}
        self.rebalancing = rebalancing
        self.min_history = int(self.params.get("min_history", self.params.get("lookback", 0)))
        self.window_dependent = False  # True if target depends on window progress (no cross-window cache)

    def target(self, hist: pd.DataFrame, ctx: Context) -> np.ndarray:
        if len(hist) < self.min_history:
            ctx.info["fallback"] = True
            return ctx.fallback if ctx.fallback is not None else np.full(len(ctx.assets), 1 / len(ctx.assets))
        ctx.info["fallback"] = False
        return self._target(hist, ctx)

    def _target(self, hist, ctx):  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "type": self.type, "params": self.params, "rebalancing": self.rebalancing}


class Static(Strategy):
    """Fixed policy weights, rebalanced per the profile/strategy rebalancing rule."""
    type = "static"

    def _target(self, hist, ctx):
        return _vec(ctx.assets, self.params["weights"])


class SixtyForty(Strategy):
    """Equity share split equally among `equity` assets, the rest equally among `bonds`."""
    type = "sixty_forty"

    def _target(self, hist, ctx):
        eq, bd = self.params["equity"], self.params["bonds"]
        s = float(self.params.get("equity_share", 0.6))
        w = {a: s / len(eq) for a in eq}
        for a in bd:
            w[a] = w.get(a, 0) + (1 - s) / len(bd)
        return _vec(ctx.assets, w)


class Glidepath(Strategy):
    """Linear interpolation from `start_weights` to `end_weights` as the horizon elapses."""
    type = "glidepath"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.window_dependent = True

    def _target(self, hist, ctx):
        w0, w1 = _vec(ctx.assets, self.params["start_weights"]), _vec(ctx.assets, self.params["end_weights"])
        return (1 - ctx.progress) * w0 + ctx.progress * w1


class RiskParity(Strategy):
    """Inverse-volatility (default) or equal-risk-contribution weights on a trailing window."""
    type = "risk_parity"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.lookback = int(self.params.get("lookback", 36))
        self.min_history = int(self.params.get("min_history", self.lookback))

    def _target(self, hist, ctx):
        x = hist.iloc[-self.lookback:].values
        incl = np.array([a not in self.params.get("exclude", []) for a in ctx.assets]) & (ctx.cs.ub > 0)
        vol = x.std(axis=0, ddof=1)
        vol = np.where(vol > 1e-8, vol, np.nan)
        w = np.where(incl, 1 / vol, 0.0)
        w = np.nan_to_num(w)
        if self.params.get("method", "inverse_vol") == "erc":
            cov = ledoit_wolf(x)
            m = incl & (w > 0)
            c = cov[np.ix_(m, m)]

            def f(v):
                p = v @ c @ v
                rc = v * (c @ v) / p
                return np.sum((rc - 1 / m.sum()) ** 2)
            v0 = w[m] / w[m].sum()
            r = minimize(
                f,
                v0,
                bounds=[(1e-6, 1)] * m.sum(),
                constraints=[{"type": "eq", "fun": lambda v: v.sum() - 1}],
                method="SLSQP",
            )
            w = np.zeros(len(ctx.assets))
            w[m] = r.x
        return w / w.sum()


class MinVariance(Strategy):
    """Minimum variance under the profile constraints; Ledoit-Wolf covariance on a trailing window."""

    type = "min_variance"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.lookback = int(self.params.get("lookback", 60))
        self.min_history = int(self.params.get("min_history", self.lookback))

    def _target(self, hist, ctx):
        c = ledoit_wolf(hist.iloc[-self.lookback :].values) * 12
        x0 = ctx.cs.project(np.full(len(ctx.assets), 1 / len(ctx.assets)))
        return _solve(lambda w: w @ c @ w, x0, ctx.cs)


class MaxSharpe(Strategy):
    """Max ex-ante Sharpe: trailing mean excess return (shrunk to the cross-sectional mean) / LW vol."""

    type = "max_sharpe"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.lookback = int(self.params.get("lookback", 60))
        self.min_history = int(self.params.get("min_history", self.lookback))

    def _mu_cov(self, hist, ctx):
        x = hist.iloc[-self.lookback :]
        ex = x.sub(x[ctx.cash_asset], axis=0).values
        mu = ex.mean(axis=0) * 12
        k = float(self.params.get("mu_shrink", 0.5))
        mu = (1 - k) * mu + k * mu.mean()
        return mu, ledoit_wolf(x.values) * 12

    def _target(self, hist, ctx):
        mu, c = self._mu_cov(hist, ctx)
        x0 = ctx.cs.project(np.full(len(ctx.assets), 1 / len(ctx.assets)))
        return _solve(lambda w: -(mu @ w) / np.sqrt(w @ c @ w + 1e-12), x0, ctx.cs)


class MeanVariance(MaxSharpe):
    """Mean-variance utility mu.w - (risk_aversion/2) w'Cw with shrunk mu and Ledoit-Wolf C."""

    type = "mean_variance"

    def _target(self, hist, ctx):
        mu, c = self._mu_cov(hist, ctx)
        lam = float(self.params.get("risk_aversion", 4.0))
        x0 = ctx.cs.project(np.full(len(ctx.assets), 1 / len(ctx.assets)))
        return _solve(lambda w: -(mu @ w) + 0.5 * lam * (w @ c @ w), x0, ctx.cs)


class TrendFilter(Strategy):
    """Base weights; any risky asset whose total-return index is below its `ma_months` moving
    average at the end of the previous month has its weight moved to the cash asset."""

    type = "trend_filter"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.ma = int(self.params.get("ma_months", 10))
        self.min_history = int(self.params.get("min_history", self.ma))

    def _target(self, hist, ctx):
        w = _vec(ctx.assets, self.params["base_weights"])
        idx = (1 + hist.iloc[-self.ma :]).cumprod()
        below = idx.iloc[-1] < idx.mean()
        ci = ctx.cash_idx
        for i, a in enumerate(ctx.assets):
            if i != ci and a not in self.params.get("always_hold", []) and bool(below[a]):
                w[ci] += w[i]
                w[i] = 0.0
        return w


class Momentum(Strategy):
    """Relative momentum: equal weight on the `top_k` assets of `candidates` with the best trailing
    `lookback`-month return (skipping `skip` recent months); with `absolute=True` an asset whose
    momentum is below cash is replaced by cash. Optional `core_weights` are held permanently and
    the momentum sleeve gets the remainder."""

    type = "momentum"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.lb = int(self.params.get("lookback", 12))
        self.skip = int(self.params.get("skip", 0))
        self.min_history = int(self.params.get("min_history", self.lb + self.skip))

    def _target(self, hist, ctx):
        cand = self.params.get("candidates") or [a for a in ctx.assets if a != ctx.cash_asset]
        x = hist.iloc[len(hist) - self.lb - self.skip : len(hist) - self.skip]
        mom = (1 + x).prod() - 1
        core = _vec(ctx.assets, self.params.get("core_weights", {}))
        sleeve = 1 - core.sum()
        k = int(self.params.get("top_k", 2))
        ranked = mom[cand].sort_values(ascending=False).index[:k]
        w = core.copy()
        for a in ranked:
            j = ctx.assets.index(a)
            if self.params.get("absolute", True) and mom[a] < mom[ctx.cash_asset]:
                j = ctx.cash_idx
            w[j] += sleeve / k
        return w


REGISTRY = {
    c.type: c
    for c in (Static, SixtyForty, Glidepath, RiskParity, MinVariance, MaxSharpe, MeanVariance, TrendFilter, Momentum)
}


def build_strategy(spec: dict) -> Strategy:
    return REGISTRY[spec["type"]](spec["name"], spec.get("params"), spec.get("rebalancing"))
