"""Investor-profile configuration (YAML) -> validated dict with defaults.

See finance/backtest/profiles/example.yaml for a fully commented example. A profile given by id is looked up in
``paths.profile_dirs()`` (the packaged ``profiles/`` folder; ``ALPHAFORGE_BT_PROFILES`` or ``profiles_dir`` override
it).
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from .paths import PROFILES_DIR, profile_dirs

__all__ = ["DEFAULTS", "PROFILES_DIR", "find_profile", "load_profile", "validate"]

OBJECTIVES = ("max_real_return", "max_sharpe", "max_return_over_cvar", "min_shortfall")
REBALANCING_FREQUENCIES = ("monthly", "quarterly", "annual", "bands", "never")
STRATEGY_TYPES = (
    "static",
    "sixty_forty",
    "glidepath",
    "risk_parity",
    "min_variance",
    "max_sharpe",
    "mean_variance",
    "trend_filter",
    "momentum",
)

DEFAULTS = {
    "id": None,
    "description": "",
    "currency": "CAD",
    "fx_fill": "none",
    "horizon_years": 10,
    "mode": "non_overlapping",
    "step_months": 12,
    "period": {"start": None, "end": None},
    "universe": None,
    "cash_asset": None,
    "objective": {"type": "max_real_return", "target_real_return": None, "target_real_wealth": None},
    "constraints": {
        "default_bounds": [0.0, 1.0],
        "asset_bounds": {},
        "class_max_weight": {},
        "exclude": {"assets": [], "tags": [], "classes": []},
        "groups": [],
        "exposure_overrides": {},
    },
    "risk_limits": {"max_vol": None, "max_drawdown": None, "max_cvar_5": None},
    "flows": {"initial": 1.0, "monthly": 0.0, "indexed_to_inflation": True},
    "rebalancing": {"frequency": "annual", "band": 0.05},
    "costs_bps": 0.0,
    "fallback_weights": None,
    "strategies": [],
    "selection": {"quantile": 0.10, "max_breach_rate": None, "min_past_windows": 3},
    "oracle": {"enabled": True, "n_starts": 6},
    "seed": 42,
}


def _merge(base: dict, overrides: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _universe_errors(profile: dict, catalogue) -> list[str]:
    errors = []
    if not profile.get("id"):
        errors.append("id is required")
    if not profile.get("universe"):
        errors.append("universe (list of asset_id) is required")
    else:
        unknown = [asset for asset in profile["universe"] if asset not in catalogue.index]
        if unknown:
            errors.append(f"unknown assets in universe: {unknown}")
    if profile.get("cash_asset") not in (profile.get("universe") or []):
        errors.append("cash_asset must be one of the universe assets")
    return errors


def _setting_errors(profile: dict) -> list[str]:
    errors = []
    objective = profile["objective"]
    if profile["currency"] not in ("CAD", "USD"):
        errors.append("currency must be CAD or USD")
    if objective["type"] not in OBJECTIVES:
        errors.append(f"objective.type must be one of {OBJECTIVES}")
    if (
        objective["type"] == "min_shortfall"
        and objective["target_real_return"] is None
        and objective["target_real_wealth"] is None
    ):
        errors.append("min_shortfall needs objective.target_real_return or objective.target_real_wealth")
    if profile["rebalancing"]["frequency"] not in REBALANCING_FREQUENCIES:
        errors.append(f"rebalancing.frequency must be one of {REBALANCING_FREQUENCIES}")
    if profile["mode"] not in ("non_overlapping", "rolling"):
        errors.append("mode must be non_overlapping or rolling")
    return errors


def _single_strategy_errors(strategy: dict, earlier_names: set, universe: list) -> list[str]:
    name = strategy.get("name")
    errors = []
    if strategy.get("type") not in STRATEGY_TYPES:
        errors.append(f"strategy {name}: type must be one of {STRATEGY_TYPES}")
    if not name or name in earlier_names:
        errors.append(f"strategy names must be unique and non-empty ({name})")
    for asset in (strategy.get("params", {}) or {}).get("weights", {}) or {}:
        if asset not in universe:
            errors.append(f"strategy {name}: weight on {asset} not in universe")
    if strategy.get("rebalancing", {}).get("frequency", "annual") not in REBALANCING_FREQUENCIES:
        errors.append(f"strategy {name}: bad rebalancing.frequency")
    return errors


def _strategy_errors(profile: dict) -> list[str]:
    errors = []
    names = set()
    for strategy in profile["strategies"]:
        errors += _single_strategy_errors(strategy, names, profile.get("universe") or [])
        names.add(strategy.get("name"))
    if not profile["strategies"]:
        errors.append("at least one strategy is required")
    return errors


def _group_errors(profile: dict) -> list[str]:
    return [
        f"group {group}: needs a name and one of exposure/tags_any/classes/assets"
        for group in profile["constraints"]["groups"]
        if not group.get("name") or not any(k in group for k in ("exposure", "tags_any", "classes", "assets"))
    ]


def validate(profile: dict) -> dict:
    from .data import load_assets

    errors = [
        *_universe_errors(profile, load_assets()),
        *_setting_errors(profile),
        *_strategy_errors(profile),
        *_group_errors(profile),
    ]
    if errors:
        raise ValueError("invalid profile:\n - " + "\n - ".join(errors))
    return profile


def find_profile(name: str, profiles_dir: str | Path | None = None) -> Path:
    """Path of ``<name>.yaml`` in ``profiles_dir`` (if given) or the first matching directory of ``profile_dirs()``."""
    dirs = [Path(profiles_dir)] if profiles_dir is not None else profile_dirs()
    for folder in dirs:
        candidate = folder / f"{name}.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"profile {name!r} not found in: {', '.join(str(folder) for folder in dirs)}")


def load_profile(name_or_path: str, profiles_dir: str | Path | None = None) -> dict:
    path = Path(name_or_path)
    if not path.suffix:
        path = find_profile(name_or_path, profiles_dir)
    with open(path, encoding="utf-8") as file:
        raw = yaml.safe_load(file)
    profile = _merge(DEFAULTS, raw)
    profile["_path"] = str(path)
    return validate(profile)
