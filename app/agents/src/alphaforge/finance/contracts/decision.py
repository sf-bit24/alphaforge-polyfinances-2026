"""Decision, Fact et TraceEvent — contrat entre le volet finance et la webapp (Sacha).

PROPOSITION v0.1 (2026-11-14), à valider par l'équipe. Simulation seulement, jamais un conseil.

Principe : « le code calcule, le modèle explique, chaque nombre cite sa source ».
- Tout nombre affiché est un ``Fact`` produit par un outil Python et relié à un ``TraceEvent``.
- Une phrase d'explication ne peut citer que des ``fact_id`` présents dans la décision :
  la validation refuse une explication qui s'appuie sur un chiffre inexistant (fidélité par construction).
- La webapp affiche ces objets tels quels ; elle n'effectue aucun calcul financier.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.1.0"
WEIGHT_TOLERANCE = 1e-6


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Label = Literal["FAIT", "HYPOTHESE", "FICTION"]


class Source(_Strict):
    dataset: str  # ex. « fred:DGS10 », « starter:prices_daily »
    url: str | None = None
    licence: str | None = None
    retrieved_utc: datetime | None = None
    sha256: str | None = None
    processing: str | None = None  # ex. « adj_close -> rendements mensuels CAD »


class Fact(_Strict):
    """Un nombre calculé, avec sa provenance complète."""

    fact_id: str
    label_fr: str
    value: float | int | str | None
    unit: str  # « % », « CAD », « ratio », « années »...
    currency: Literal["CAD", "USD", "EUR"] | None = None
    as_of: date | None = None  # date d'observation
    published: date | None = None  # date de publication si différente
    status: Label = "FAIT"
    sources: list[Source] = Field(min_length=1)
    trace_id: str  # TraceEvent qui l'a produit


class TraceEvent(_Strict):
    trace_id: str
    parent_id: str | None = None
    agent: str  # « quant_data », « governance », « explainability »...
    tool: str | None = None  # nom de la fonction @tool
    inputs: dict[str, Any] = Field(default_factory=dict)
    output_summary: str | None = None
    fact_ids: list[str] = Field(default_factory=list)
    started_utc: datetime
    ended_utc: datetime | None = None
    status: Literal["ok", "erreur", "refus"] = "ok"
    message: str | None = None
    data_version: str | None = None  # hash de la couche de données
    code_version: str | None = None  # git SHA
    seed: int | None = None
    model_id: str | None = None  # modèle Bedrock si un LLM est intervenu
    otel_trace_id: str | None = None  # lien vers la trace OpenTelemetry (X-Ray / JSONL)
    otel_span_id: str | None = None


class Position(_Strict):
    asset_id: str
    weight: float = Field(ge=0, le=1)
    goal_id: str | None = None  # seau / objectif servi
    role: str | None = None  # « coeur », « satellite », « reserve »
    rationale_fact_ids: list[str] = Field(default_factory=list)


class ConstraintCheck(_Strict):
    rule_id: str
    description_fr: str
    derived_from: str  # champ du profil ou règle (YAML) qui la justifie
    limit: float | None = None
    value_fact_id: str | None = None
    active: bool = False  # contrainte saturée à l'optimum
    violated: bool = False
    shadow_price: float | None = None  # multiplicateur dual (coût de la contrainte)
    blocking: bool = True


class Statement(_Strict):
    text_fr: str
    fact_ids: list[str] = Field(default_factory=list)
    label: Label = "FAIT"


class Explanation(_Strict):
    """Les 4 questions de l'atelier NBDB."""

    data_used: list[Statement]
    why: list[Statement]
    limits: list[Statement]
    what_would_change: list[Statement]


class Counterfactual(_Strict):
    change_fr: str  # « si la perte tolérée passait de 10 % à 20 % »
    result_fact_ids: list[str] = Field(min_length=1)


class Decision(_Strict):
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    decision_id: str
    profile_id: str
    profile_version: int = Field(ge=1)
    created_utc: datetime
    kind: Literal["proposition", "refus_encadre", "position_attente", "incomplet", "protection"]
    simulation_only: Literal[True] = True
    positions: list[Position] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    constraints: list[ConstraintCheck] = Field(default_factory=list)
    counterfactuals: list[Counterfactual] = Field(default_factory=list)
    explanation: Explanation
    reprofile_triggers_fired: list[str] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(min_length=1)
    disclaimer_fr: str = "Simulation éducative — ne constitue pas un conseil financier personnalisé."

    @model_validator(mode="after")
    def _integrity(self) -> Decision:
        fact_ids = {fact.fact_id for fact in self.facts}
        if len(fact_ids) != len(self.facts):
            raise ValueError("fact_id en double")
        trace_ids = {event.trace_id for event in self.trace}
        for fact in self.facts:
            if fact.trace_id not in trace_ids:
                raise ValueError(f"fact {fact.fact_id}: trace_id {fact.trace_id} absent de la trace")
        unknown = self._cited_fact_ids() - fact_ids
        if unknown:
            raise ValueError(f"chiffres cités sans Fact correspondant : {sorted(unknown)}")
        if self.kind == "proposition":
            self._check_proposition()
        return self

    def _cited_fact_ids(self) -> set[str]:
        explanation = self.explanation
        cited: set[str] = set()
        for section in (explanation.data_used, explanation.why, explanation.limits, explanation.what_would_change):
            for statement in section:
                cited.update(statement.fact_ids)
        for position in self.positions:
            cited.update(position.rationale_fact_ids)
        for counterfactual in self.counterfactuals:
            cited.update(counterfactual.result_fact_ids)
        cited.update(check.value_fact_id for check in self.constraints if check.value_fact_id)
        return cited

    def _check_proposition(self) -> None:
        if not self.positions:
            raise ValueError("une proposition doit contenir des positions")
        total = sum(position.weight for position in self.positions)
        if abs(total - 1.0) > WEIGHT_TOLERANCE:
            raise ValueError(f"les poids somment à {total:.6f}, pas à 1")
        if any(check.violated and check.blocking for check in self.constraints):
            raise ValueError("proposition avec contrainte bloquante violée : utiliser refus_encadre")
