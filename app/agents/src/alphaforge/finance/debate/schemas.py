"""Contrats du débat : plaidoyer, rapports de lentille, amendements, tours.

Proposition v0.1 (2026-11-14), à intégrer à ``contracts/`` une fois validée par l'équipe.
Les lentilles ne produisent JAMAIS de poids : seulement des amendements d'une liste fermée qui ne
peuvent que resserrer le mandat. Le code les valide, les applique et réoptimise.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Lens = Literal["timeline", "risk", "diversity", "constraints"]
LENSES: tuple[Lens, ...] = ("timeline", "risk", "diversity", "constraints")
# Noms des lentilles dans les textes montrés (roles.LENS_PROMPTS) : l'identifiant reste dans la trace et les fact_id.
LENS_FR: dict[Lens, str] = {
    "timeline": "horizon",
    "risk": "risque",
    "diversity": "diversité et préférences",
    "constraints": "contraintes",
}

# Ordre de priorité quand deux amendements se contredisent (le plus prioritaire gagne).
PRIORITY: dict[Lens, int] = {"constraints": 0, "risk": 1, "timeline": 2, "diversity": 3}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Amendment(_Strict):
    """Changement borné proposé par une lentille. ``target`` dépend de ``kind`` :

    - ``tighten_limit`` : rule_id d'une limite existante ; ``value`` = nouveau max (< max actuel)
    - ``cap_group``     : rule_id d'une limite group_weight/exposure existante ; ``value`` = nouveau max
    - ``exclude_asset`` : ticker de l'univers ; ``value`` ignoré
    - ``require_min_group`` : rule_id d'une limite group_weight existante ; ``value`` = nouveau min
    - ``switch_risk_measure`` : "CDAR" (seul passage admis : vers une mesure plus prudente)
    - ``flag_only``     : point d'attention, aucun changement
    """

    kind: Literal[
        "tighten_limit", "cap_group", "exclude_asset", "require_min_group", "switch_risk_measure", "flag_only"
    ]
    target: str
    value: float | None = None
    reason_fr: str = Field(max_length=400)
    evidence_fact_ids: list[str] = Field(min_length=1)


class Point(_Strict):
    text_fr: str = Field(max_length=400)
    fact_ids: list[str] = Field(default_factory=list)


class LensReport(_Strict):
    """Sortie structurée d'une lentille pour un tour."""

    lens: Lens
    support: list[Point] = Field(default_factory=list, max_length=4)
    objections: list[Point] = Field(default_factory=list, max_length=4)
    amendments: list[Amendment] = Field(default_factory=list, max_length=3)


class AdvocacyBrief(_Strict):
    """Plaidoyer de A3 pour le candidat (il n'est montré aux lentilles qu'au tour 2)."""

    thesis_fr: str = Field(max_length=600)
    arguments: list[Point] = Field(default_factory=list, max_length=5)
    rebuttals: list[Point] = Field(default_factory=list, max_length=5)  # tour 2 seulement


class AppliedAmendment(_Strict):
    lens: Lens
    amendment: Amendment
    status: Literal["applique", "rejete"]
    why_fr: str
    before: float | str | None = None
    after: float | str | None = None


class DebateRound(_Strict):
    round: Literal[1, 2]
    candidate_fact_ids: list[str]
    advocate: AdvocacyBrief | None = None
    lens_reports: list[LensReport]
    emphasis: dict[str, float]
    decisions: list[AppliedAmendment] = Field(default_factory=list)
    # Tour 2 : verdict par lentille calculé par le code, jamais « levé » par persuasion.
    verdicts: dict[str, Literal["soutien", "objection_maintenue", "objection_satisfaite"]] = Field(default_factory=dict)
