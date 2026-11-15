"""Types publics du compilateur F1 (InvestorProfile -> PolicySpec). Simulation seulement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from alphaforge.finance.contracts import Limit, PolicySpec

DecisionKind = Literal["incomplet", "protection", "position_attente"]


class SpecificRequest(BaseModel):
    """Demande ponctuelle de l'utilisateur (« acheter 50 000 $ de NVDA »).

    F1 ne l'approuve jamais : il expose seulement les plafonds (bac a sable, titre individuel,
    crypto) pour que le graphe optimise avec et sans la demande, puis que le Judge tranche.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticker: str
    kind: Literal["buy"] = "buy"
    amount_cad: float | None = Field(default=None, gt=0)
    weight: float | None = Field(default=None, gt=0, le=1)

    @model_validator(mode="after")
    def _one_size(self) -> SpecificRequest:
        if (self.amount_cad is None) == (self.weight is None):
            raise ValueError("SpecificRequest : fournir amount_cad OU weight (un seul)")
        return self


@dataclass
class RequestView:
    """Plafonds applicables a une demande, sans verdict d'approbation."""

    ticker: str
    asset_class: str | None
    in_universe: bool
    excluded_reason: str | None
    requested_weight: float | None  # None si W inconnu et demande en CAD
    requested_cad: float | None
    sandbox_max: float
    sandbox_max_cad: float | None
    single_name_max: float | None  # si titre individuel
    crypto_max: float | None  # si crypto
    applicable_max: float  # min des plafonds qui visent ce ticker
    applicable_max_cad: float | None
    outside_policy: bool
    reasons: list[str] = field(default_factory=list)
    sandbox_only: bool = False  # biais FOMO : la demande ne passe que par le bac a sable
    cooldown_days: int = 0
    limits: list[Limit] = field(default_factory=list)  # sat.sandbox (a ajouter pour l'optimisation « avec »)


@dataclass
class CompileResult:
    policy: PolicySpec | None
    level: str
    R: float
    capacity: dict[str, Any]
    tolerance: dict[str, Any]
    decision_kind: DecisionKind | None
    emphasis: dict[str, float]
    trace: list[dict[str, Any]]
    missing_defaults: list[str]
    status: str  # COMPLETE | INCOMPLETE | PROTECTION (effectif)
    level_from_R: str  # noqa: N815 (champ public fige : lu par la selection de strategie et par les tests)
    horizon_years: float | None  # T du seau risque
    l_star: float | None
    e_cap: float | None  # part actions max (fraction)
    limits: list[Limit] = field(default_factory=list)  # meme si policy est None
    buckets: list[dict[str, Any]] = field(default_factory=list)
    emphasis_rules: list[str] = field(default_factory=list)
    request: RequestView | None = None
    near_cutoff: bool = False  # R a moins de levels.hysteresis d'une coupure

    def policy_with_request(self) -> PolicySpec | None:
        """PolicySpec + limite sat.sandbox de la demande (pour l'optimisation « avec demande »)."""
        if self.policy is None or self.request is None or not self.request.limits:
            return self.policy
        data = self.policy.model_dump()
        limits = [*self.policy.limits, *self.request.limits]
        data["limits"] = [limit.model_dump() for limit in limits]
        return PolicySpec.model_validate(data)
