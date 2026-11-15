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
from .windows import Window

LABEL = "ORACLE (hindsight=True) - non investissable, sert a la retro-ingenierie"


def _penalty(m: dict, lim: dict) -> float:
    p = 0.0
    for key, mk in (("max_vol", "volatility"), ("max_drawdown", "max_drawdown"), ("max_cvar_5", "cvar_5")):
        if lim.get(key) is not None:
            p += max(0.0, m[mk] - lim[key])
    return 50.0 * p


def oracle_window(R: pd.DataFrame, infl: pd.Series, window: Window, profile: dict, provider: ConstraintProvider,
                  seed: int = 42) -> dict:
    assets = list(R.columns)
    Rw = R.loc[window.start:window.end]
    X = Rw.values
    inf = infl.reindex(Rw.index).values
    rf = Rw[profile["cash_asset"]].values
    cs = provider.for_window(window)  # look-through exposures: max over the window (conservative)
    lim = profile["risk_limits"]

    def f(w):
        m = evaluate(X @ w, inf, rf, profile)
        s = m["score"]
        if not np.isfinite(s):
            s = -1e3
        return -(s - _penalty(m, lim))

    rng = np.random.default_rng(seed)
    n = len(assets)
    starts = [cs.project(np.full(n, 1 / n))]
    for i in range(n):  # tilt towards each asset
        e = np.full(n, 0.2 / n)
        e[i] += 0.8
        starts.append(cs.project(e))
    for _ in range(int(profile["oracle"].get("n_starts", 6))):
        starts.append(cs.project(rng.dirichlet(np.ones(n))))
    best = None
    for x0 in starts:
        res = minimize(f, x0, bounds=cs.bounds(), constraints=cs.scipy_constraints(), method="SLSQP",
                       options={"ftol": 1e-9, "maxiter": 200})
        w = cs.project(res.x)
        val = f(w)
        if best is None or val < best[0]:
            best = (val, w)
    w = best[1]
    m = evaluate(X @ w, inf, rf, profile)
    m.update({"turnover_ann": np.nan, "n_rebalances": window.n_months - 1, "fallback_months": 0})
    feasible_risk = not m["risk_breaches"]
    return {"metrics": m, "weights": dict(zip(assets, np.round(w, 6).tolist())), "hindsight": True,
            "label": LABEL, "risk_limits_met": feasible_risk, "constraint_violations": cs.violations(w)}
