"""Investor-profile configuration (YAML) -> validated dict with defaults.

See finance/backtest/profiles/example.yaml for a fully commented example. A profile given by id is looked up in
``paths.profile_dirs()`` (packaged profiles, then the studies of ``app/agents/scripts/backtest/profiles`` in a source
checkout; ``ALPHAFORGE_BT_PROFILES`` or ``profiles_dir`` override the list).
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

from .paths import PROFILES_DIR, profile_dirs

__all__ = ["DEFAULTS", "PROFILES_DIR", "find_profile", "load_profile", "validate"]

OBJECTIVES = ("max_real_return", "max_sharpe", "max_return_over_cvar", "min_shortfall")
REBAL = ("monthly", "quarterly", "annual", "bands", "never")
STRATEGY_TYPES = ("static", "sixty_forty", "glidepath", "risk_parity", "min_variance", "max_sharpe",
                  "mean_variance", "trend_filter", "momentum")

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


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def validate(p: dict) -> dict:
    from .data import load_assets

    cat = load_assets()
    errs = []
    if not p.get("id"):
        errs.append("id is required")
    if not p.get("universe"):
        errs.append("universe (list of asset_id) is required")
    else:
        bad = [a for a in p["universe"] if a not in cat.index]
        if bad:
            errs.append(f"unknown assets in universe: {bad}")
    if p.get("cash_asset") not in (p.get("universe") or []):
        errs.append("cash_asset must be one of the universe assets")
    if p["currency"] not in ("CAD", "USD"):
        errs.append("currency must be CAD or USD")
    if p["objective"]["type"] not in OBJECTIVES:
        errs.append(f"objective.type must be one of {OBJECTIVES}")
    if p["objective"]["type"] == "min_shortfall" and p["objective"]["target_real_return"] is None \
            and p["objective"]["target_real_wealth"] is None:
        errs.append("min_shortfall needs objective.target_real_return or objective.target_real_wealth")
    if p["rebalancing"]["frequency"] not in REBAL:
        errs.append(f"rebalancing.frequency must be one of {REBAL}")
    if p["mode"] not in ("non_overlapping", "rolling"):
        errs.append("mode must be non_overlapping or rolling")
    names = set()
    for s in p["strategies"]:
        if s.get("type") not in STRATEGY_TYPES:
            errs.append(f"strategy {s.get('name')}: type must be one of {STRATEGY_TYPES}")
        if not s.get("name") or s["name"] in names:
            errs.append(f"strategy names must be unique and non-empty ({s.get('name')})")
        names.add(s.get("name"))
        for a in (s.get("params", {}) or {}).get("weights", {}) or {}:
            if a not in (p.get("universe") or []):
                errs.append(f"strategy {s.get('name')}: weight on {a} not in universe")
        if s.get("rebalancing", {}).get("frequency", "annual") not in REBAL:
            errs.append(f"strategy {s.get('name')}: bad rebalancing.frequency")
    if not p["strategies"]:
        errs.append("at least one strategy is required")
    for g in p["constraints"]["groups"]:
        if not g.get("name") or not any(k in g for k in ("exposure", "tags_any", "classes", "assets")):
            errs.append(f"group {g}: needs a name and one of exposure/tags_any/classes/assets")
    if errs:
        raise ValueError("invalid profile:\n - " + "\n - ".join(errs))
    return p


def find_profile(name: str, profiles_dir: str | Path | None = None) -> Path:
    """Path of ``<name>.yaml`` in ``profiles_dir`` (if given) or the first matching directory of ``profile_dirs()``."""
    dirs = [Path(profiles_dir)] if profiles_dir is not None else profile_dirs()
    for d in dirs:
        candidate = d / f"{name}.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"profile {name!r} not found in: {', '.join(str(d) for d in dirs)}")


def load_profile(name_or_path: str, profiles_dir: str | Path | None = None) -> dict:
    path = Path(name_or_path)
    if not path.suffix:
        path = find_profile(name_or_path, profiles_dir)
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    p = _merge(DEFAULTS, raw)
    p["_path"] = str(path)
    return validate(p)
