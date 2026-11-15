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

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer, model_validator

SCHEMA_VERSION = "0.2.0-draft"

RiskMeasure = Literal["CVAR", "CDAR", "VOL", "MDD", "CVAR12M", "STRESS_2022", "PROB_LOSS"]
# CVAR12M : contrôle seulement (Judge), pas d'optimisation. CVaR des rendements composés sur 12 mois
# glissants (chevauchants), sur l'historique long, raccordé aux proxys déclarés (HYPOTHESE).
# STRESS_2022 : contrôle seulement, perte (positive) de l'année civile 2022 en devise du mandat, tickers réels.
# Quand history_proxies est fourni, la MDD du Judge se mesure aussi sur l'historique long raccordé.
# PROB_LOSS : contrôle seulement (Judge). P(perte cumulée à l'horizon H > L) ≤ α, lue dans la table de scénarios
# précalculée (outil scenario_risk), IC 90 % ; la limite porte sur la borne haute ci_hi (prudence).
# L = selector.loss_level, H = selector.horizon_years, α = Limit.max. Aucune valeur n'est fixée ici (F1).
# Voir alphaforge/scenarios/PROPOSAL_PROB_LOSS.md et portfolio/scenario_risk.py.
CONTROL_ONLY_MEASURES = frozenset({"CVAR12M", "STRESS_2022", "PROB_LOSS"})
ScenarioBlockName = Literal["CA_EQ", "US_MKT", "BONDS", "CASH", "GOLD", "CRYPTO"]  # = alphaforge.scenarios.schema
ScenarioFamily = Literal["CAD77", "CAD71", "USD1926"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _drop_unset_optionals(data: dict, defaults: dict) -> dict:
    """Retire d'une sérialisation les champs PROB_LOSS restés à leur valeur par défaut : sans limite PROB_LOSS, un
    mandat sérialisé (policy.json, empreintes) reste identique à celui d'avant l'ajout de ces champs."""
    return {key: value for key, value in data.items() if key not in defaults or value != defaults[key]}


class Selector(_Strict):
    """Ce que vise une limite. Un seul des champs est utilisé selon ``Limit.kind``."""

    assets: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)  # asset_class de l'engine (equity_us…)
    tags_any: list[str] = Field(default_factory=list)  # tags de l'engine (crypto, tech_heavy…)
    exposure_tag: str | None = None  # look-through (tech, energy…)
    measure: RiskMeasure | None = None  # pour kind = "risk"
    loss_level: float | None = Field(default=None, gt=0, le=1)  # PROB_LOSS seulement : L, fraction du montant
    horizon_years: int | None = Field(default=None, ge=1)  # PROB_LOSS seulement : H, années

    @model_serializer(mode="wrap")
    def _serialize(self, handler: SerializerFunctionWrapHandler) -> dict:
        return _drop_unset_optionals(handler(self), {"loss_level": None, "horizon_years": None})


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
        self._check_prob_loss_fields()
        return self

    def _check_prob_loss_fields(self) -> None:
        """PROB_LOSS exige L, H et une probabilité α ; ces champs sont réservés à PROB_LOSS."""
        if not (self.kind == "risk" and self.selector.measure == "PROB_LOSS"):
            if self.selector.loss_level is not None or self.selector.horizon_years is not None:
                raise ValueError(f"limite {self.rule_id}: loss_level et horizon_years sont réservés à PROB_LOSS")
            return
        if self.selector.loss_level is None or self.selector.horizon_years is None:
            raise ValueError(f"limite {self.rule_id}: PROB_LOSS exige selector.loss_level et horizon_years")
        if self.max is None or not 0 < self.max < 1:
            raise ValueError(f"limite {self.rule_id}: PROB_LOSS exige 0 < max < 1 (probabilité)")


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


class ScenarioBlock(_Strict):
    """Bloc de la table de scénarios qui représente un actif de l'engine (ex. XIU.TO -> CA_EQ), pour PROB_LOSS."""

    block: ScenarioBlockName
    source: str  # justification du rapprochement
    status: Literal["HYPOTHESE"] = "HYPOTHESE"


_SCENARIO_DEFAULTS = {
    "scenario_blocks": {},
    "scenario_family": None,
    "scenario_model_id": None,
    "scenario_run_id": None,
}


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

    # PROB_LOSS (facultatif, lu par le Judge seulement). scenario_blocks : rattachement déclaré par F1, prioritaire
    # sur le rattachement prudent par défaut (portfolio/scenario_risk.py). scenario_family : None = CAD77 si
    # currency = CAD, USD1926 sinon. scenario_model_id : None = modèle par défaut du manifeste. scenario_run_id :
    # None = scenarios/latest.json ; sinon run figé (rejeu de démonstration).
    scenario_blocks: dict[str, ScenarioBlock] = Field(default_factory=dict)
    scenario_family: ScenarioFamily | None = None
    scenario_model_id: str | None = None
    scenario_run_id: str | None = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler: SerializerFunctionWrapHandler) -> dict:
        return _drop_unset_optionals(handler(self), _SCENARIO_DEFAULTS)

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
        self._check_scenario_fields()
        return self

    def _check_scenario_fields(self) -> None:
        stray = set(self.scenario_blocks) - set(self.universe)
        if stray:
            raise ValueError(f"scenario_blocks hors univers : {sorted(stray)}")
        if self.scenario_family is not None and self.scenario_family.startswith("CAD") != (self.currency == "CAD"):
            raise ValueError(f"scenario_family {self.scenario_family} incohérente avec la devise {self.currency}")

    @property
    def scenario_family_used(self) -> str:
        """Famille de la table de scénarios lue par PROB_LOSS (cohérente avec la devise du mandat)."""
        return self.scenario_family or ("CAD77" if self.currency == "CAD" else "USD1926")

    @property
    def investable(self) -> list[str]:
        return [asset for asset in self.universe if asset not in self.excluded]
