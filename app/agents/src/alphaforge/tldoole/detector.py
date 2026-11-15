"""A7, ``detectGaps-Agent`` : quels concepts l'investisseur ne comprend-il pas encore ?

A7 lit les messages libres de l'investisseur et les candidats des règles déterministes (``signals``), puis
rend au plus trois lacunes, chacune prouvée par une citation exacte d'un message (``m<n>``) ou par la
preuve d'une règle (``r_…``). Le code vérifie chaque citation dans le texte d'origine et refuse une lacune
sans preuve : A7 ne déduit rien de l'âge, du revenu ni du seul niveau de connaissances.

Sans modèle disponible, ou si A7 échoue, les candidats des règles d'au moins ``RULE_THRESHOLD`` tiennent lieu
de détection (``detector: "rules"``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from strands import tool

from ..agentkit import AgentSpec, ModelFactory, run_agent, tool_result
from ..errors import AppError
from ..trace import Trace
from .concepts import Catalog, normalize
from .signals import RULE_THRESHOLD, Candidate, InvestorMessage

MAX_GAPS = 3
MAX_REASON = 220


@dataclass
class Gap:
    concept_id: str
    confidence: float
    evidence: list[dict[str, Any]]
    reason: str
    detector: str  # "A7" ou "rules"
    rule: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "confidence": round(self.confidence, 2),
            "evidence": self.evidence,
            "reason": self.reason,
            "detector": self.detector,
            "rule": self.rule,
        }


@dataclass
class DetectionInput:
    catalog: Catalog
    locale: str
    level: str | None
    messages: list[InvestorMessage]
    candidates: dict[str, Candidate]
    covered: dict[str, str] = field(default_factory=dict)  # concept_id -> état (ready, understood, unclear…)


def system_prompt(locale: str) -> str:
    language = "French (Canada), addressing the investor as 'vous'" if locale != "en" else "English"
    return (
        "You are A7, the comprehension-gap detector of AlphaForge AI, an educational investment-decision "
        "simulator (no real transactions, no personalised advice). You decide which concepts of a fixed catalog "
        "the investor most likely does not understand yet, so that a short explainer video can be made for them.\n"
        "Rules:\n"
        "- Use only concept ids from <catalog>.\n"
        "- Every gap needs evidence you cite by ref: an investor message (m<n>, with a quote copied verbatim from "
        "it) or the evidence of a rule candidate (r_...). No evidence, no gap.\n"
        "- A question or a stated confusion about a concept is strong evidence; a bare mention is weak. Rule "
        "candidates are hints computed from answers: keep them only if they plausibly reveal a misunderstanding.\n"
        "- Never infer a gap from age, income, gender or the knowledge level alone.\n"
        "- Concepts in <covered> already have a video; report them again only if a newer message shows the "
        "confusion persists.\n"
        f"- At most {MAX_GAPS} gaps, ranked by how much the misunderstanding could hurt the investor's decisions.\n"
        f"- Write each reason in {language}: one short sentence describing the observable evidence, without "
        "judging the person.\n"
        "Call report_gaps exactly once. An empty list is a valid answer."
    )


def build_prompt(data: DetectionInput) -> str:
    context = {
        "locale": data.locale,
        "knowledge_level": data.level,
        "catalog": data.catalog.brief(data.locale),
        "investor_messages": [
            {"ref": m.ref, "at": m.at, "provenance": m.provenance, "text": m.text.replace("<", "‹").replace(">", "›")}
            for m in data.messages[-12:]
        ],
        "rule_candidates": [c.to_dict() for c in data.candidates.values()],
        "covered": data.covered,
    }
    return "<context>\n" + json.dumps(context, ensure_ascii=False, indent=1, default=str) + "\n</context>"


class GapReport:
    """Validation de ``report_gaps`` : identifiants, preuves citées, citations exactes."""

    def __init__(self, data: DetectionInput):
        self.data = data
        self.messages = {m.ref: m for m in data.messages}
        self.rule_evidence = {e.ref: (c, e) for c in data.candidates.values() for e in c.evidence}
        self.gaps: list[Gap] | None = None

    def submit(self, gaps: Any) -> dict[str, Any]:
        if not isinstance(gaps, list):
            return {"status": "error", "reason": "gaps must be a list"}
        if len(gaps) > MAX_GAPS:
            return {"status": "error", "reason": f"at most {MAX_GAPS} gaps"}
        built, errors, seen = [], [], set()
        for index, raw in enumerate(gaps, start=1):
            gap, error = self._build(raw)
            if error:
                errors.append({"gap": index, "reason": error})
            elif gap.concept_id in seen:
                errors.append({"gap": index, "reason": "duplicate concept_id"})
            else:
                seen.add(gap.concept_id)
                built.append(gap)
        if errors:
            return {"status": "error", "errors": errors}
        self.gaps = built
        return {"status": "ok", "gaps": len(built)}

    def _build(self, raw: Any) -> tuple[Gap | None, str | None]:
        if not isinstance(raw, dict):
            return None, "each gap is an object"
        concept_id = raw.get("concept_id")
        if self.data.catalog.get(concept_id) is None:
            return None, f"unknown concept_id {concept_id!r}"
        try:
            confidence = float(raw.get("confidence"))
        except (TypeError, ValueError):
            return None, "confidence must be a number between 0 and 1"
        if not 0 <= confidence <= 1:
            return None, "confidence must be between 0 and 1"
        evidence_in = raw.get("evidence")
        if not isinstance(evidence_in, list) or not evidence_in:
            return None, "at least one evidence item is required"
        evidence = []
        for item in evidence_in[:3]:
            ref = item.get("ref") if isinstance(item, dict) else None
            if ref in self.messages:
                message = self.messages[ref]
                quote = str(item.get("quote") or "").strip()
                if not quote or normalize(quote) not in normalize(message.text):
                    return None, f"quote for {ref} must be copied verbatim from that message"
                evidence.append(
                    {
                        "kind": "message",
                        "ref": ref,
                        "quote": quote[:180],
                        "provenance": message.provenance,
                        "at": message.at,
                    }
                )
            elif ref in self.rule_evidence:
                candidate, rule_evidence = self.rule_evidence[ref]
                if candidate.concept_id != concept_id:
                    return None, f"{ref} is evidence for {candidate.concept_id}, not {concept_id}"
                evidence.append({**rule_evidence.to_dict(), "rule": candidate.rule})
            else:
                return None, f"unknown evidence ref {ref!r}; cite m<n> or a rule evidence ref"
        reason = str(raw.get("reason") or "").strip()
        if not reason:
            return None, "reason is required"
        rule = next((e.get("rule") for e in evidence if e.get("rule")), None)
        return Gap(concept_id, confidence, evidence, reason[:MAX_REASON], "A7", rule), None


def rule_gaps(data: DetectionInput) -> list[Gap]:
    """Détection sans modèle : candidats des règles au-dessus du seuil, les plus forts d'abord."""
    gaps = []
    for candidate in sorted(data.candidates.values(), key=lambda c: c.score, reverse=True):
        if candidate.score < RULE_THRESHOLD or candidate.concept_id in data.covered:
            continue
        concept = data.catalog.get(candidate.concept_id)
        label = concept.text("label", data.locale) if concept else candidate.concept_id
        reason = (
            f"Signal « {candidate.rule} » sur le concept {label}."
            if data.locale != "en"
            else f"Signal '{candidate.rule}' on the concept {label}."
        )
        gaps.append(
            Gap(
                candidate.concept_id,
                candidate.score,
                [e.to_dict() for e in candidate.evidence],
                reason,
                "rules",
                candidate.rule,
            )
        )
    return gaps[:MAX_GAPS]


def run_a7(data: DetectionInput, *, model_factory: ModelFactory, model_id: str, trace: Trace) -> list[Gap]:
    report = GapReport(data)

    @tool(
        name="report_gaps",
        description=(
            "Report the comprehension gaps (0 to 3). Each gap: concept_id from the catalog, confidence 0..1, "
            "evidence (1 to 3 items {ref, quote?}: ref m<n> with a verbatim quote, or a rule evidence ref r_...), "
            "reason (one short sentence in the investor's language)."
        ),
        inputSchema={
            "json": {
                "type": "object",
                "properties": {
                    "gaps": {
                        "type": "array",
                        "maxItems": MAX_GAPS,
                        "items": {
                            "type": "object",
                            "properties": {
                                "concept_id": {"type": "string"},
                                "confidence": {"type": "number"},
                                "evidence": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"ref": {"type": "string"}, "quote": {"type": "string"}},
                                        "required": ["ref"],
                                    },
                                },
                                "reason": {"type": "string"},
                            },
                            "required": ["concept_id", "confidence", "evidence", "reason"],
                        },
                    }
                },
                "required": ["gaps"],
            }
        },
        context=True,
    )
    def report_gaps(gaps: list[dict[str, Any]], tool_context) -> str:
        outcome = report.submit(gaps)
        if outcome.get("status") == "ok":
            tool_context.agent.cancel(after_current_tools=True)
        return tool_result(outcome)

    spec = AgentSpec(
        actor="A7",
        name="detectGaps-Agent",
        effort="low",
        system_prompt=system_prompt(data.locale),
        tools=[report_gaps],
        max_turns=4,
        max_tokens=4000,
        tool_summaries={
            "report_gaps": lambda i: {"gaps": [g.get("concept_id") for g in i.get("gaps") or [] if isinstance(g, dict)]}
        },
    )
    run = run_agent(spec, build_prompt(data), model_factory=model_factory, model_id=model_id, trace=trace)
    if report.gaps is None:
        run.follow_up("You did not call report_gaps successfully. Call report_gaps now.", trace)
    if report.gaps is None:
        raise AppError("model_error", trace.t("A7 n'a pas rendu de lacunes valides.", "A7 returned no valid gaps."))
    return report.gaps


def detect(data: DetectionInput, *, model_factory: ModelFactory | None, model_id: str, trace: Trace) -> list[Gap]:
    """A7 si un modèle est disponible et qu'il y a matière à juger; sinon, ou en cas d'échec, les règles."""
    if not data.messages and not data.candidates:
        trace.add("deterministic", "A7", trace.t("Aucun signal à juger", "No signal to judge"), None)
        return []
    if model_factory is not None:
        try:
            gaps = run_a7(data, model_factory=model_factory, model_id=model_id, trace=trace)
            # Une règle forte qu'A7 a écartée reste visible dans la trace, pas dans les lacunes.
            return gaps
        except AppError as exc:
            if exc.code == "guardrail_blocked":
                raise
            trace.add("deterministic", "A7", trace.t("Repli sur les règles", "Falling back to rules"), exc.message)
    gaps = rule_gaps(data)
    trace.add(
        "deterministic",
        "A7",
        trace.t("Lacunes tirées des règles", "Gaps from rules"),
        None,
        outputs={"gaps": [g.concept_id for g in gaps]},
    )
    return gaps
