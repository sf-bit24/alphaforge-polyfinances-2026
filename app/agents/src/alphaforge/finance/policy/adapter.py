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
from typing import Literal

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

    def model_post_init(self, _ctx) -> None:
        if any(not 0 <= v <= 1 for v in self.tolerance_subscores.values()):
            raise ValueError("tolerance_subscores : valeurs dans [0, 1]")
        if self.poche_liquide_cad > self.M_cad:
            raise ValueError("poche_liquide_cad > M_cad")


def load_adapter_config(path: str | Path | None = None) -> dict:
    with open(path or ADAPTER_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def aggregate_tolerance(sub: dict[str, float], cfg: dict) -> float | None:
    """Agregat 0-1 des sous-scores presents, selon tolerance.aggregation."""
    if not sub:
        return None
    t = cfg["tolerance"]
    if t["aggregation"] == "min":
        return min(sub.values())
    if t["aggregation"] == "mean_minus_half_range":
        w = {k: t["weights"][k] for k in sub}
        mean = sum(w[k] * sub[k] for k in sub) / sum(w.values())
        return max(0.0, mean - t["range_penalty"] * (max(sub.values()) - min(sub.values())))
    raise ValueError(f"questionnaire_adapter.yaml : agregation inconnue {t['aggregation']}")


def apply_questionnaire(
    p: InvestorProfile, q: QuestionnaireScores, cfg: dict | None = None
) -> tuple[InvestorProfile, dict, list[dict]]:
    """Retourne (profil adapte, options pour F1, trace)."""
    cfg = cfg or load_adapter_config()
    ver = cfg["version"]
    src = lambda k: f"questionnaire_adapter.yaml@{ver}#{k}"  # noqa: E731
    trace: list[dict] = []
    upd: dict = {}
    W_risk = q.M_cad - q.poche_liquide_cad
    upd["investable_wealth"] = W_risk
    trace.append(
        {
            "rule": "questionnaire.M_risque",
            "inputs": {"M_cad": q.M_cad, "poche_liquide_cad": q.poche_liquide_cad},
            "output": W_risk,
            "yaml_path": src("liquid_pocket"),
        }
    )
    agg = aggregate_tolerance(dict(q.tolerance_subscores), cfg)
    if agg is not None:
        t = cfg["tolerance"]
        conf = (
            q.tolerance_confidence
            if q.tolerance_confidence is not None
            else (t["single_subscore_confidence"] if len(q.tolerance_subscores) == 1 else t["default_confidence"])
        )
        upd["tolerance_declared"] = Score(
            value=round(100 * agg, 6), confidence=conf, method=f"questionnaire brain, agregation {t['aggregation']}"
        )
        upd["tolerance_tested"] = None
        trace.append(
            {
                "rule": "questionnaire.tolerance",
                "inputs": dict(q.tolerance_subscores),
                "output": {"value": 100 * agg, "confidence": conf},
                "yaml_path": src("tolerance.aggregation"),
            }
        )
    if q.capacity_score is not None:
        cap = q.capacity_score * cfg["capacity"]["scale"]
        prev = p.capacity_assessed.value if p.capacity_assessed else None
        upd["capacity_assessed"] = Score(
            value=min(cap, prev) if prev is not None else cap, method="questionnaire brain"
        )
        trace.append(
            {
                "rule": "questionnaire.capacity",
                "inputs": {"capacity_score": q.capacity_score, "previous": prev},
                "output": upd["capacity_assessed"].value,
                "yaml_path": src("capacity"),
            }
        )
    notes = []
    if q.L_cad is not None:
        upd["max_acceptable_loss_cad"] = q.L_cad
        if cfg["loss"]["drop_pct_when_L_given"]:
            upd["max_acceptable_loss_pct"] = None
        if not q.L_confirmed:
            notes.append("L_cad non confirme (SF-19) : applique quand meme (il ne peut que resserrer)")
        trace.append(
            {
                "rule": "questionnaire.L",
                "inputs": {"L_cad": q.L_cad, "M_risque": W_risk, "confirmed": q.L_confirmed},
                "output": q.L_cad / W_risk if W_risk else None,
                "yaml_path": src("loss"),
            }
        )
    if q.completeness is not None:
        upd["confidence"] = min(q.completeness, p.confidence) if p.confidence is not None else q.completeness
    unknown = set(q.covered_goal_ids) - {g.goal_id for g in p.goals}
    if unknown:
        raise ValueError(f"covered_goal_ids inconnus : {sorted(unknown)}")
    if len(q.covered_goal_ids) == len(p.goals) and p.goals:
        raise ValueError("la poche liquide couvre tous les objectifs : aucun seau risque a compiler")
    newp = InvestorProfile.model_validate(
        {**p.model_dump(), **{k: (v.model_dump() if isinstance(v, BaseModel) else v) for k, v in upd.items()}}
    )
    opts = {
        "covered_goal_ids": set(q.covered_goal_ids),
        "sequence_reserve_years": q.sequence_reserve_years,
        "liquid_pocket_cad": q.poche_liquide_cad,
        "bucket_level": cfg["liquid_pocket"]["bucket_level"],
        "notes": notes,
    }
    return newp, opts, trace
