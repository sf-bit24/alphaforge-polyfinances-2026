"""Chargement de ``evolution.yaml`` (seule configuration de l'évolution), validé et empreinté."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PATH = Path(__file__).with_name("evolution.yaml")


class _C(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Bands(_C):
    abs: float = Field(gt=0, le=0.5)
    rel: float = Field(gt=0, le=1)
    min_abs: float = Field(ge=0, le=0.1)
    trade_mode: Literal["half", "edge", "full"]
    cap_cushion: float = Field(default=0.0, ge=0, le=0.05)   # absent = pas de coussin


class Trading(_C):
    min_trade_cad: float = Field(ge=0)
    cost_bps: float = Field(ge=0)
    max_turnover_tick: float = Field(gt=0, le=2)


class Flows(_C):
    contribution_first: bool
    large_flow_share: float = Field(gt=0, le=1)


class Review(_C):
    review_months: int = Field(ge=1)
    kyc_months_managed: int = Field(ge=1)
    kyc_months_other: int = Field(ge=1)
    need_goal_months: int = Field(ge=1)
    drawdown_reference: Literal["hwm", "cost"]


class Gate(_C):
    min_dsr: float = Field(ge=0, le=1)
    max_pbo: float = Field(ge=0, le=1)
    min_train_months: int = Field(ge=12)
    require_no_limit_breach: bool
    costs_included: bool


class Overlays(_C):
    model_config = ConfigDict(extra="allow", frozen=True)   # un bloc par overlay, lu par chaque module
    order: list[str]
    common: dict


class EvolutionConfig(_C):
    version: str
    status: Literal["HYPOTHESE"]
    brain_fiche: str
    bands: Bands
    trading: Trading
    flows: Flows
    review: Review
    overlays: Overlays
    gate: Gate
    sha256: str = ""

    def overlay(self, name: str) -> dict:
        return dict(getattr(self.overlays, name, None) or {})

    def src(self, path: str) -> str:
        """Référence citable d'un paramètre : ``evolution.yaml@<version>#<chemin>``."""
        return f"evolution.yaml@{self.version}#{path}"


@lru_cache(maxsize=8)
def load_config(path: str | None = None) -> EvolutionConfig:
    p = Path(path) if path else DEFAULT_PATH
    raw = p.read_bytes()
    data = yaml.safe_load(raw)
    return EvolutionConfig(**data, sha256=hashlib.sha256(raw).hexdigest())
