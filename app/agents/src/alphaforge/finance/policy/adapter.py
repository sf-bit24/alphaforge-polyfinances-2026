"""Adaptateur questionnaire (brain product/questionnaire-profil.md) -> InvestorProfile pour F1.

Le questionnaire calcule ses propres scores (tolerance composite, capacite, perte admissible L en $,
poche liquide). F1 garde risk_levels.yaml v0.2 comme moteur de reference : l'adaptateur traduit ces
sorties en champs du profil que F1 consomme deja, sans compter deux fois un meme fait :
- tolerance : un seul Score agrege (tolerance_tested retire, le test est dans l'agregat) ;
- capacite : capacity_assessed, combine par min (jamais cumule) avec la capacite calculee par F1 ;
- perte : L -> max_acceptable_loss_cad sur M_risque ; le % declare est retire (deja dans L) ;
- poche liquide : retiree de investable_wealth ; ses objectifs sortent de T et de q ; pas de seconde
  reserve de retraits si la poche couvre deja la zone de sequence.
Le stress 2022 du questionnaire n'est PAS utilise pour choisir le niveau (voir README).
SIMULATION SEULEMENT.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from alphaforge.finance.contracts.profile import InvestorProfile, Score

ADAPTER_FILE = Path(__file__).with_name("questionnaire_adapter.yaml")
SubScore = Literal["declared", "scenarios", "revealed", "test"]


class QuestionnaireScores(BaseModel):
    """Sorties chiffrees du questionnaire (identifiants de questions du brain entre parentheses)."""

    model_config = ConfigDict(extra="forbid")

    M_cad: float = Field(gt=0)  # SF-00 (borne prudente de tranche)
    poche_liquide_cad: float = Field(default=0.0, ge=0)  # OB-03, OB-06 < 3 ans, CT-09, SF-16
    L_cad: float | None = Field(default=None, ge=0)  # L = min(L_cap, L_tol), sur M_risque
    L_confirmed: bool = False  # SF-19
    tolerance_subscores: dict[SubScore, float] = Field(default_factory=dict)  # 0-1
    tolerance_confidence: float | None = Field(default=None, ge=0, le=1)
    capacity_score: float | None = Field(default=None, ge=0, le=1)  # 0-1, plafonds du brain inclus
    covered_goal_ids: list[str] = Field(default_factory=list)  # objectifs finances par la poche
    sequence_reserve_years: float | None = Field(default=None, ge=0)  # annees de retraits deja dans la poche
    completeness: float | None = Field(default=None, ge=0, le=1)

    def model_post_init(self, _context) -> None:
        if any(not 0 <= score <= 1 for score in self.tolerance_subscores.values()):
            raise ValueError("tolerance_subscores : valeurs dans [0, 1]")
        if self.poche_liquide_cad > self.M_cad:
            raise ValueError("poche_liquide_cad > M_cad")


def load_adapter_config(path: str | Path | None = None) -> dict:
    with open(path or ADAPTER_FILE, encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def aggregate_tolerance(subscores: dict[str, float], config: dict) -> float | None:
    """Agregat 0-1 des sous-scores presents, selon tolerance.aggregation."""
    if not subscores:
        return None
    rules = config["tolerance"]
    if rules["aggregation"] == "min":
        return min(subscores.values())
    if rules["aggregation"] == "mean_minus_half_range":
        weights = {name: rules["weights"][name] for name in subscores}
        mean = sum(weights[name] * subscores[name] for name in subscores) / sum(weights.values())
        return max(0.0, mean - rules["range_penalty"] * (max(subscores.values()) - min(subscores.values())))
    raise ValueError(f"questionnaire_adapter.yaml : agregation inconnue {rules['aggregation']}")


class _AdapterTrace:
    """Trace des traductions du questionnaire ; chaque entree cite questionnaire_adapter.yaml@<version>#<cle>."""

    def __init__(self, version: str):
        self.version = version
        self.entries: list[dict] = []

    def record(self, rule: str, inputs: dict, output: Any, key: str) -> None:
        self.entries.append(
            {
                "rule": rule,
                "inputs": inputs,
                "output": output,
                "yaml_path": f"questionnaire_adapter.yaml@{self.version}#{key}",
            }
        )


def _tolerance_updates(questionnaire: QuestionnaireScores, config: dict, trace: _AdapterTrace) -> dict[str, Any]:
    """Un seul Score agrege ; tolerance_tested est retire, le test etant deja dans l'agregat."""
    aggregate = aggregate_tolerance(dict(questionnaire.tolerance_subscores), config)
    if aggregate is None:
        return {}
    rules = config["tolerance"]
    if questionnaire.tolerance_confidence is not None:
        confidence = questionnaire.tolerance_confidence
    elif len(questionnaire.tolerance_subscores) == 1:
        confidence = rules["single_subscore_confidence"]
    else:
        confidence = rules["default_confidence"]
    declared = Score(
        value=round(100 * aggregate, 6),
        confidence=confidence,
        method=f"questionnaire brain, agregation {rules['aggregation']}",
    )
    trace.record(
        "questionnaire.tolerance",
        dict(questionnaire.tolerance_subscores),
        {"value": 100 * aggregate, "confidence": confidence},
        "tolerance.aggregation",
    )
    return {"tolerance_declared": declared, "tolerance_tested": None}


def _capacity_updates(
    profile: InvestorProfile, questionnaire: QuestionnaireScores, config: dict, trace: _AdapterTrace
) -> dict[str, Any]:
    """capacity_assessed : la capacite du questionnaire, ou celle deja evaluee si elle est plus basse."""
    if questionnaire.capacity_score is None:
        return {}
    capacity = questionnaire.capacity_score * config["capacity"]["scale"]
    previous = profile.capacity_assessed.value if profile.capacity_assessed else None
    assessed = Score(value=min(capacity, previous) if previous is not None else capacity, method="questionnaire brain")
    trace.record(
        "questionnaire.capacity",
        {"capacity_score": questionnaire.capacity_score, "previous": previous},
        assessed.value,
        "capacity",
    )
    return {"capacity_assessed": assessed}


def _loss_updates(
    questionnaire: QuestionnaireScores, risk_wealth: float, config: dict, trace: _AdapterTrace
) -> dict[str, Any]:
    """L devient max_acceptable_loss_cad sur M_risque ; le % declare est retire, car il est deja dans L."""
    if questionnaire.L_cad is None:
        return {}
    updates: dict[str, Any] = {"max_acceptable_loss_cad": questionnaire.L_cad}
    if config["loss"]["drop_pct_when_L_given"]:
        updates["max_acceptable_loss_pct"] = None
    trace.record(
        "questionnaire.L",
        {"L_cad": questionnaire.L_cad, "M_risque": risk_wealth, "confirmed": questionnaire.L_confirmed},
        questionnaire.L_cad / risk_wealth if risk_wealth else None,
        "loss",
    )
    return updates


def _notes(questionnaire: QuestionnaireScores) -> list[str]:
    if questionnaire.L_cad is not None and not questionnaire.L_confirmed:
        return ["L_cad non confirme (SF-19) : applique quand meme (il ne peut que resserrer)"]
    return []


def _check_covered_goals(profile: InvestorProfile, questionnaire: QuestionnaireScores) -> None:
    unknown = set(questionnaire.covered_goal_ids) - {goal.goal_id for goal in profile.goals}
    if unknown:
        raise ValueError(f"covered_goal_ids inconnus : {sorted(unknown)}")
    if len(questionnaire.covered_goal_ids) == len(profile.goals) and profile.goals:
        raise ValueError("la poche liquide couvre tous les objectifs : aucun seau risque a compiler")


def apply_questionnaire(
    profile: InvestorProfile, questionnaire: QuestionnaireScores, config: dict | None = None
) -> tuple[InvestorProfile, dict, list[dict]]:
    """Retourne (profil adapte, options pour F1, trace)."""
    config = config or load_adapter_config()
    trace = _AdapterTrace(config["version"])
    risk_wealth = questionnaire.M_cad - questionnaire.poche_liquide_cad  # M_risque
    trace.record(
        "questionnaire.M_risque",
        {"M_cad": questionnaire.M_cad, "poche_liquide_cad": questionnaire.poche_liquide_cad},
        risk_wealth,
        "liquid_pocket",
    )
    updates: dict[str, Any] = {"investable_wealth": risk_wealth}
    updates.update(_tolerance_updates(questionnaire, config, trace))
    updates.update(_capacity_updates(profile, questionnaire, config, trace))
    updates.update(_loss_updates(questionnaire, risk_wealth, config, trace))
    if questionnaire.completeness is not None:
        updates["confidence"] = (
            min(questionnaire.completeness, profile.confidence)
            if profile.confidence is not None
            else questionnaire.completeness
        )
    _check_covered_goals(profile, questionnaire)
    adapted = InvestorProfile.model_validate(
        {
            **profile.model_dump(),
            **{
                name: (value.model_dump() if isinstance(value, BaseModel) else value) for name, value in updates.items()
            },
        }
    )
    options = {
        "covered_goal_ids": set(questionnaire.covered_goal_ids),
        "sequence_reserve_years": questionnaire.sequence_reserve_years,
        "liquid_pocket_cad": questionnaire.poche_liquide_cad,
        "bucket_level": config["liquid_pocket"]["bucket_level"],
        "notes": _notes(questionnaire),
    }
    return adapted, options, trace.entries
