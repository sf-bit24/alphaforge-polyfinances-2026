from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Constraints(BaseModel):
    max_crypto: float = 0.0
    max_single_asset: float = 0.2
    max_equity: float = 0.6
    min_cash: float = 0.05
    esg_required: bool = False
    exclude_carbon_intensity: str | None = None


class Persona(BaseModel):
    name: str
    age: int
    horizon_years: int
    capacity_for_loss: Literal["low", "medium", "high"]
    risk_tolerance: Literal["low", "balanced", "high", "very_high"]
    behavioral_scores: dict[str, int] = Field(default_factory=dict)
    constraints: Constraints
    goals: list[str] = Field(default_factory=list)


class Asset(BaseModel):
    ticker: str
    name: str
    asset_class: str
    region: str
    esg_score: float
    carbon_intensity: str
    expected_return: float
    volatility: float


class Allocation(BaseModel):
    ticker: str
    weight: float
    rationale: str = ""


class Portfolio(BaseModel):
    persona: str
    allocations: list[Allocation]
    expected_return: float
    volatility: float
    max_drawdown_proxy: float
    warnings: list[str] = Field(default_factory=list)
    refused: bool = False


class TraceEvent(BaseModel):
    agent: str
    action: str
    reasoning: str
    evidence: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    portfolio: Portfolio
    trace: list[TraceEvent] = Field(default_factory=list)
    recommendation: str


def load_persona(name: str, root: Path | None = None) -> Persona:
    root = root or Path(__file__).resolve().parents[1]
    with (root / "data" / "profiles" / f"{name.lower()}.json").open() as f:
        return Persona.model_validate(json.load(f))
