"""Vues renvoyées au client : ``ClientState``, ``ProfileView`` et ``Completeness`` (CONTRACTS.md 3.2 et 3.3)."""

from __future__ import annotations

from typing import Any

from ..trace import Trace
from . import rules
from .questionnaire import Questionnaire, band_brief, fact_band, fact_label, format_fact, labeled
from .state import ClientSession

VIEW_DIMENSIONS = (
    "objective",
    "horizon",
    "risk_tolerance",
    "risk_capacity",
    "constraints",
    "preferences",
    "context",
)


def dimension_summary(
    questionnaire: Questionnaire,
    dimension: str,
    facts: dict[str, dict[str, Any]],
    risk: dict[str, Any],
    locale: str,
) -> str | None:
    """Résumé d'une dimension à partir des faits confirmés. Un fait répondu par une tranche montre la tranche,
    pas la borne que le code retient (``format_fact``). Le séparateur suit la langue (``labeled``)."""
    values = {field_id: fact.get("value") for field_id, fact in facts.items()}
    if dimension == "risk_tolerance":
        return rules.level_label(questionnaire, risk["tolerance"], locale)
    if dimension == "risk_capacity":
        return rules.level_label(questionnaire, risk["capacity"], locale)
    parts = []
    for spec in questionnaire.fields.values():
        if spec.dimension != dimension or not spec.summary or values.get(spec.id) is None:
            continue
        if not questionnaire.applicable(spec.when, values):
            continue
        text = format_fact(spec, facts[spec.id], locale)
        parts.append(text if spec.type == "enum" else labeled(spec.label_text(locale), text, locale))
    return " · ".join(parts) or None


def _dimension_status(questionnaire: Questionnaire, dimension: str, values: dict[str, Any]) -> str:
    """``known`` quand tous les champs requis de la dimension sont connus, ``partial`` quand une partie l'est."""
    required = [
        spec
        for spec in questionnaire.fields.values()
        if spec.dimension == dimension and spec.weight > 0 and questionnaire.applicable(spec.when, values)
    ]
    known_required = [spec for spec in required if rules.field_known(questionnaire, spec.id, values)]
    if required and len(known_required) == len(required):
        return "known"
    if known_required:
        return "partial"
    return "missing"


def _fact_view(questionnaire: Questionnaire, field_id: str, fact: dict[str, Any], locale: str) -> dict[str, Any]:
    """Un fait de ``ProfileView``. Champs facultatifs, dans la langue de la vue : ``label``, la valeur telle que
    l'investisseur la lit (« Plutôt stables », « CELI, REER », « Oui »), et ``band``, la tranche choisie pour une
    réponse numérique. ``value`` reste le code ou le nombre que lit le volet finance."""
    view = {"field": field_id, "value": fact.get("value"), "provenance": fact.get("provenance"), "at": fact.get("at")}
    spec = questionnaire.fields.get(field_id)
    if spec is not None:
        view["label"] = fact_label(spec, fact, locale)
    band = fact_band(fact)
    if band is not None:
        view["band"] = band_brief(band, locale)
    return view


def _confirmed_facts_by_date(questionnaire: Questionnaire, session: ClientSession, locale: str) -> list[dict[str, Any]]:
    # Une valeur à confirmer n'est pas encore un fait du profil (la valeur confirmée qu'elle remplace l'est).
    confirmed = sorted(session.confirmed_facts().items(), key=lambda item: (item[1].get("at") or "", item[0]))
    return [_fact_view(questionnaire, field_id, fact, locale) for field_id, fact in confirmed]


def profile_view(
    questionnaire: Questionnaire, session: ClientSession, locale: str, documents: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    values = session.values()
    confirmed = session.confirmed_facts()
    risk = rules.risk_profile(questionnaire, values)
    dimensions: dict[str, Any] = {}
    for dimension in VIEW_DIMENSIONS:
        status = _dimension_status(questionnaire, dimension, values)
        fields = {
            spec.name: values[spec.id]
            for spec in questionnaire.fields.values()
            if spec.dimension == dimension and values.get(spec.id) is not None
        }
        dimensions[dimension] = {
            "status": status,
            "summary": dimension_summary(questionnaire, dimension, confirmed, risk, locale),
            "fields": fields,
        }
    facts = _confirmed_facts_by_date(questionnaire, session, locale)
    return {
        "knowledge_level": rules.knowledge_level(questionnaire, values),
        "effective_risk": risk["effective"],
        "risk": risk,
        "dimensions": dimensions,
        "facts": facts,
        "documents": documents or [],
    }


def completeness_view(questionnaire: Questionnaire, session: ClientSession, locale: str) -> dict[str, Any]:
    return rules.completeness(questionnaire, session.values(), locale)


def current_questions(questionnaire: Questionnaire, session: ClientSession, locale: str) -> list[dict[str, Any]]:
    if session.stage == "base_questions":
        question = questionnaire.next_question(session.values(), session.answers)
        return [questionnaire.render(question, locale)] if question else []
    if session.stage == "followups":
        return list(session.data.get("pending_questions") or [])
    return []


def client_state(  # noqa: PLR0913 - signature gardée : le service l'appelle par mots-clés
    questionnaire: Questionnaire,
    session: ClientSession,
    *,
    locale: str,
    trace: Trace,
    message: str | None = None,
    portfolio: dict[str, Any] | None = None,
    documents: list[dict[str, Any]] | None = None,
    client_kb: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = {
        "client_id": session.client_id,
        "locale": locale,
        "stage": session.stage,
        "message": message,
        "questions": current_questions(questionnaire, session, locale),
        "profile": profile_view(questionnaire, session, locale, documents),
        "completeness": completeness_view(questionnaire, session, locale),
        "portfolio": portfolio,
        "trace": trace.steps,
    }
    if client_kb is not None:
        # Knowledge Base du client (CONTRACTS.md 3.3) : statut, identifiant, documents indexés, clés en attente.
        state["client_kb"] = client_kb
    return state
