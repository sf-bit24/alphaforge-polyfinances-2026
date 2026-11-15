"""Expert de sujet (E1 à E7) : planifie, lance n chercheurs, relit leurs constats et met en attente les éléments.

Boucle (outils vérifiés par le code) :
1. ``search_general_knowledge`` : ce que la base générale sait déjà;
2. ``spawn_researchers`` : n missions sans recoupement; le code applique les plafonds (n par tour selon la
   profondeur, deux tours au plus, paquets du sujet seulement, budget de chaque chercheur);
3. relecture des constats : garder les deux valeurs quand deux sources divergent, noter les lacunes;
4. ``stage_items`` : constats retenus → éléments ``staging/<run_id>/experts/<sujet>/<id>.json``;
5. en mode question, ``stage_subject_brief`` : synthèse du sujet, chaque nombre fondé sur un constat cité;
6. ``finish``.

L'expert ne lit jamais le Web lui-même.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from strands import tool

from .. import clock
from ..agentkit import AgentSpec, ModelFactory, run_agent, tool_result
from ..errors import AppError
from ..store import Store
from ..trace import Trace
from . import documents, items
from .launcher import Launcher, session_id
from .packs import (
    DEPTH_CAPS,
    MAX_ROUNDS,
    PACKS,
    RESEARCHER_BUDGET_S,
    RESEARCHER_MAX_TOOL_CALLS,
    Subject,
)

SYSTEM_PROMPT = """You are {code}, the {name} research expert of AlphaForge AI, a simulation-only \
decision-support prototype for Canadian retail investors. You lead research for your subject: you never read the \
web yourself; you spawn research sub-agents, each in its own isolated session, and you judge what they bring back.

Your scope: {scope}
Your source packs (a researcher only gets the packs you give it):
{packs}

{mode_block}

How to work:
1. Call search_general_knowledge once or twice to see what the shared base already holds, so you do not ask for it \
again.
2. Call spawn_researchers with {cap_line} non-overlapping missions. Each mission has a precise objective, the \
evidence wanted, the packs, issuers and themes. Split by source family or by question, never duplicate.
3. Read the findings. If two sources disagree, keep both. If important evidence is missing and the run allows a \
second round ({rounds_left} round(s) in total), spawn a few more missions for the gaps only.
4. Call stage_items with the findings worth keeping in the shared base, each with a neutral French summary of one or \
two sentences. Every number you write must come from the finding. Skip weak, duplicate or off-topic findings. \
Findings from quarantined hosts may be staged: the supervisor holds them for human review.
{brief_step}
6. Call finish with a short French note and the remaining gaps.

Never give advice ("buy", "sell", "avoid"), never forecast, never invent a number or a source.
"""

SWEEP_BLOCK = """Mode: scheduled sweep. Window starts {since}. Tickers of the run: {issuers}.
Standing plan of your subject (adapt it to what the base already holds):
{plan}"""

QUESTION_BLOCK = """Mode: research question.
Question asked to AlphaForge: {question}
Your part of it: {sub_question}
Issuers: {issuers}. Themes: {themes}. Window starts {since}. {as_of_line}"""

BRIEF_STEP = """5. Call stage_subject_brief once: a French synthesis of your part of the question (150 to 300 words), \
citing the finding ids it rests on, with its limits (lags, vintages, licences) and gaps. Every number must appear \
in a cited finding."""


@dataclass
class ExpertJob:
    run_id: str
    subject: Subject
    mode: str
    question: str | None
    sub_question: str | None
    issuers: list[str]
    themes: list[str]
    since: str
    as_of: str | None
    depth: str
    max_researchers: int

    @property
    def prefix(self) -> str:
        return f"staging/{self.run_id}/experts/{self.subject.code}/"


@dataclass
class ExpertRun:
    job: ExpertJob
    store: Store
    launcher: Launcher
    knowledge: Any
    deadline: float
    rounds: int = 0
    spawned: int = 0
    findings: dict[str, dict[str, Any]] = field(default_factory=dict)
    researchers: list[dict[str, Any]] = field(default_factory=list)
    staged: dict[str, str] = field(default_factory=dict)  # finding_id -> clé de l'élément
    staged_items: dict[str, dict[str, Any]] = field(default_factory=dict)
    brief_key: str | None = None
    finished: bool = False
    note: str = ""
    gaps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def remaining(self) -> int:
        return max(0, self.job.max_researchers - self.spawned)

    def spawn(self, missions: list[dict[str, Any]]) -> dict[str, Any]:
        if self.rounds >= MAX_ROUNDS:
            return {"status": "error", "reason": f"au plus {MAX_ROUNDS} tours de lancement"}
        if not isinstance(missions, list) or not missions:
            return {"status": "error", "reason": "missions doit être une liste non vide"}
        cap = min(DEPTH_CAPS[self.job.depth], self.remaining())
        if cap <= 0:
            return {"status": "error", "reason": "plafond de chercheurs atteint pour ce sujet"}
        accepted, refused = [], []
        for mission in missions[:cap]:
            packs = [p for p in (mission.get("packs") or []) if p in self.job.subject.packs]
            objective = " ".join(str(mission.get("objective") or "").split())[:500]
            if not packs or not objective:
                refused.append({"objective": objective, "reason": "objectif ou paquets du sujet manquants"})
                continue
            self.spawned += 1
            accepted.append(
                {
                    "run_id": self.job.run_id,
                    "subject": self.job.subject.code,
                    "researcher": f"r{self.spawned}",
                    "objective": objective,
                    "evidence_wanted": [str(e)[:200] for e in (mission.get("evidence_wanted") or [])][:8],
                    "packs": packs,
                    "issuers": [str(i).upper()[:20] for i in (mission.get("issuers") or self.job.issuers)][:12],
                    "themes": [str(t)[:40] for t in (mission.get("themes") or self.job.themes)][:8],
                    "since": self.job.since,
                    "as_of": self.job.as_of,
                    "budget_s": RESEARCHER_BUDGET_S,
                    "max_tool_calls": RESEARCHER_MAX_TOOL_CALLS,
                }
            )
        if len(missions) > cap:
            refused += [
                {"objective": str(m.get("objective"))[:120], "reason": "au-delà du plafond"} for m in missions[cap:]
            ]
        if not accepted:
            return {"status": "error", "reason": "aucune mission valide", "refused": refused}
        self.rounds += 1
        timeout = max(60.0, min(RESEARCHER_BUDGET_S + 150, self.deadline - time.monotonic()))
        results = self.launcher.run(accepted, timeout)
        report = []
        new_findings = []
        for result in results:
            marker = result.get("marker") or {}
            brief = result["brief"]
            entry = {
                "researcher": brief["researcher"],
                "objective": brief["objective"],
                "status": marker.get("status") or ("error" if result.get("error") else "unknown"),
                "error": result.get("error") or marker.get("error"),
                "summary": marker.get("summary"),
                "gaps": marker.get("gaps") or [],
                "blocked_hosts": marker.get("blocked_hosts") or {},
                "quarantine": marker.get("quarantine") or [],
                "findings": len(result.get("findings") or []),
            }
            report.append(entry)
            self.researchers.append(
                {**entry, "session_id": session_id(brief["run_id"], brief["subject"], brief["researcher"])}
            )
            for finding in result.get("findings") or []:
                if isinstance(finding, dict) and finding.get("finding_id"):
                    self.findings[finding["finding_id"]] = finding
                    new_findings.append(finding)
        compact = [
            {
                "finding_id": f["finding_id"],
                "kind": f.get("kind"),
                "label": f.get("label"),
                "claim": f.get("claim"),
                "values": {k: str(v)[:120] for k, v in list((f.get("values") or {}).items())[:6]},
                "observation_date": f.get("observation_date"),
                "publication_date": f.get("publication_date"),
                "publication_basis": f.get("publication_basis"),
                "host": f.get("host"),
                "host_status": f.get("host_status"),
            }
            for f in new_findings
        ]
        return {
            "status": "ok",
            "round": self.rounds,
            "researchers": report,
            "findings": compact,
            "refused": refused,
            "researchers_left": self.remaining(),
        }

    def stage(self, selections: list[dict[str, Any]]) -> dict[str, Any]:
        written, unknown = [], []
        for selection in selections or []:
            if not isinstance(selection, dict):
                continue
            finding = self.findings.get(str(selection.get("finding_id")))
            if finding is None:
                unknown.append(selection.get("finding_id"))
                continue
            summary = selection.get("summary") or finding.get("claim")
            draft = items.build_item(finding)
            missing = documents.grounded(str(summary), items.allowed_numbers(draft), items.allowed_dates(draft))
            if missing:
                unknown.append(f"{finding['finding_id']} : nombres non fondés {missing[:3]}")
                continue
            item = items.build_item(finding, summary=summary, tags=selection.get("tags") or [])
            key = self.job.prefix + f"{item['id']}.json"
            self.store.put_json(key, item)
            self.staged[finding["finding_id"]] = key
            self.staged_items[finding["finding_id"]] = item
            written.append({"finding_id": finding["finding_id"], "item_id": item["id"]})
        return {"status": "ok", "staged": written, "refused": unknown}

    def stage_brief(self, text: str, citations: list[str]) -> dict[str, Any]:
        if self.job.mode != "question":
            return {"status": "error", "reason": "la synthèse ne sert qu'en mode question"}
        cited = [c for c in citations or [] if c in self.findings]
        if not cited:
            return {"status": "error", "reason": "citer au moins un constat existant"}
        for finding_id in cited:
            if finding_id not in self.staged:
                self.stage([{"finding_id": finding_id}])
        cited = [c for c in cited if c in self.staged]
        values = [n for c in cited for n in items.allowed_numbers(self.staged_items[c])]
        dates = [d for c in cited for d in items.allowed_dates(self.staged_items[c])]
        missing = documents.grounded(text, values, dates)
        if missing:
            return {"status": "error", "reason": "nombres absents des constats cités : " + ", ".join(missing[:5])}
        document = {
            "subject": self.job.subject.code,
            "question": self.job.question,
            "sub_question": self.job.sub_question,
            "text": " ".join(str(text).split())[:4000],
            "citations": [{"finding_id": c, "item_id": self.staged_items[c]["id"]} for c in cited],
            "gaps": self.gaps,
            "as_of": self.job.as_of,
            "written_at": clock.iso(),
        }
        self.brief_key = self.job.prefix + "brief.json"
        self.store.put_json(self.brief_key, document)
        return {"status": "ok", "brief_key": self.brief_key, "citations": len(cited)}

    def tools(self) -> list[Any]:
        run = self

        @tool(
            name="search_general_knowledge",
            description="Search the shared general knowledge base (what AlphaForge already knows).",
            inputSchema={
                "json": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
            },
        )
        def search_general_knowledge(query: str) -> str:
            results = run.knowledge.search(str(query)[:500]) if run.knowledge is not None else []
            return tool_result(
                {"status": "ok", "results": results, "enabled": bool(results) or run.knowledge is not None}
            )

        mission_schema = {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "evidence_wanted": {"type": "array", "items": {"type": "string"}},
                "packs": {"type": "array", "items": {"type": "string", "enum": list(run.job.subject.packs)}},
                "issuers": {"type": "array", "items": {"type": "string"}},
                "themes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["objective", "packs"],
        }

        @tool(
            name="spawn_researchers",
            description="Spawn research sub-agents, one isolated session each; waits for them and returns findings.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {"missions": {"type": "array", "items": mission_schema}},
                    "required": ["missions"],
                }
            },
        )
        def spawn_researchers(missions: list[dict[str, Any]]) -> str:
            return tool_result(run.spawn(missions))

        @tool(
            name="stage_items",
            description="Stage selected findings for the supervisor, each with a neutral French summary.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "selections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "finding_id": {"type": "string"},
                                    "summary": {"type": "string"},
                                    "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                                },
                                "required": ["finding_id"],
                            },
                        }
                    },
                    "required": ["selections"],
                }
            },
        )
        def stage_items(selections: list[dict[str, Any]]) -> str:
            return tool_result(run.stage(selections))

        @tool(
            name="stage_subject_brief",
            description="Question mode only: stage the French synthesis of your part, citing finding ids.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "citations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["text", "citations"],
                }
            },
        )
        def stage_subject_brief(text: str, citations: list[str]) -> str:
            return tool_result(run.stage_brief(text, citations))

        @tool(
            name="finish",
            description="End the expert run with a short French note and the remaining gaps.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {"note": {"type": "string"}, "gaps": {"type": "array", "items": {"type": "string"}}},
                }
            },
            context=True,
        )
        def finish(tool_context, note: str = "", gaps: list[str] | None = None) -> str:
            run.finished = True
            run.note = " ".join(str(note).split())[:600]
            run.gaps = [" ".join(str(g).split())[:300] for g in (gaps or [])][:10]
            if run.brief_key:
                document = run.store.get_json(run.brief_key) or {}
                document["gaps"] = run.gaps
                run.store.put_json(run.brief_key, document)
            tool_context.agent.cancel(after_current_tools=True)
            return tool_result({"status": "ok"})

        tools = [search_general_knowledge, spawn_researchers, stage_items]
        if run.job.mode == "question":
            tools.append(stage_subject_brief)
        return [*tools, finish]


def _pack_lines(subject: Subject) -> str:
    lines = []
    for name in subject.packs:
        pack = PACKS[name]
        lines.append(
            f"- {name}: hosts {', '.join(pack.hosts)}" + (f"; search {', '.join(pack.sources)}" if pack.sources else "")
        )
    return "\n".join(lines)


def run_expert(
    *,
    job: ExpertJob,
    store: Store,
    trace: Trace,
    model_factory: ModelFactory,
    model_id: str,
    launcher: Launcher,
    knowledge: Any = None,
    budget_seconds: float = 1500,
) -> dict[str, Any]:
    run = ExpertRun(
        job=job, store=store, launcher=launcher, knowledge=knowledge, deadline=time.monotonic() + budget_seconds
    )
    subject = job.subject
    cap = min(DEPTH_CAPS[job.depth], job.max_researchers)
    if job.mode == "sweep":
        plan = "\n".join(f"- {b['objective']} (packs: {', '.join(b['packs'])})" for b in subject.sweep)
        mode_block = SWEEP_BLOCK.format(since=job.since, issuers=", ".join(job.issuers) or "none", plan=plan)
    else:
        mode_block = QUESTION_BLOCK.format(
            question=job.question,
            sub_question=job.sub_question or job.question,
            issuers=", ".join(job.issuers) or "none",
            themes=", ".join(job.themes) or "none",
            since=job.since,
            as_of_line=f"Point in time: only evidence published on or before {job.as_of}." if job.as_of else "",
        )
    prompt = SYSTEM_PROMPT.format(
        code=subject.code,
        name=subject.name,
        scope=subject.scope,
        packs=_pack_lines(subject),
        mode_block=mode_block,
        cap_line=f"1 to {cap}",
        rounds_left=MAX_ROUNDS,
        brief_step=BRIEF_STEP if job.mode == "question" else "5. (No brief in sweep mode.)",
    )
    spec = AgentSpec(
        actor=subject.code,
        name=f"Expert {subject.code} {subject.name}",
        effort="high",
        system_prompt=prompt,
        tools=run.tools(),
        max_turns=12,
        max_tokens=16000,
        tool_summaries={
            "spawn_researchers": lambda i: {"missions": len(i.get("missions") or [])},
            "stage_items": lambda i: {"selections": len(i.get("selections") or [])},
            "stage_subject_brief": lambda i: {"citations": len(i.get("citations") or [])},
        },
    )
    error = None
    try:
        run_agent(spec, "Start.", model_factory=model_factory, model_id=model_id, trace=trace)
    except AppError as exc:
        error = f"{exc.code}: {exc.message}"
    if error and not run.staged:
        raise AppError("model_error", error)
    return {
        "subject": subject.code,
        "mode": job.mode,
        "rounds": run.rounds,
        "researchers": run.researchers,
        "spawned": run.spawned,
        "findings": len(run.findings),
        "items": len(run.staged),
        "keys": sorted(run.staged.values()),
        "brief_key": run.brief_key,
        "note": run.note,
        "gaps": run.gaps,
        "warnings": run.warnings + ([error] if error else []) + ([] if run.finished else ["finish non appelé"]),
    }
