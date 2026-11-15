"""Chargement de ``strategy.yaml`` (étape 0). Pur : PyYAML + pydantic, sûr en CI. Simulation seulement."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

StyleId = Literal["defensive", "dynamique", "offensive"]
STYLES: tuple[StyleId, ...] = ("defensive", "dynamique", "offensive")
DEFAULT_PATH = Path(__file__).with_name("strategy.yaml")
LEVELS = ("N0", "N1", "N2", "N3", "N4", "N5")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Preference(_Strict):
    max_up: int = Field(ge=0, le=2)
    goal_to_preference: dict[str, StyleId]
    beginner_max_style: StyleId
    low_tolerance_levels: list[str]
    high_tolerance_levels: list[str]
    short_horizon_years: float


class Band(_Strict):
    rounding: float = Field(gt=0, le=0.1)
    low_composure_pi_max: float = Field(ge=0, le=1)
    incomplete_pi: float = Field(ge=0, le=1)
    growth_classes: list[str]


class SectorTag(_Strict):
    s_ref: float = Field(ge=0, le=1)
    delta: float = Field(gt=0, le=1)
    source: str


class Sectors(_Strict):
    phi: float = Field(ge=0, le=1)
    rounding: float = Field(gt=0)
    tags: dict[str, SectorTag]
    tau: dict[StyleId, dict[str, float]]
    employment_to_tag: dict[str, str]
    employment_to_sector: dict[str, str]


class Features(_Strict):
    vol_weeks: int
    vol_min_obs: int
    beta_days: int
    beta_min_obs: int
    corr_weeks: int
    liquidity_days: int
    momentum_months: list[int]
    local_index: dict[str, str]
    core: dict[str, float]


class InterestAsset(_Strict):
    """Intérêt servi par un FNB, pas par un titre individuel : plancher borné par une limite du mandat."""

    asset: str
    limit: str  # rule_id du plafond qui borne le plancher (ex. alloc.gold)


class Bonus(_Strict):
    size: float
    style_tags: dict[StyleId, list[str]]
    interests: dict[str, dict[str, Any]]
    interest_assets: dict[str, InterestAsset] = Field(default_factory=dict)
    unavailable_interests: list[str]
    preference_penalty: float
    favored_tickers_bonus: int = Field(default=1, ge=0, le=1)  # bonus de `size` pour un titre préféré, une fois


class Eligibility(_Strict):
    mdd_long_max: float
    min_median_dollar_volume_cad: float
    min_line_cad: float


class KRule(_Strict):
    k_default: int = Field(ge=0)
    k_max: int = Field(ge=0)
    one_per_sector: bool


class Floors(_Strict):
    phi: dict[StyleId, float]
    f_abs: float = Field(gt=0, le=1)
    min_floor: float = Field(ge=0)
    overconfidence_mult: float = Field(gt=0, le=1)


class Decided(_Strict):
    date: str
    by: str
    items: list[str]


class StrategyConfig(_Strict):
    version: str
    status: Literal["HYPOTHESE"]
    decided: Decided | None = None
    brain_fiche: str
    okf_methodology: str
    inspirations: list[str]
    styles: list[StyleId]
    level_to_style: dict[str, StyleId]
    preference: Preference
    band: Band
    sectors: Sectors
    features: Features
    weights: dict[StyleId, dict[str, list[float]]]
    bonus: Bonus
    eligibility: Eligibility
    k: KRule
    floors: Floors
    non_shortlisted: Literal["exclude", "free"]
    profile_codes: dict[str, Any]
    sha256: str = ""  # rempli au chargement (sha256 du fichier, cité par chaque Fact strat.*)

    @model_validator(mode="after")
    def _coherence(self) -> StrategyConfig:
        if tuple(self.styles) != STYLES:
            raise ValueError(f"styles doit valoir {STYLES}")
        if set(self.level_to_style) != set(LEVELS):
            raise ValueError("level_to_style doit couvrir N0..N5")
        idx = [STYLES.index(self.level_to_style[L]) for L in LEVELS]
        if idx != sorted(idx):
            raise ValueError("level_to_style doit être monotone (un niveau plus haut n'est jamais plus prudent)")
        for st, w in self.weights.items():
            for feat, pair in w.items():
                if len(pair) != 2 or pair[0] not in (-1, 1) or pair[1] <= 0:
                    raise ValueError(f"weights.{st}.{feat} : [signe ±1, poids > 0] attendu")
        if self.k.k_default > self.k.k_max:
            raise ValueError("k_default > k_max")
        return self

    @property
    def ref(self) -> str:
        return f"strategy.yaml@{self.version}"

    def src(self, path: str) -> str:
        return f"{self.ref}#{path}"


def load_strategy(path: str | Path | None = None) -> StrategyConfig:
    p = Path(path) if path else DEFAULT_PATH
    return _load(str(p.resolve()))


@lru_cache(maxsize=8)
def _load(path: str) -> StrategyConfig:
    raw = Path(path).read_bytes()
    data = yaml.safe_load(raw)
    cfg = StrategyConfig.model_validate(data)
    return cfg.model_copy(update={"sha256": hashlib.sha256(raw).hexdigest()})
