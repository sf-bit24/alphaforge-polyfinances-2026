"""PolicySpec — le mandat dérivé du profil (F1) et consommé par F2-F4.

BROUILLON v0.2 (2026-11-14), aligné sur le plan local « construire le portefeuille ».
À valider par l'équipe. Simulation seulement, jamais un conseil.

- F1 (profil → mandat) **produit** ce contrat. F2 (optimiseur), F3 (analyses) et F4
  (contrôle des plafonds du Judge) le **consomment** sans jamais le modifier.
- Chaque limite porte un ``rule_id`` et sa justification ``derived_from`` (champ du profil
  ou règle YAML@version). Le Judge recopie ces champs dans ses ``ConstraintCheck``.
- Aucune valeur par défaut chiffrée n'est fixée ici : les seuils viennent de F1.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.2.0-draft"

RiskMeasure = Literal["CVAR", "CDAR", "VOL", "MDD", "CVAR12M", "STRESS_2022"]
# CVAR12M : contrôle seulement (Judge), pas d'optimisation. CVaR des rendements composés sur 12 mois
# glissants (chevauchants), sur l'historique long, raccordé aux proxys déclarés (HYPOTHESE).
# STRESS_2022 : contrôle seulement, perte (positive) de l'année civile 2022 en devise du mandat, tickers réels.
# Quand history_proxies est fourni, la MDD du Judge se mesure aussi sur l'historique long raccordé.
CONTROL_ONLY_MEASURES = frozenset({"CVAR12M", "STRESS_2022"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Selector(_Strict):
    """Ce que vise une limite. Un seul des champs est utilisé selon ``Limit.kind``."""

    assets: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)  # asset_class de l'engine (equity_us…)
    tags_any: list[str] = Field(default_factory=list)  # tags de l'engine (crypto, tech_heavy…)
    exposure_tag: str | None = None  # look-through (tech, energy…)
    measure: RiskMeasure | None = None  # pour kind = "risk"


class Limit(_Strict):
    rule_id: str
    kind: Literal["asset_weight", "group_weight", "exposure", "risk"]
    selector: Selector
    min: float | None = None
    max: float | None = None
    blocking: bool = True
    derived_from: str  # ex. « profile.biases[FOMO] »
    source: str | None = None  # ex. « risk_levels.yaml@0.1 »
    description_fr: str | None = None

    @model_validator(mode="after")
    def _bounds(self) -> Limit:
        if self.min is None and self.max is None:
            raise ValueError(f"limite {self.rule_id}: min ou max requis")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"limite {self.rule_id}: min > max")
        if self.kind == "risk":
            if self.selector.measure is None:
                raise ValueError(f"limite {self.rule_id}: selector.measure requis pour kind=risk")
            if self.min is not None:
                raise ValueError(f"limite {self.rule_id}: une limite de risque n'a qu'un max")
        elif self.min is not None and not 0 <= self.min <= 1 or self.max is not None and not 0 <= self.max <= 1:
            raise ValueError(f"limite {self.rule_id}: un poids est dans [0, 1]")
        if self.kind == "exposure" and not self.selector.exposure_tag:
            raise ValueError(f"limite {self.rule_id}: selector.exposure_tag requis")
        return self


class ExposureOverride(_Strict):
    """Part d'un actif exposée à un thème quand l'engine n'a pas de look-through (QQQ, XIU…)."""

    value: float = Field(ge=0, le=1)
    source: str  # fiche émetteur datée, sinon HYPOTHESE
    status: Literal["FAIT", "HYPOTHESE"] = "HYPOTHESE"


class HistoryProxy(_Strict):
    """Actif de l'engine dont l'historique remplace celui d'un actif avant son lancement."""

    proxy: str  # asset_id de l'engine (ex. US_MKT)
    source: str  # justification du rapprochement
    status: Literal["HYPOTHESE"] = "HYPOTHESE"


class PolicySpec(_Strict):
    schema_version: Literal["0.2.0-draft"] = SCHEMA_VERSION
    policy_id: str
    profile_id: str
    profile_version: int = Field(ge=1)
    created_utc: datetime
    currency: Literal["CAD", "USD"] = "CAD"

    universe: list[str] = Field(min_length=2)
    excluded: dict[str, str] = Field(default_factory=dict)  # actif -> raison (fact_id ou règle)

    objective: Literal["min_risk", "max_utility"] = "min_risk"
    risk_measure: Literal["CVAR", "CDAR", "VARIANCE"] = "CVAR"
    cvar_beta: float = Field(default=0.95, gt=0.5, lt=1)
    risk_aversion: float | None = Field(default=None, gt=0)  # requis si objective = max_utility
    expected_returns: dict[str, float] | None = None  # μ annuel par actif (prior sourcé), sinon rétréci
    expected_returns_source: str | None = None

    limits: list[Limit] = Field(default_factory=list)
    exposure_overrides: dict[str, dict[str, ExposureOverride]] = Field(default_factory=dict)

    history_proxies: dict[str, HistoryProxy] = Field(default_factory=dict)  # pour CVAR12M / MDD / stress
    # δ_j : perte maximale supposée d'un actif sans historique long (crypto…). Exclu de la série longue,
    # il ajoute w_j·δ_j à CVAR12M et MDD (sous-additivité et homogénéité de la CVaR ; prudent pour la MDD).
    loss_bounds: dict[str, float] = Field(default_factory=dict)
    loss_bounds_source: str | None = None

    lookback_months: int = Field(default=120, ge=24)
    min_history_months: int = Field(default=36, ge=12)
    max_turnover: float | None = Field(default=None, ge=0, le=2)
    transaction_cost_bps: float = Field(default=0.0, ge=0)

    missing_defaults: list[str] = Field(default_factory=list)  # bornes prudentes appliquées par F1

    @model_validator(mode="after")
    def _coherence(self) -> PolicySpec:
        if len(set(self.universe)) != len(self.universe):
            raise ValueError("univers avec doublons")
        ids = [limit.rule_id for limit in self.limits]
        if len(ids) != len(set(ids)):
            raise ValueError("rule_id en double")
        if self.objective == "max_utility" and self.risk_aversion is None:
            raise ValueError("objective=max_utility exige risk_aversion")
        unknown = set(self.excluded) - set(self.universe)
        if unknown:
            raise ValueError(f"exclusions hors univers : {sorted(unknown)}")
        if any(not 0 < bound <= 1 for bound in self.loss_bounds.values()):
            raise ValueError("loss_bounds : chaque δ est dans ]0, 1]")
        if self.loss_bounds and not self.loss_bounds_source:
            raise ValueError("loss_bounds exige loss_bounds_source")
        if self.expected_returns is not None and not self.expected_returns_source:
            raise ValueError("expected_returns exige expected_returns_source")
        return self

    @property
    def investable(self) -> list[str]:
        return [asset for asset in self.universe if asset not in self.excluded]
