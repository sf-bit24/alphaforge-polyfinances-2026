"""Vérification des entrées et des sorties.

Entrées : Bedrock Guardrails (version numérotée) — sujets interdits (conseil réel, ordres, garanties),
attaques de prompt, données personnelles anonymisées (NAS canadien compris).
Sorties : vérificateur numérique DÉTERMINISTE — chaque nombre d'une phrase doit correspondre à un
``Fact`` que la phrase cite (formats français : « 3,4 % », « 0,034 », « 50 000 $ », « -31 % ») —
puis ancrage contextuel Guardrails contre les faits (score, seuil 0,75).
Chaque vérification est tracée (span + événement) et rend un rapport structuré.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..contracts import Decision, Fact
from .telemetry import log_event, span

# nombre FR : « 50 000 », « 3,4 », « 0.034 », « -31 », suivi éventuellement de % ou $
_NUM = re.compile(r"(?<![\w./:-])([-−+]?(?:\d{1,3}(?:[  ]\d{3})+|\d+)(?:[.,]\d+)?)\s?(%|\$|\s?pts?\b|\s?points?\b)?")
_FACT_TOKEN = re.compile(r"\b[\w.-]+(?::[\w.\[\]-]+)+")  # fact_id du type judge-check:risk.cvar_m:max
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")


@dataclass
class NumberClaim:
    raw: str
    value: float
    unit: str  # "%", "$", "pts" ou ""
    decimals: int


@dataclass
class NumberCheck:
    ok: bool
    matched: list[tuple[str, str]] = field(default_factory=list)  # (texte, fact_id)
    unmatched: list[str] = field(default_factory=list)


def extract_numbers(text: str) -> list[NumberClaim]:
    cleaned = _ISO_DATE.sub(" ", _FACT_TOKEN.sub(" ", text))
    claims = []
    for match in _NUM.finditer(cleaned):
        raw, unit = match.group(1), (match.group(2) or "").strip()
        unit = "pts" if unit.startswith("p") else unit
        digits = raw.replace("−", "-").replace(" ", "").replace(" ", "")
        decimals = len(re.split(r"[.,]", digits)[1]) if re.search(r"[.,]", digits) else 0
        value = float(digits.replace(",", "."))
        if not unit and decimals == 0 and 1900 <= abs(value) <= 2100:  # année
            continue
        claims.append(NumberClaim(match.group(0).strip(), value, unit, decimals))
    return claims


def _matches(claim: NumberClaim, fact_value: float) -> bool:
    """Correspondance à l'arrondi affiché près ; le signe est ignoré (« -31 % » = perte de 0,31)."""
    tolerance = 0.5 * 10 ** (-claim.decimals) + 1e-12
    claimed, fact_value = abs(claim.value), abs(fact_value)
    if claim.unit in ("%", "pts"):
        return abs(claimed / 100 - fact_value) <= tolerance / 100
    if claim.unit == "$":
        return abs(claimed - fact_value) <= tolerance
    return (
        abs(claimed - fact_value) <= tolerance or abs(claimed / 100 - fact_value) <= tolerance / 100
    )  # « 0,034 » ou « 3,4 » sans unité


def verify_numbers(text: str, facts: Iterable[Fact]) -> NumberCheck:
    numeric = [(fact.fact_id, float(fact.value)) for fact in facts if isinstance(fact.value, (int, float))]
    check = NumberCheck(ok=True)
    for claim in extract_numbers(text):
        matched = next((fact_id for fact_id, value in numeric if _matches(claim, value)), None)
        if matched:
            check.matched.append((claim.raw, matched))
        else:
            check.unmatched.append(claim.raw)
    check.ok = not check.unmatched
    return check


@dataclass
class DecisionCheck:
    ok: bool
    statements: list[dict]


def verify_decision(decision: Decision) -> DecisionCheck:
    """Fidélité phrase par phrase : les nombres d'un énoncé doivent venir des faits QU'IL cite."""
    facts = {fact.fact_id: fact for fact in decision.facts}
    rows, ok = [], True
    with span("verify.decision", decision_id=decision.decision_id, n_facts=len(facts)):
        for section in ("data_used", "why", "limits", "what_would_change"):
            for statement in getattr(decision.explanation, section):
                cited = [facts[fact_id] for fact_id in statement.fact_ids if fact_id in facts]
                check = verify_numbers(statement.text_fr, cited)
                rows.append(
                    {
                        "section": section,
                        "text": statement.text_fr,
                        "ok": check.ok,
                        "matched": check.matched,
                        "unmatched": check.unmatched,
                    }
                )
                ok &= check.ok
        log_event(
            "verify.decision",
            decision_id=decision.decision_id,
            ok=ok,
            unmatched=[text for row in rows for text in row["unmatched"]],
        )
    return DecisionCheck(ok, rows)


# --------------------------------------------------------------------------- Guardrails


@dataclass
class GuardrailCheck:
    action: str  # NONE | GUARDRAIL_INTERVENED
    text_out: str  # texte d'entrée anonymisé ou message de blocage
    topics: list[str]
    pii: list[str]
    grounding: float | None = None
    relevance: float | None = None
    blocked: bool = False


def _client():
    import boto3

    return boto3.client("bedrock-runtime")


def _summarize(response: dict, original: str) -> GuardrailCheck:
    assessment = (response.get("assessments") or [{}])[0]
    topics = [topic["name"] for topic in (assessment.get("topicPolicy") or {}).get("topics", [])]
    sensitive = assessment.get("sensitiveInformationPolicy") or {}
    pii = [entity["type"] for entity in sensitive.get("piiEntities", [])] + [
        regex["name"] for regex in sensitive.get("regexes", [])
    ]
    grounding = {item["type"]: item for item in (assessment.get("contextualGroundingPolicy") or {}).get("filters", [])}
    outputs = response.get("outputs") or []
    # La pertinence (lien avec la formulation de la question) n'est qu'un indicateur : seul l'ancrage bloque.
    blocked = (
        bool(topics)
        or grounding.get("GROUNDING", {}).get("action") == "BLOCKED"
        or any(item.get("action") == "BLOCKED" for item in (assessment.get("contentPolicy") or {}).get("filters", []))
    )
    return GuardrailCheck(
        response["action"],
        outputs[0]["text"] if outputs else original,
        topics,
        pii,
        grounding.get("GROUNDING", {}).get("score"),
        grounding.get("RELEVANCE", {}).get("score"),
        blocked,
    )


def verify_input(text: str, guardrail: tuple[str, str], client=None) -> GuardrailCheck:
    with span(
        "verify.input", **{"aws.bedrock.guardrail.id": guardrail[0], "aws.bedrock.guardrail.version": guardrail[1]}
    ):
        response = (client or _client()).apply_guardrail(
            guardrailIdentifier=guardrail[0],
            guardrailVersion=guardrail[1],
            source="INPUT",
            content=[{"text": {"text": text}}],
        )
        check = _summarize(response, text)
        log_event("verify.input", action=check.action, blocked=check.blocked, topics=check.topics, pii=check.pii)
    return check


def _format_value(value, unit: str) -> str:
    if isinstance(value, (int, float)) and unit not in ("CAD", "$", "mois", "poids") and abs(value) <= 1.5:
        return f"{value * 100:.1f} %".replace(".", ",")
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") if isinstance(value, float) else str(value)


def facts_as_text(facts: Iterable[Fact]) -> str:
    """Faits en phrases simples : l'ancrage contextuel de Guardrails juge mal un JSON brut
    (score 0,36 constaté sur des chiffres pourtant exacts)."""
    return "\n".join(
        f"{fact.label_fr} : {_format_value(fact.value, fact.unit)} ({fact.unit}) [{fact.fact_id}]." for fact in facts
    )


def verify_output(
    text: str, facts: Iterable[Fact], query: str, guardrail: tuple[str, str], client=None
) -> tuple[NumberCheck, GuardrailCheck]:
    facts = list(facts)
    source = facts_as_text(facts)
    with span(
        "verify.output", **{"aws.bedrock.guardrail.id": guardrail[0], "aws.bedrock.guardrail.version": guardrail[1]}
    ) as output_span:
        numbers = verify_numbers(text, facts)
        response = (client or _client()).apply_guardrail(
            guardrailIdentifier=guardrail[0],
            guardrailVersion=guardrail[1],
            source="OUTPUT",
            content=[
                {"text": {"text": source, "qualifiers": ["grounding_source"]}},
                {"text": {"text": query, "qualifiers": ["query"]}},
                {"text": {"text": text, "qualifiers": ["guard_content"]}},
            ],
        )
        guardrail_check = _summarize(response, text)
        output_span.set_attribute("alphaforge.numbers.unmatched", len(numbers.unmatched))
        if guardrail_check.grounding is not None:
            output_span.set_attribute("alphaforge.grounding.score", guardrail_check.grounding)
        log_event(
            "verify.output",
            numbers_ok=numbers.ok,
            unmatched=numbers.unmatched,
            grounding=guardrail_check.grounding,
            relevance=guardrail_check.relevance,
            blocked=guardrail_check.blocked,
            topics=guardrail_check.topics,
        )
    return numbers, guardrail_check
