"""Règles déterministes du profil : niveau de connaissances, risque effectif et complétude.

Les barèmes sont dans ``questionnaire.yaml`` (section ``rules``); ce module applique toujours la même logique.
À relire par le volet finance de l'équipe larpathon.

Niveau de connaissances
    total = points de fréquence des placements (0 à 3) + points du suivi de l'actualité (0 à 3)
    + points des produits connus (0 à 3). Niveau mesuré : débutant de 0 à 2, intermédiaire de 3 à 5,
    avancé de 6 à 9. Niveau retenu = min(auto-évaluation, niveau mesuré + 1 cran). Un niveau fixé dans les
    réglages (provenance ``settings``) remplace le calcul.

Risque effectif (échelle 0 = low, 1 = low_medium, 2 = medium, 3 = medium_high, 4 = high)
    tolérance = partie entière de la moyenne des points connus (réaction à une baisse de 20 %, attitude face
    aux variations, et comportement lors d'une baisse réelle si A1 l'a appris et qu'elle a été vécue);
    capacité = partie entière de la moyenne des trois composantes (fonds d'urgence, stabilité des revenus,
    effet d'une perte), plafonnée par l'horizon (< 3 ans : 1; 3 à 10 ans : 3), le besoin de liquidité
    (une partie : 3; une part importante : 1), un impact majeur d'une perte (1) et une dette coûteuse (2);
    risque effectif = min(tolérance, capacité). Une composante requise inconnue donne ``None`` : le code ne
    devine aucune valeur.

Complétude
    score = somme des poids des champs applicables connus / somme des poids des champs applicables;
    ``displayed`` = min(score, cap); ``ready`` = score >= threshold.
"""

from __future__ import annotations

import math
from typing import Any

from .questionnaire import Questionnaire

LEVELS_KNOWLEDGE = ("beginner", "intermediate", "advanced")


def _points(table: dict[str, Any], value: Any) -> float | None:
    if value is None:
        return None
    key = str(value).lower() if isinstance(value, bool) else value
    if key in table:
        return float(table[key])
    return None


# ---------------------------------------------------------------------- niveau de connaissances
def measured_knowledge_points(q: Questionnaire, values: dict[str, Any]) -> int | None:
    rule = q.rules["knowledge_level"]
    total = 0.0
    for field_id, table in rule["points"].items():
        points = _points(table, values.get(field_id))
        if points is None:
            return None
        total += points
    products = values.get("knowledge.products_known")
    if products is None:
        return None
    core = sum(1 for p in products if p in rule["products"]["core"])
    advanced = any(p in rule["products"]["advanced"] for p in products)
    if core == 0:
        product_points = 0
    elif core <= 2:
        product_points = 1
    elif advanced:
        product_points = 3
    else:
        product_points = 2
    return int(total) + product_points


def measured_knowledge_level(q: Questionnaire, values: dict[str, Any]) -> str | None:
    points = measured_knowledge_points(q, values)
    if points is None:
        return None
    bands = q.rules["knowledge_level"]["bands"]
    level = "beginner"
    for name in LEVELS_KNOWLEDGE:
        if points >= bands[name]:
            level = name
    return level


def computed_knowledge_level(q: Questionnaire, values: dict[str, Any]) -> str | None:
    measured = measured_knowledge_level(q, values)
    declared = values.get("knowledge.self_assessment")
    if measured is None or declared not in LEVELS_KNOWLEDGE:
        return None
    margin = int(q.rules["knowledge_level"].get("self_assessment_margin", 1))
    ceiling = min(LEVELS_KNOWLEDGE.index(measured) + margin, len(LEVELS_KNOWLEDGE) - 1)
    return LEVELS_KNOWLEDGE[min(LEVELS_KNOWLEDGE.index(declared), ceiling)]


def knowledge_level(q: Questionnaire, values: dict[str, Any]) -> str | None:
    override = values.get("knowledge.level")
    if override in LEVELS_KNOWLEDGE:
        return override
    return computed_knowledge_level(q, values)


# ---------------------------------------------------------------------- risque
def risk_levels(q: Questionnaire) -> tuple[str, ...]:
    return tuple(q.rules["risk"]["levels"])


def tolerance_score(q: Questionnaire, values: dict[str, Any]) -> int | None:
    rule = q.rules["risk"]["tolerance"]
    if any(values.get(field_id) is None for field_id in rule["required"]):
        return None
    scores = []
    for field_id, table in rule["points"].items():
        points = _points(table, values.get(field_id))
        if points is not None:
            scores.append(points)
    if not scores:
        return None
    return int(math.floor(sum(scores) / len(scores)))


def capacity_score(q: Questionnaire, values: dict[str, Any]) -> int | None:
    rule = q.rules["risk"]["capacity"]
    if any(values.get(field_id) is None for field_id in rule["required"]):
        return None
    scores = []
    for field_id, table in rule["points"].items():
        points = _points(table, values.get(field_id))
        if points is None:
            return None
        scores.append(points)
    for field_id, thresholds in rule["thresholds"].items():
        number = float(values[field_id])
        points = None
        for minimum, value in thresholds:
            if number >= float(minimum):
                points = float(value)
        if points is None:
            return None
        scores.append(points)
    score = int(math.floor(sum(scores) / len(scores)))
    for field_id, caps in rule["caps"].items():
        cap = _points(caps, values.get(field_id))
        if cap is not None:
            score = min(score, int(cap))
    return score


def risk_profile(q: Questionnaire, values: dict[str, Any]) -> dict[str, str | None]:
    levels = risk_levels(q)
    tolerance = tolerance_score(q, values)
    capacity = capacity_score(q, values)
    effective = None if tolerance is None or capacity is None else min(tolerance, capacity)
    return {
        "tolerance": levels[tolerance] if tolerance is not None else None,
        "capacity": levels[capacity] if capacity is not None else None,
        "effective": levels[effective] if effective is not None else None,
    }


def level_label(q: Questionnaire, level: str | None, locale: str, *, effective: bool = False) -> str | None:
    if level is None:
        return None
    labels = q.rules["risk"]["effective_labels" if effective else "level_labels"]
    entry = labels.get(level) or {}
    return entry.get(locale) or entry.get("fr") or level


# ---------------------------------------------------------------------- complétude
def field_known(q: Questionnaire, field_id: str, values: dict[str, Any]) -> bool:
    spec = q.fields[field_id]
    if spec.computed and field_id == "knowledge.level":
        return knowledge_level(q, values) is not None
    value = values.get(field_id)
    return value is not None and not (isinstance(value, list) and not value and spec.type != "multi_enum")


def completeness(q: Questionnaire, values: dict[str, Any], locale: str = "fr") -> dict[str, Any]:
    total = 0.0
    known = 0.0
    missing: list[tuple[float, int, dict[str, Any]]] = []
    for index, spec in enumerate(q.fields.values()):
        if spec.weight <= 0 or not q.applicable(spec.when, values):
            continue
        total += spec.weight
        if field_known(q, spec.id, values):
            known += spec.weight
        else:
            missing.append(
                (
                    -spec.weight,
                    index,
                    {"dimension": spec.dimension, "field": spec.name, "label": spec.label_text(locale)},
                )
            )
    score = round(known / total, 4) if total else 0.0
    missing.sort(key=lambda item: (item[0], item[1]))
    return {
        "score": score,
        "displayed": round(min(score, q.cap), 4),
        "threshold": q.threshold,
        "cap": q.cap,
        "ready": score >= q.threshold,
        "missing": [entry for _, _, entry in missing],
    }


def missing_fields(q: Questionnaire, values: dict[str, Any]) -> list[str]:
    """Identifiants complets des champs requis manquants, du plus lourd au plus léger."""
    out = []
    for spec in sorted(q.fields.values(), key=lambda s: -s.weight):
        if spec.weight > 0 and q.applicable(spec.when, values) and not field_known(q, spec.id, values):
            out.append(spec.id)
    return out
