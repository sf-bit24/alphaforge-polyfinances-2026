"""Monthly backtest of one strategy on one window (ex-ante: decisions use only past data)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import metrics as M
from .constraints import ConstraintSet
from .strategies import Context, Strategy
from .windows import Window


class ConstraintProvider:
    """Builds (and caches) the ConstraintSet valid at a decision date.

    Constraints only change over time through time-varying look-through exposures
    (US_MKT industry shares); the exposure used for a decision in month t is the one
    observed at the end of month t-1.
    """

    def __init__(self, assets: list[str], cfg: dict):
        self.assets, self.cfg = assets, cfg
        self.dynamic = any("exposure" in g for g in cfg.get("groups") or [])
        self._static = None if self.dynamic else ConstraintSet(assets, cfg)
        self._cache: dict = {}

    def at(self, prev_month: pd.Timestamp | None) -> ConstraintSet:
        if not self.dynamic:
            return self._static
        if prev_month not in self._cache:
            self._cache[prev_month] = ConstraintSet(self.assets, self.cfg, date=prev_month)
        return self._cache[prev_month]

    def for_window(self, w: Window) -> ConstraintSet:
        if not self.dynamic:
            return self._static
        return ConstraintSet(self.assets, self.cfg, window=(w.start, w.end))


def flows_vector(profile: dict, infl: np.ndarray) -> np.ndarray:
    f = profile["flows"]
    n = len(infl)
    base = np.full(n, float(f.get("monthly", 0.0)))
    if f.get("indexed_to_inflation", True):
        base = base * np.cumprod(1 + infl)
    return base


def objective_score(m: dict, profile: dict) -> float:
    o = profile["objective"]
    t = o["type"]
    if t == "max_real_return":
        return m["ann_real_return"]
    if t == "max_sharpe":
        return m["sharpe"]
    if t == "max_return_over_cvar":
        return m["ann_return"] / max(m["cvar_5"], 1e-3)
    if t == "min_shortfall":
        if o.get("target_real_wealth") is not None:
            return m["final_real_wealth"] / float(o["target_real_wealth"]) - 1
        return m["ann_real_return"] - float(o["target_real_return"])
    raise ValueError(t)


def missed_target(m: dict, profile: dict) -> bool | None:
    o = profile["objective"]
    if o.get("target_real_wealth") is not None:
        return bool(m["final_real_wealth"] < float(o["target_real_wealth"]))
    if o.get("target_real_return") is not None:
        return bool(m["ann_real_return"] < float(o["target_real_return"]))
    return None


def risk_breaches(m: dict, profile: dict) -> list[str]:
    lim = profile["risk_limits"]
    out = []
    if lim.get("max_vol") is not None and m["volatility"] > lim["max_vol"]:
        out.append(f"vol {m['volatility']:.3f} > {lim['max_vol']}")
    if lim.get("max_drawdown") is not None and m["max_drawdown"] > lim["max_drawdown"]:
        out.append(f"maxDD {m['max_drawdown']:.3f} > {lim['max_drawdown']}")
    if lim.get("max_cvar_5") is not None and m["cvar_5"] > lim["max_cvar_5"]:
        out.append(f"CVaR5 {m['cvar_5']:.3f} > {lim['max_cvar_5']}")
    return out


def evaluate(port_r: np.ndarray, infl: np.ndarray, rf: np.ndarray, profile: dict) -> dict:
    flows = flows_vector(profile, infl)
    m = M.summary(port_r, inflation=infl, rf=rf, initial=float(profile["flows"].get("initial", 1.0)), flows=flows)
    m["score"] = objective_score(m, profile)
    m["missed_target"] = missed_target(m, profile)
    m["risk_breaches"] = risk_breaches(m, profile)
    return m


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


def run_window(R: pd.DataFrame, infl: pd.Series, window: Window, strategy: Strategy, profile: dict,
               provider: ConstraintProvider, cache: dict | None = None, fallback: np.ndarray | None = None) -> dict:
    """Simulate `strategy` over `window`. R must contain history before the window (used by the
    strategy) and the window itself. Returns metrics + weight history."""
    assets = list(R.columns)
    cash = profile["cash_asset"]
    rb = strategy.rebalancing or profile["rebalancing"]
    freq, band = rb.get("frequency", "annual"), float(rb.get("band", 0.05))
    cost_rate = float(profile.get("costs_bps", 0.0)) / 1e4
    months = R.loc[window.start:window.end].index
    if len(months) != window.n_months:
        raise ValueError(f"window {window.label} not fully covered by data")
    pos0 = R.index.get_loc(window.start)
    Rv = R.values
    n = len(months)
    port = np.empty(n)
    w_drift = None
    w_hist = np.empty((n, len(assets)))
    turnover_sum, n_fallback, n_rebal = 0.0, 0, 0
    cur_fb = False
    traded = np.zeros(n, dtype=bool)
    drift_out = 0
    for i in range(n):
        pos = pos0 + i
        date = R.index[pos]
        prev = R.index[pos - 1] if pos > 0 else None
        need_target = w_drift is None or _due(freq, i)
        if need_target:
            key = (strategy.name, date)
            if cache is not None and not strategy.window_dependent and key in cache:
                tgt, fb = cache[key]
            else:
                cs = provider.at(prev)
                ctx = Context(assets, cash, cs, date, progress=_progress(freq, i, n), fallback=fallback)
                tgt = cs.project(strategy.target(R.iloc[:pos], ctx))
                fb = bool(ctx.info.get("fallback"))
                if cache is not None and not strategy.window_dependent:
                    cache[key] = (tgt, fb)
            if w_drift is None:
                w = tgt
            elif freq == "bands" and np.max(np.abs(w_drift - tgt)) <= band:
                w = w_drift
            else:
                w = tgt
            if w is tgt:
                cur_fb = fb
                traded[i] = True
            if w_drift is not None and w is tgt:
                dw = np.abs(w - w_drift).sum()
                turnover_sum += 0.5 * dw
                n_rebal += 1
                cost = cost_rate * dw
            else:
                cost = 0.0
        else:
            w, cost = w_drift, 0.0
        n_fallback += int(cur_fb)
        if not traded[i] and not provider.at(prev).is_feasible(w, 1e-4):
            drift_out += 1  # constraints hold at trades; drifted weights may leave the set in between
        r = Rv[pos]
        gross = float(w @ r)
        port[i] = gross - cost
        w_hist[i] = w
        w_drift = w * (1 + r) / (1 + gross) if (1 + gross) > 0 else w
    inf = infl.reindex(months).values
    rf = R.loc[months, cash].values
    m = evaluate(port, inf, rf, profile)
    m.update({"turnover_ann": turnover_sum / (n / 12), "n_rebalances": n_rebal, "fallback_months": n_fallback,
              "drift_months_outside_constraints": drift_out})
    return {"metrics": m, "returns": pd.Series(port, index=months), "traded": pd.Series(traded, index=months),
            "weights": pd.DataFrame(w_hist, index=months, columns=assets)}
