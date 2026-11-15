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
    q: Questionnaire, dimension: str, values: dict[str, Any], risk: dict[str, Any], locale: str
) -> str | None:
    if dimension == "risk_tolerance":
        return rules.level_label(q, risk["tolerance"], locale)
    if dimension == "risk_capacity":
        return rules.level_label(q, risk["capacity"], locale)
    parts = []
    for spec in q.fields.values():
        if spec.dimension != dimension or not spec.summary or values.get(spec.id) is None:
            continue
        if not q.applicable(spec.when, values):
            continue
        text = format_field_value(spec, values[spec.id], locale)
        parts.append(text if spec.type == "enum" else f"{spec.label_text(locale)} : {text}")
    return " · ".join(parts) or None


def profile_view(
    q: Questionnaire, session: ClientSession, locale: str, documents: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    values = session.values()
    risk = rules.risk_profile(q, values)
    dimensions: dict[str, Any] = {}
    for dimension in VIEW_DIMENSIONS:
        required = [
            spec
            for spec in q.fields.values()
            if spec.dimension == dimension and spec.weight > 0 and q.applicable(spec.when, values)
        ]
        known_required = [spec for spec in required if rules.field_known(q, spec.id, values)]
        if required and len(known_required) == len(required):
            status = "known"
        elif known_required:
            status = "partial"
        else:
            status = "missing"
        fields = {
            spec.name: values[spec.id]
            for spec in q.fields.values()
            if spec.dimension == dimension and values.get(spec.id) is not None
        }
        dimensions[dimension] = {
            "status": status,
            "summary": dimension_summary(q, dimension, values, risk, locale),
            "fields": fields,
        }
    facts = [
        {"field": field_id, "value": fact.get("value"), "provenance": fact.get("provenance"), "at": fact.get("at")}
        # Une valeur à confirmer n'est pas encore un fait du profil (la valeur confirmée qu'elle remplace l'est).
        for field_id, fact in sorted(
            session.confirmed_facts().items(), key=lambda item: (item[1].get("at") or "", item[0])
        )
    ]
    return {
        "knowledge_level": rules.knowledge_level(q, values),
        "effective_risk": risk["effective"],
        "risk": risk,
        "dimensions": dimensions,
        "facts": facts,
        "documents": documents or [],
    }


def completeness_view(q: Questionnaire, session: ClientSession, locale: str) -> dict[str, Any]:
    return rules.completeness(q, session.values(), locale)


def current_questions(q: Questionnaire, session: ClientSession, locale: str) -> list[dict[str, Any]]:
    if session.stage == "base_questions":
        question = q.next_question(session.values(), session.answers)
        return [q.render(question, locale)] if question else []
    if session.stage == "followups":
        return list(session.data.get("pending_questions") or [])
    return []


def client_state(
    q: Questionnaire,
    session: ClientSession,
    *,
    locale: str,
    trace: Trace,
    message: str | None = None,
    portfolio: dict[str, Any] | None = None,
    documents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "client_id": session.client_id,
        "locale": locale,
        "stage": session.stage,
        "message": message,
        "questions": current_questions(q, session, locale),
        "profile": profile_view(q, session, locale, documents),
        "completeness": completeness_view(q, session, locale),
        "portfolio": portfolio,
        "trace": trace.steps,
    }
