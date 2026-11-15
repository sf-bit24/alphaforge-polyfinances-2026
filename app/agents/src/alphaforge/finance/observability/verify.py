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
_FACT_TOKEN = re.compile(r"\b[\w.-]+(?::[\w.\[\]-]+)+")          # fact_id du type judge-check:risk.cvar_m:max
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")


@dataclass
class NumberClaim:
    raw: str
    value: float
    unit: str          # "%", "$", "pts" ou ""
    decimals: int


@dataclass
class NumberCheck:
    ok: bool
    matched: list[tuple[str, str]] = field(default_factory=list)     # (texte, fact_id)
    unmatched: list[str] = field(default_factory=list)


def extract_numbers(text: str) -> list[NumberClaim]:
    clean = _ISO_DATE.sub(" ", _FACT_TOKEN.sub(" ", text))
    out = []
    for m in _NUM.finditer(clean):
        raw, unit = m.group(1), (m.group(2) or "").strip()
        unit = "pts" if unit.startswith("p") else unit
        digits = raw.replace("−", "-").replace(" ", "").replace(" ", "")
        dec = len(re.split(r"[.,]", digits)[1]) if re.search(r"[.,]", digits) else 0
        val = float(digits.replace(",", "."))
        if not unit and dec == 0 and 1900 <= abs(val) <= 2100:      # année
            continue
        out.append(NumberClaim(m.group(0).strip(), val, unit, dec))
    return out


def _matches(c: NumberClaim, f: float) -> bool:
    """Correspondance à l'arrondi affiché près ; le signe est ignoré (« -31 % » = perte de 0,31)."""
    tol = 0.5 * 10 ** (-c.decimals) + 1e-12
    v, f = abs(c.value), abs(f)
    if c.unit in ("%", "pts"):
        return abs(v / 100 - f) <= tol / 100
    if c.unit == "$":
        return abs(v - f) <= tol
    return abs(v - f) <= tol or abs(v / 100 - f) <= tol / 100     # « 0,034 » ou « 3,4 » sans unité


def verify_numbers(text: str, facts: Iterable[Fact]) -> NumberCheck:
    numeric = [(f.fact_id, float(f.value)) for f in facts if isinstance(f.value, (int, float))]
    res = NumberCheck(ok=True)
    for c in extract_numbers(text):
        hit = next((fid for fid, v in numeric if _matches(c, v)), None)
        if hit:
            res.matched.append((c.raw, hit))
        else:
            res.unmatched.append(c.raw)
    res.ok = not res.unmatched
    return res


@dataclass
class DecisionCheck:
    ok: bool
    statements: list[dict]


def verify_decision(decision: Decision) -> DecisionCheck:
    """Fidélité phrase par phrase : les nombres d'un énoncé doivent venir des faits QU'IL cite."""
    facts = {f.fact_id: f for f in decision.facts}
    rows, ok = [], True
    with span("verify.decision", decision_id=decision.decision_id, n_facts=len(facts)):
        for section in ("data_used", "why", "limits", "what_would_change"):
            for st in getattr(decision.explanation, section):
                chk = verify_numbers(st.text_fr, [facts[i] for i in st.fact_ids if i in facts])
                rows.append({"section": section, "text": st.text_fr, "ok": chk.ok,
                             "matched": chk.matched, "unmatched": chk.unmatched})
                ok &= chk.ok
        log_event("verify.decision", decision_id=decision.decision_id, ok=ok,
                  unmatched=[u for r in rows for u in r["unmatched"]])
    return DecisionCheck(ok, rows)


# --------------------------------------------------------------------------- Guardrails

@dataclass
class GuardrailCheck:
    action: str                       # NONE | GUARDRAIL_INTERVENED
    text_out: str                     # texte d'entrée anonymisé ou message de blocage
    topics: list[str]
    pii: list[str]
    grounding: float | None = None
    relevance: float | None = None
    blocked: bool = False


def _client():
    import boto3
    return boto3.client("bedrock-runtime")


def _summarize(resp: dict, original: str) -> GuardrailCheck:
    a = (resp.get("assessments") or [{}])[0]
    topics = [t["name"] for t in (a.get("topicPolicy") or {}).get("topics", [])]
    sip = a.get("sensitiveInformationPolicy") or {}
    pii = [p["type"] for p in sip.get("piiEntities", [])] + [r["name"] for r in sip.get("regexes", [])]
    g = {f["type"]: f for f in (a.get("contextualGroundingPolicy") or {}).get("filters", [])}
    outs = resp.get("outputs") or []
    # La pertinence (lien avec la formulation de la question) n'est qu'un indicateur : seul l'ancrage bloque.
    blocked = bool(topics) or g.get("GROUNDING", {}).get("action") == "BLOCKED" or \
        any(f.get("action") == "BLOCKED" for f in (a.get("contentPolicy") or {}).get("filters", []))
    return GuardrailCheck(resp["action"], outs[0]["text"] if outs else original, topics, pii,
                          g.get("GROUNDING", {}).get("score"), g.get("RELEVANCE", {}).get("score"), blocked)


def verify_input(text: str, guardrail: tuple[str, str], client=None) -> GuardrailCheck:
    with span("verify.input", **{"aws.bedrock.guardrail.id": guardrail[0],
                                 "aws.bedrock.guardrail.version": guardrail[1]}):
        resp = (client or _client()).apply_guardrail(
            guardrailIdentifier=guardrail[0], guardrailVersion=guardrail[1], source="INPUT",
            content=[{"text": {"text": text}}])
        chk = _summarize(resp, text)
        log_event("verify.input", action=chk.action, blocked=chk.blocked, topics=chk.topics, pii=chk.pii)
    return chk


def _fmt(v, unit: str) -> str:
    if isinstance(v, (int, float)) and unit not in ("CAD", "$", "mois", "poids") and abs(v) <= 1.5:
        return f"{v * 100:.1f} %".replace(".", ",")
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") if isinstance(v, float) else str(v)


def facts_as_text(facts: Iterable[Fact]) -> str:
    """Faits en phrases simples : l'ancrage contextuel de Guardrails juge mal un JSON brut
    (score 0,36 constaté sur des chiffres pourtant exacts)."""
    return "\n".join(f"{f.label_fr} : {_fmt(f.value, f.unit)} ({f.unit}) [{f.fact_id}]." for f in facts)


def verify_output(text: str, facts: Iterable[Fact], query: str, guardrail: tuple[str, str],
                  client=None) -> tuple[NumberCheck, GuardrailCheck]:
    facts = list(facts)
    source = facts_as_text(facts)
    with span("verify.output", **{"aws.bedrock.guardrail.id": guardrail[0],
                                  "aws.bedrock.guardrail.version": guardrail[1]}) as s:
        nums = verify_numbers(text, facts)
        resp = (client or _client()).apply_guardrail(
            guardrailIdentifier=guardrail[0], guardrailVersion=guardrail[1], source="OUTPUT",
            content=[{"text": {"text": source, "qualifiers": ["grounding_source"]}},
                     {"text": {"text": query, "qualifiers": ["query"]}},
                     {"text": {"text": text, "qualifiers": ["guard_content"]}}])
        g = _summarize(resp, text)
        s.set_attribute("alphaforge.numbers.unmatched", len(nums.unmatched))
        if g.grounding is not None:
            s.set_attribute("alphaforge.grounding.score", g.grounding)
        log_event("verify.output", numbers_ok=nums.ok, unmatched=nums.unmatched, grounding=g.grounding,
                  relevance=g.relevance, blocked=g.blocked, topics=g.topics)
    return nums, g
