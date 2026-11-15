"""A0, routeur et rédacteur des questions de recherche (mode question seulement).

- ``route`` : lit la question, choisit 1 à 4 sujets et une sous-question pour chacun, répartit le plafond de
  chercheurs de l'exécution entre eux et écrit ``staging/<run_id>/router/plan.json``. Si le modèle ne répond pas,
  un routage par mots-clés prend le relais (aucune question n'est perdue).
- ``compose`` : lit les synthèses des experts et leurs éléments, rédige la synthèse finale, chaque nombre fondé
  sur un élément cité, et la met en attente pour A6 (``staging/<run_id>/router/<id>.json``, type ``brief``).

A0 ne lit jamais le Web, ne lance aucun chercheur et ne reçoit aucune donnée de client : une synthèse entre dans
la base générale.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from strands import tool

from .. import clock
from ..agentkit import AgentSpec, ModelFactory, run_agent, tool_result
from ..collect import staging
from ..errors import AppError
from ..store import Store
from ..trace import Trace
from . import documents, items
from .packs import DEPTH_CAPS, MAX_RESEARCHERS_PER_RUN, SUBJECTS

MAX_SUBJECTS = 4

ROUTE_PROMPT = """You are A0, the research router of AlphaForge AI, a simulation-only decision-support prototype for \
Canadian retail investors. A question arrives; you choose which subject experts should research it, and give each \
one a precise sub-question. Choose 1 to {max_subjects} subjects, only those that bring real evidence.

Subjects:
{subjects}

Call choose_subjects once, then stop."""

COMPOSE_PROMPT = """You are A0, the research writer of AlphaForge AI, a simulation-only decision-support prototype \
for Canadian retail investors. Write the final research brief in French from the subject briefs and items below.

Rules:
- 250 to 500 words, neutral, factual. Structure: a short answer, the evidence by subject, then « Limites » (lags, \
vintages, licences, quality of market odds) and « Lacunes » (what was not found).
- Every number must come from a cited item. Cite item ids in `citations`. Never advise, never forecast.
- Contextual signals (attention, market odds, factors) are context, never a buy or sell signal.

Call write_brief once, then stop."""

_KEYWORDS = {
    "E1": (
        "inflation",
        "ipc",
        "cpi",
        "emploi",
        "chomage",
        "pib",
        "gdp",
        "politique monetaire",
        "banque du canada",
        "fed",
    ),
    "E2": ("taux", "rate", "obligation", "bond", "yield", "change", "fx", "dollar", "or ", "gold", "petrole", "oil"),
    "E3": ("action", "societe", "company", "resultats", "earnings", "dividende", "depot", "filing", "cours", "price"),
    "E4": ("esg", "emission", "climat", "durab", "fnb", "etf", "exclusion", "pipeline", "incident"),
    "E5": ("logement", "housing", "loyer", "rent", "immobilier", "hypothec", "mortgage", "mises en chantier"),
    "E6": ("probabilite", "odds", "marche predictif", "kalshi", "polymarket", "recession", "positionnement", "cot"),
    "E7": ("actualite", "news", "medias", "attention", "tendance", "trend", "sentiment", "wikipedia"),
}


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()


def keyword_route(question: str, issuers: list[str], themes: list[str]) -> list[dict[str, str]]:
    folded = _fold(" ".join([question, *themes]))
    chosen = [code for code, words in _KEYWORDS.items() if any(w in folded for w in words)]
    if issuers and "E3" not in chosen:
        chosen.insert(0, "E3")
    if not chosen:
        chosen = ["E1", "E7"]
    return [{"subject": code, "sub_question": question} for code in chosen[:MAX_SUBJECTS]]


def share_caps(selections: list[dict[str, str]], depth: str) -> list[dict[str, Any]]:
    n = max(1, len(selections))
    share = max(1, min(DEPTH_CAPS[depth], MAX_RESEARCHERS_PER_RUN // n))
    return [{**s, "max_researchers": share} for s in selections]


@dataclass
class RouteState:
    selections: list[dict[str, str]] = field(default_factory=list)

    def tools(self) -> list[Any]:
        state = self

        @tool(
            name="choose_subjects",
            description="Choose the subject experts for the question, each with a sub-question.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "selections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "subject": {"type": "string", "enum": list(SUBJECTS)},
                                    "sub_question": {"type": "string"},
                                },
                                "required": ["subject", "sub_question"],
                            },
                        }
                    },
                    "required": ["selections"],
                }
            },
            context=True,
        )
        def choose_subjects(tool_context, selections: list[dict[str, Any]]) -> str:
            seen = set()
            for selection in selections or []:
                code = selection.get("subject") if isinstance(selection, dict) else None
                if code in SUBJECTS and code not in seen and len(state.selections) < MAX_SUBJECTS:
                    seen.add(code)
                    sub = " ".join(str(selection.get("sub_question") or "").split())[:400]
                    state.selections.append({"subject": code, "sub_question": sub})
            tool_context.agent.cancel(after_current_tools=True)
            return tool_result({"status": "ok", "subjects": [s["subject"] for s in state.selections]})

        return [choose_subjects]


def route(
    *,
    job: dict[str, Any],
    store: Store,
    trace: Trace,
    model_factory: ModelFactory,
    model_id: str,
) -> dict[str, Any]:
    subjects = "\n".join(f"- {s.code} {s.name}: {s.scope}" for s in SUBJECTS.values())
    state = RouteState()
    warnings = []
    spec = AgentSpec(
        actor="A0",
        name="Research router",
        effort="medium",
        system_prompt=ROUTE_PROMPT.format(max_subjects=MAX_SUBJECTS, subjects=subjects),
        tools=state.tools(),
        max_turns=3,
        max_tokens=4000,
    )
    question_block = (
        f"Question: {job['question']}\nIssuers: {', '.join(job['issuers']) or 'none'}\n"
        f"Themes: {', '.join(job['themes']) or 'none'}\nDepth: {job['depth']}"
    )
    try:
        run_agent(spec, question_block, model_factory=model_factory, model_id=model_id, trace=trace)
    except AppError as exc:
        warnings.append(f"routage par le modèle indisponible ({exc.code}) : routage par mots-clés")
    selections = state.selections or keyword_route(job["question"], job["issuers"], job["themes"])
    if not state.selections and not warnings:
        warnings.append("le modèle n'a choisi aucun sujet : routage par mots-clés")
    plan = {
        "run_id": job["run_id"],
        "question": job["question"],
        "issuers": job["issuers"],
        "themes": job["themes"],
        "as_of": job.get("as_of"),
        "depth": job["depth"],
        "since": job["since"],
        "subjects": share_caps(selections, job["depth"]),
        "routed_at": clock.iso(),
    }
    store.put_json(f"staging/{job['run_id']}/router/plan.json", plan)
    trace.add(
        "deterministic", "A0", "Plan de recherche", None, outputs={"subjects": [s["subject"] for s in plan["subjects"]]}
    )
    return {"plan": plan, "warnings": warnings}


@dataclass
class ComposeState:
    items_by_id: dict[str, dict[str, Any]]
    brief: dict[str, Any] | None = None
    error: str | None = None

    def tools(self) -> list[Any]:
        state = self

        @tool(
            name="write_brief",
            description="Write the final French research brief, citing item ids.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "text": {"type": "string"},
                        "citations": {"type": "array", "items": {"type": "string"}},
                        "gaps": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "text", "citations"],
                }
            },
        )
        def write_brief(title: str, text: str, citations: list[str], gaps: list[str] | None = None) -> str:
            cited = [c for c in dict.fromkeys(citations or []) if c in state.items_by_id]
            if not cited:
                return tool_result({"status": "error", "reason": "citer au moins un élément existant"})
            allowed = [n for c in cited for n in items.allowed_numbers(state.items_by_id[c])]
            missing = documents.grounded(f"{title} {text}", allowed)
            if missing:
                return tool_result(
                    {"status": "error", "reason": "nombres absents des éléments cités : " + ", ".join(missing[:5])}
                )
            state.brief = {
                "title": " ".join(str(title).split())[:160],
                "text": str(text).strip()[:8000],
                "citations": cited,
                "gaps": [" ".join(str(g).split())[:300] for g in (gaps or [])][:10],
            }
            return tool_result({"status": "ok", "citations": len(cited)})

        return [write_brief]


def compose(
    *,
    run_id: str,
    store: Store,
    trace: Trace,
    model_factory: ModelFactory,
    model_id: str,
) -> dict[str, Any]:
    plan = store.get_json(f"staging/{run_id}/router/plan.json")
    if not plan:
        raise AppError("not_found", "plan de recherche absent : lancer route d'abord")
    subject_briefs, items_by_id, warnings = [], {}, []
    for entry in plan.get("subjects") or []:
        code = entry.get("subject")
        prefix = f"staging/{run_id}/experts/{code}/"
        brief = store.get_json(prefix + "brief.json")
        if brief:
            subject_briefs.append(brief)
        else:
            warnings.append(f"{code} : aucune synthèse de sujet")
        for info in store.list(prefix, limit=500):
            name = info.key.rsplit("/", 1)[-1]
            if name.startswith("_") or name in ("brief.json",) or not name.endswith(".json"):
                continue
            item = store.get_json(info.key)
            if isinstance(item, dict) and item.get("id"):
                items_by_id[item["id"]] = item
    if not items_by_id:
        raise AppError("not_found", "aucun élément mis en attente par les experts : rien à synthétiser")
    listing = [
        {
            "id": i["id"],
            "kind": i.get("kind"),
            "title": i.get("title"),
            "source": i.get("source"),
            "observed_at": i.get("observed_at"),
            "published_at": i.get("published_at"),
            "summary": i.get("summary"),
            "values": {k: str(v)[:80] for k, v in list(((i.get("data") or {}).get("values") or {}).items())[:5]},
            "subject": (i.get("data") or {}).get("subject"),
        }
        for i in items_by_id.values()
    ]
    state = ComposeState(items_by_id=items_by_id)
    spec = AgentSpec(
        actor="A0",
        name="Research writer",
        effort="medium",
        system_prompt=COMPOSE_PROMPT,
        tools=state.tools(),
        max_turns=4,
        max_tokens=12000,
    )
    import json

    prompt = (
        f"Question: {plan['question']}\n\n<subject_briefs>\n{json.dumps(subject_briefs, ensure_ascii=False)}\n"
        f"</subject_briefs>\n\n<items>\n{json.dumps(listing, ensure_ascii=False)}\n</items>"
    )
    run_agent(spec, prompt, model_factory=model_factory, model_id=model_id, trace=trace)
    if state.brief is None:
        raise AppError("model_error", "A0 n'a rédigé aucune synthèse valide")
    now = clock.iso()
    brief_id = "brief-" + staging.short_hash(f"{run_id}|{plan['question']}")
    item = {
        "id": brief_id,
        "kind": "brief",
        "title": state.brief["title"],
        "url": None,
        "source": "AlphaForge AI (A0, synthèse de recherche)",
        "published_at": now,
        "observed_at": None,
        "retrieved_at": now,
        "language": "fr",
        "tickers": plan.get("issuers") or [],
        "summary": state.brief["text"][:600],
        "data": {
            "run_id": run_id,
            "question": plan["question"],
            "text": state.brief["text"],
            "citations": state.brief["citations"],
            "subjects": [s.get("subject") for s in plan.get("subjects") or []],
            "gaps": state.brief["gaps"] + [g for b in subject_briefs for g in b.get("gaps") or []][:10],
            "as_of": plan.get("as_of"),
            "collected_by": "A0",
        },
    }
    key = f"staging/{run_id}/router/{brief_id}.json"
    store.put_json(key, item)
    return {"brief_key": key, "citations": len(state.brief["citations"]), "warnings": warnings}
