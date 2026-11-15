"""Hard portfolio constraints and projection onto the admissible set.

All constraints are linear: lb_i <= w_i <= ub_i, sum w = 1 (long-only by default) and
group constraints  min_g <= a_g . w <= max_g  where a_g is a look-through exposure vector
(e.g. tech share of each asset), a class/tag membership vector, or an explicit asset list.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy.optimize import linprog, minimize

from .data import exposure_vector, load_assets


def _is_member(
    asset: str, catalogue: pd.DataFrame, listed: list | None, classes: list | None, tags: list | None
) -> bool:
    """Membership by explicit asset list, asset class or any shared tag."""
    return bool(
        asset in (listed or [])
        or catalogue.at[asset, "asset_class"] in (classes or [])
        or set(catalogue.at[asset, "tag_list"]) & set(tags or [])
    )


def _weight_bounds(assets: list[str], config: dict, catalogue: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Default bounds, capped by the class maxima, then replaced by the explicit asset bounds."""
    n = len(assets)
    low, high = config.get("default_bounds", [0.0, 1.0])
    lower = np.full(n, float(low))
    upper = np.full(n, float(high))
    for asset_class, maximum in (config.get("class_max_weight") or {}).items():
        for i, asset in enumerate(assets):
            if catalogue.at[asset, "asset_class"] == asset_class:
                upper[i] = min(upper[i], float(maximum))
    for asset, (low, high) in (config.get("asset_bounds") or {}).items():
        if asset in assets:
            i = assets.index(asset)
            lower[i], upper[i] = float(low), float(high)
    return lower, upper


def _membership_vector(assets: list[str], group: dict, catalogue: pd.DataFrame) -> np.ndarray:
    vector = np.zeros(len(assets))
    for i, asset in enumerate(assets):
        if _is_member(asset, catalogue, group.get("assets"), group.get("classes"), group.get("tags_any")):
            vector[i] = 1.0
    return vector


def _without_lookthrough(assets: list[str], overrides: dict, catalogue: pd.DataFrame) -> list[str]:
    """Broad-market assets whose exposure comes from no override, no US_MKT look-through and no assets.csv value."""
    return [
        asset
        for asset in assets
        if asset not in overrides
        and asset != "US_MKT"
        and catalogue.at[asset, "proxy_for_ticker"] != "US_MKT"
        and {"broad_market", "tech_heavy"} & set(catalogue.at[asset, "tag_list"])
        and not catalogue.at[asset, "exposure_map"]
    ]


def _groups(assets: list[str], config: dict, catalogue: pd.DataFrame, date, window) -> tuple[list[tuple], list[str]]:
    """Group constraints (name, vector, min, max) and the warnings about missing look-through data."""
    groups, messages = [], []
    overrides = config.get("exposure_overrides") or {}
    for group in config.get("groups") or []:
        if "exposure" in group:
            vector = exposure_vector(assets, group["exposure"], date=date, overrides=overrides, window=window)
            unknown = _without_lookthrough(assets, overrides, catalogue)
            if unknown:
                messages.append(
                    f"group {group['name']}: no look-through data for {unknown} (exposure treated as "
                    f"0 unless tagged); set constraints.exposure_overrides with a documented source"
                )
        else:
            vector = _membership_vector(assets, group, catalogue)
        groups.append((group["name"], vector, group.get("min"), group.get("max")))
    return groups, messages


class ConstraintSet:
    def __init__(self, assets: list[str], config: dict, date=None, window=None):
        self.assets = list(assets)
        self.config = config
        catalogue = load_assets()
        self.lb, self.ub = _weight_bounds(assets, config, catalogue)
        exclude = config.get("exclude") or {}
        self.excluded = []
        for i, asset in enumerate(assets):
            if _is_member(asset, catalogue, exclude.get("assets"), exclude.get("classes"), exclude.get("tags")):
                self.lb[i] = self.ub[i] = 0.0
                self.excluded.append(asset)
        self.groups, self.warnings = _groups(assets, config, catalogue, date, window)
        for message in self.warnings:
            warnings.warn(message, stacklevel=2)

    # ------------------------------------------------------------------ checks
    def violations(self, weights, tol: float = 1e-4) -> list[str]:
        weights = np.asarray(weights, float)
        messages = []
        if abs(weights.sum() - 1) > tol:
            messages.append(f"sum={weights.sum():.4f}")
        for i, asset in enumerate(self.assets):
            if weights[i] < self.lb[i] - tol or weights[i] > self.ub[i] + tol:
                messages.append(f"{asset}={weights[i]:.4f} not in [{self.lb[i]}, {self.ub[i]}]")
        for name, vector, minimum, maximum in self.groups:
            exposure = float(vector @ weights)
            if minimum is not None and exposure < minimum - tol:
                messages.append(f"{name}={exposure:.4f} < {minimum}")
            if maximum is not None and exposure > maximum + tol:
                messages.append(f"{name}={exposure:.4f} > {maximum}")
        return messages

    def is_feasible(self, weights, tol: float = 1e-4) -> bool:
        return not self.violations(weights, tol)

    # ------------------------------------------------------------------ scipy helpers
    def bounds(self):
        return list(zip(self.lb, self.ub, strict=True))

    def scipy_constraints(self):
        constraints = [
            {"type": "eq", "fun": lambda weights: weights.sum() - 1.0, "jac": lambda weights: np.ones_like(weights)}
        ]
        for _, vector, minimum, maximum in self.groups:
            if minimum is not None:
                constraints.append(
                    {
                        "type": "ineq",
                        "fun": (lambda weights, row=vector, bound=minimum: row @ weights - bound),
                        "jac": (lambda weights, row=vector: row),
                    }
                )
            if maximum is not None:
                constraints.append(
                    {
                        "type": "ineq",
                        "fun": (lambda weights, row=vector, bound=maximum: bound - row @ weights),
                        "jac": (lambda weights, row=vector: -row),
                    }
                )
        return constraints

    def feasible_point(self) -> np.ndarray:
        """Any admissible point (LP); raises if the constraint set is empty."""
        n = len(self.assets)
        inequality_rows, inequality_bounds = [], []
        for _, vector, minimum, maximum in self.groups:
            if maximum is not None:
                inequality_rows.append(vector)
                inequality_bounds.append(maximum)
            if minimum is not None:
                inequality_rows.append(-vector)
                inequality_bounds.append(-minimum)
        result = linprog(
            np.zeros(n),
            A_ub=np.array(inequality_rows) if inequality_rows else None,
            b_ub=inequality_bounds or None,
            A_eq=np.ones((1, n)),
            b_eq=[1.0],
            bounds=self.bounds(),
            method="highs",
        )
        if not result.success:
            raise ValueError("constraint set is infeasible: " + result.message)
        return result.x

    def _least_squares(self, target: np.ndarray, start: np.ndarray, max_iterations: int) -> np.ndarray:
        return minimize(
            lambda weights: 0.5 * np.sum((weights - target) ** 2),
            start,
            jac=lambda weights: weights - target,
            bounds=self.bounds(),
            constraints=self.scipy_constraints(),
            method="SLSQP",
            options={"ftol": 1e-12, "maxiter": max_iterations},
        ).x

    def project(self, weights) -> np.ndarray:
        """Closest admissible weights (least squares) to `weights`."""
        target = np.nan_to_num(np.asarray(weights, float))
        if self.is_feasible(target, tol=1e-9):
            return target
        start = np.clip(target, self.lb, self.ub)
        if start.sum() > 0:
            start = start / start.sum()
        projected = self._least_squares(target, start, 500)
        if not self.is_feasible(projected, tol=1e-5):
            feasible = self.feasible_point()
            projected = self._least_squares(target, feasible, 1000)
            projected = projected if self.is_feasible(projected, tol=1e-5) else feasible
        projected = np.clip(projected, self.lb, self.ub)
        return projected / projected.sum()
