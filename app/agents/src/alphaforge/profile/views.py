"""Vues renvoyées au client : ``ClientState``, ``ProfileView`` et ``Completeness`` (CONTRACTS.md 3.2 et 3.3)."""

from __future__ import annotations

from typing import Any

from ..trace import Trace
from . import rules
from .questionnaire import Questionnaire, format_field_value
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
    questionnaire: Questionnaire, dimension: str, values: dict[str, Any], risk: dict[str, Any], locale: str
) -> str | None:
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
        text = format_field_value(spec, values[spec.id], locale)
        parts.append(text if spec.type == "enum" else f"{spec.label_text(locale)} : {text}")
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


def _confirmed_facts_by_date(session: ClientSession) -> list[dict[str, Any]]:
    # Une valeur à confirmer n'est pas encore un fait du profil (la valeur confirmée qu'elle remplace l'est).
    confirmed = sorted(session.confirmed_facts().items(), key=lambda item: (item[1].get("at") or "", item[0]))
    return [
        {"field": field_id, "value": fact.get("value"), "provenance": fact.get("provenance"), "at": fact.get("at")}
        for field_id, fact in confirmed
    ]


def profile_view(
    questionnaire: Questionnaire, session: ClientSession, locale: str, documents: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    values = session.values()
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
            "summary": dimension_summary(questionnaire, dimension, values, risk, locale),
            "fields": fields,
        }
    facts = _confirmed_facts_by_date(session)
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
