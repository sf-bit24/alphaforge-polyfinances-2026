"""Hard portfolio constraints and projection onto the admissible set.

All constraints are linear: lb_i <= w_i <= ub_i, sum w = 1 (long-only by default) and
group constraints  min_g <= a_g . w <= max_g  where a_g is a look-through exposure vector
(e.g. tech share of each asset), a class/tag membership vector, or an explicit asset list.
"""
from __future__ import annotations

import warnings

import numpy as np
from scipy.optimize import linprog, minimize

from .data import exposure_vector, load_assets

TOL = 1e-6


class ConstraintSet:
    def __init__(self, assets: list[str], cfg: dict, date=None, window=None):
        self.assets = list(assets)
        self.cfg = cfg
        cat = load_assets()
        n = len(assets)
        lo, hi = cfg.get("default_bounds", [0.0, 1.0])
        self.lb = np.full(n, float(lo))
        self.ub = np.full(n, float(hi))
        for cls, mx in (cfg.get("class_max_weight") or {}).items():
            for i, a in enumerate(assets):
                if cat.at[a, "asset_class"] == cls:
                    self.ub[i] = min(self.ub[i], float(mx))
        for a, (l, u) in (cfg.get("asset_bounds") or {}).items():
            if a in assets:
                i = assets.index(a)
                self.lb[i], self.ub[i] = float(l), float(u)
        ex = cfg.get("exclude") or {}
        self.excluded = []
        for i, a in enumerate(assets):
            if (a in (ex.get("assets") or []) or cat.at[a, "asset_class"] in (ex.get("classes") or [])
                    or set(cat.at[a, "tag_list"]) & set(ex.get("tags") or [])):
                self.lb[i] = self.ub[i] = 0.0
                self.excluded.append(a)
        self.groups = []  # (name, vector, min, max)
        self.warnings = []
        ov = cfg.get("exposure_overrides") or {}
        for g in cfg.get("groups") or []:
            if "exposure" in g:
                vec = exposure_vector(assets, g["exposure"], date=date, overrides=ov, window=window)
                unknown = [a for a in assets if a not in ov and a != "US_MKT"
                           and cat.at[a, "proxy_for_ticker"] != "US_MKT"
                           and {"broad_market", "tech_heavy"} & set(cat.at[a, "tag_list"])
                           and not cat.at[a, "exposure_map"]]
                if unknown:
                    self.warnings.append(f"group {g['name']}: no look-through data for {unknown} (exposure treated as "
                                         f"0 unless tagged); set constraints.exposure_overrides with a documented source")
            else:
                vec = np.zeros(n)
                for i, a in enumerate(assets):
                    if (a in (g.get("assets") or []) or cat.at[a, "asset_class"] in (g.get("classes") or [])
                            or set(cat.at[a, "tag_list"]) & set(g.get("tags_any") or [])):
                        vec[i] = 1.0
            self.groups.append((g["name"], vec, g.get("min"), g.get("max")))
        for w in self.warnings:
            warnings.warn(w, stacklevel=2)

    # ------------------------------------------------------------------ checks
    def violations(self, w, tol: float = 1e-4) -> list[str]:
        w = np.asarray(w, float)
        v = []
        if abs(w.sum() - 1) > tol:
            v.append(f"sum={w.sum():.4f}")
        for i, a in enumerate(self.assets):
            if w[i] < self.lb[i] - tol or w[i] > self.ub[i] + tol:
                v.append(f"{a}={w[i]:.4f} not in [{self.lb[i]}, {self.ub[i]}]")
        for name, vec, mn, mx in self.groups:
            x = float(vec @ w)
            if mn is not None and x < mn - tol:
                v.append(f"{name}={x:.4f} < {mn}")
            if mx is not None and x > mx + tol:
                v.append(f"{name}={x:.4f} > {mx}")
        return v

    def is_feasible(self, w, tol: float = 1e-4) -> bool:
        return not self.violations(w, tol)

    # ------------------------------------------------------------------ scipy helpers
    def bounds(self):
        return list(zip(self.lb, self.ub))

    def scipy_constraints(self):
        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones_like(w)}]
        for _, vec, mn, mx in self.groups:
            if mn is not None:
                cons.append({"type": "ineq", "fun": (lambda w, v=vec, m=mn: v @ w - m), "jac": (lambda w, v=vec: v)})
            if mx is not None:
                cons.append({"type": "ineq", "fun": (lambda w, v=vec, m=mx: m - v @ w), "jac": (lambda w, v=vec: -v)})
        return cons

    def feasible_point(self) -> np.ndarray:
        """Any admissible point (LP); raises if the constraint set is empty."""
        n = len(self.assets)
        A_ub, b_ub = [], []
        for _, vec, mn, mx in self.groups:
            if mx is not None:
                A_ub.append(vec); b_ub.append(mx)
            if mn is not None:
                A_ub.append(-vec); b_ub.append(-mn)
        res = linprog(np.zeros(n), A_ub=np.array(A_ub) if A_ub else None, b_ub=b_ub or None,
                      A_eq=np.ones((1, n)), b_eq=[1.0], bounds=self.bounds(), method="highs")
        if not res.success:
            raise ValueError("constraint set is infeasible: " + res.message)
        return res.x

    def project(self, w0) -> np.ndarray:
        """Closest admissible weights (least squares) to w0."""
        w0 = np.nan_to_num(np.asarray(w0, float))
        if self.is_feasible(w0, tol=1e-9):
            return w0
        start = np.clip(w0, self.lb, self.ub)
        if start.sum() > 0:
            start = start / start.sum()
        res = minimize(lambda w: 0.5 * np.sum((w - w0) ** 2), start, jac=lambda w: w - w0,
                       bounds=self.bounds(), constraints=self.scipy_constraints(), method="SLSQP",
                       options={"ftol": 1e-12, "maxiter": 500})
        w = res.x
        if not self.is_feasible(w, tol=1e-5):
            fp = self.feasible_point()
            res = minimize(lambda w: 0.5 * np.sum((w - w0) ** 2), fp, jac=lambda w: w - w0,
                           bounds=self.bounds(), constraints=self.scipy_constraints(), method="SLSQP",
                           options={"ftol": 1e-12, "maxiter": 1000})
            w = res.x if self.is_feasible(res.x, tol=1e-5) else fp
        w = np.clip(w, self.lb, self.ub)
        return w / w.sum()
