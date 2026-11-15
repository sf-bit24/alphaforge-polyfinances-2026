"""Base OKF d'un client : profil, journal, index et traces (CONTRACTS.md, section 5).

Le runtime est sans état entre deux invocations : chaque requête relit ``profil.md`` (et son ETag), modifie
l'état en mémoire, puis écrit une seule fois avec une précondition sur l'ETag. Une écriture concurrente sur
le même profil donne ``ConflictError``. Les faits passent tous par ``set_fact`` (champ connu, valeur validée,
provenance ``base:<question>``, ``a1:<tour>``, ``a2:<tour>`` ou ``settings``).
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from .. import clock, okf
from ..store import ConflictError, Store
from ..trace import Trace
from . import rules
from .questionnaire import Questionnaire, format_field_value

UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
STAGES = ("base_questions", "existing_portfolio", "portfolio_review", "followups", "complete")
SCHEMA = "alphaforge.profile/1"
PROVENANCE = re.compile(r"^(base:q_[a-z0-9_]+|a1:\d+|a2:\d+|settings)$")
ASKED_HISTORY = 24


def profile_key(client_id: str) -> str:
    return f"clients/{client_id}/profil.md"


def journal_key(client_id: str) -> str:
    return f"clients/{client_id}/journal.md"


def index_key(client_id: str) -> str:
    return f"clients/{client_id}/index.md"


def portfolio_key(client_id: str) -> str:
    return f"clients/{client_id}/portefeuille-existant.md"


def trace_key(client_id: str, action: str, stamp: str | None = None) -> str:
    safe_action = re.sub(r"[^a-z0-9.]+", "-", action.lower())
    return f"clients/{client_id}/traces/{stamp or clock.compact()}-{safe_action}.json"


def is_client_id(value: Any) -> bool:
    return isinstance(value, str) and bool(UUID4.match(value))


class ClientSession:
    def __init__(self, client_id: str, doc: okf.OkfDoc, etag: str | None, *, created: bool = False):
        self.client_id = client_id
        self.doc = doc
        self.etag = etag
        self.created = created
        self.new_journal: list[dict[str, Any]] = []
        self.index_dirty = created

    # ------------------------------------------------------------------ chargement et création
    @classmethod
    def load(cls, store: Store, client_id: str) -> ClientSession | None:
        obj = store.get(profile_key(client_id))
        if obj is None:
            return None
        return cls(client_id, okf.parse(obj.text), obj.etag)

    @classmethod
    def create(cls, client_id: str, locale: str, questionnaire: Questionnaire) -> ClientSession:
        now = clock.iso()
        data = {
            "schema": SCHEMA,
            "client_id": client_id,
            "created_at": now,
            "updated_at": now,
            "locale": locale,
            "stage": "base_questions",
            "questionnaire_version": questionnaire.version,
            "turn": 0,
            "facts": {},
            "answers": {},
            "pending_questions": [],
            "asked": [],
            "completion": {"stopped": False, "a1_complete": False},
            "last_message": None,
            "portfolio": {"status": "none", "turn": None},
        }
        doc = okf.new_doc(
            type="Investor Profile",
            title="Profil investisseur" if locale != "en" else "Investor profile",
            description="Profil en cinq dimensions, niveau de connaissances et complétude.",
            tags=["profil-investisseur"],
            owners=["alphaforge-a1"],
            sensitivity="client",
            generated_by="agent:A1",
            at=now,
            status="draft",
            stale_after=clock.iso(clock.utcnow() + timedelta(days=92)),
            data=data,
        )
        return cls(client_id, doc, None, created=True)

    # ------------------------------------------------------------------ accès
    @property
    def data(self) -> dict[str, Any]:
        return self.doc.data

    @property
    def stage(self) -> str:
        return self.data.get("stage", "base_questions")

    @property
    def locale(self) -> str:
        return self.data.get("locale", "fr")

    @property
    def facts(self) -> dict[str, dict[str, Any]]:
        return self.data.setdefault("facts", {})

    @property
    def answers(self) -> dict[str, dict[str, Any]]:
        return self.data.setdefault("answers", {})

    @property
    def turn(self) -> int:
        return int(self.data.get("turn") or 0)

    def values(self) -> dict[str, Any]:
        return {field_id: fact.get("value") for field_id, fact in self.facts.items()}

    def next_turn(self) -> int:
        self.data["turn"] = self.turn + 1
        return self.turn

    # ------------------------------------------------------------------ écritures en mémoire
    def set_stage(self, stage: str, provenance: str, trace: Trace | None = None, *, reason: str | None = None) -> None:
        """Change d'étape et l'inscrit au journal (``kind: stage``, ``value``, ``previous``, ``note``)."""
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage}")
        if not PROVENANCE.match(provenance):
            raise ValueError(f"invalid provenance {provenance!r}")
        previous = self.stage
        if previous == stage:
            return
        self.data["stage"] = stage
        self.new_journal.append(
            {
                "at": clock.iso(),
                "kind": "stage",
                "provenance": provenance,
                "value": stage,
                "previous": previous,
                "note": reason,
            }
        )
        if trace is not None:
            trace.add(
                "deterministic",
                "questionnaire",
                trace.t("Changement d'étape", "Stage change"),
                f"{previous} → {stage}",
                inputs={"from": previous},
                outputs={"stage": stage, "reason": reason},
            )

    def set_fact(
        self,
        field_id: str,
        value: Any,
        provenance: str,
        *,
        question_id: str | None = None,
        at: str | None = None,
        option: str | None = None,
    ) -> Any:
        """Écrit un fait validé et l'inscrit au journal (``kind: answer``, ``field``, ``value``, ``question_id``?,
        ``option``?, ``previous``?). ``option`` est l'identifiant de la tranche choisie quand un clic écrit un
        nombre."""
        if not PROVENANCE.match(provenance):
            raise ValueError(f"invalid provenance {provenance!r}")
        at = at or clock.iso()
        previous = self.facts.get(field_id, {}).get("value")
        if value is None:
            self.facts.pop(field_id, None)
        else:
            self.facts[field_id] = {"value": value, "provenance": provenance, "at": at}
        entry: dict[str, Any] = {
            "at": at,
            "kind": "answer",
            "provenance": provenance,
            "field": field_id,
            "value": value,
        }
        if question_id:
            entry["question_id"] = question_id
        if option is not None:
            entry["option"] = option
        if previous is not None and previous != value:
            entry["previous"] = previous
        self.new_journal.append(entry)
        return previous

    def record_answer(self, question_id: str, value: Any) -> None:
        self.answers[question_id] = {"value": value, "at": clock.iso()}

    def journal_answer(self, question_id: str, value: Any, provenance: str) -> None:
        """Réponse à une question libre d'A1 (sans champ du profil) : ``kind: answer`` avec ``field`` nul."""
        if not PROVENANCE.match(provenance):
            raise ValueError(f"invalid provenance {provenance!r}")
        self.new_journal.append(
            {
                "at": clock.iso(),
                "kind": "answer",
                "provenance": provenance,
                "field": None,
                "value": value,
                "question_id": question_id,
            }
        )

    def journal_created(self) -> None:
        """Première entrée du journal : la base du client vient d'être créée."""
        self.new_journal.append(
            {
                "at": clock.iso(),
                "kind": "stage",
                "provenance": "settings",
                "value": self.stage,
                "previous": None,
                "note": "base du client créée",
            }
        )

    def journal_message(self, text: str, locale: str, provenance: str) -> None:
        """Texte libre de l'investisseur (``kind: message``), écrit seulement après le garde-fou d'entrée."""
        if not PROVENANCE.match(provenance) or not provenance.startswith("a1:"):
            raise ValueError(f"invalid provenance {provenance!r}")
        self.new_journal.append(
            {"at": clock.iso(), "kind": "message", "provenance": provenance, "text": text, "locale": locale}
        )

    def remember_message(self, actor: str, text: str | None, locale: str) -> None:
        self.data["last_message"] = (
            {"actor": actor, "text": text, "locale": locale, "at": clock.iso()} if text else None
        )

    def remember_questions(self, questions: list[dict[str, Any]], turn: int) -> None:
        self.data["pending_questions"] = questions
        asked = list(self.data.get("asked") or [])
        for question in questions:
            asked.append(
                {
                    "turn": turn,
                    "id": question["id"],
                    "field": question.get("field"),
                    "kind": question["kind"],
                    "prompt": question["prompt"],
                    "answer": None,
                    "answered": False,
                }
            )
        self.data["asked"] = asked[-ASKED_HISTORY:]

    def mark_answered(self, question_id: str, value: Any) -> None:
        for item in self.data.get("asked") or []:
            if item.get("id") == question_id:
                item["answered"] = True
                item["answer"] = value

    # ------------------------------------------------------------------ persistance
    def commit(self, store: Store, questionnaire: Questionnaire, trace: Trace) -> None:
        now = clock.iso()
        self.data["updated_at"] = now
        self.doc.frontmatter["generated"] = {"by": "agent:A1", "at": now}
        values = self.values()
        risk = rules.risk_profile(questionnaire, values)
        score = rules.completeness(questionnaire, values, self.locale)
        self.data["derived"] = {
            "knowledge_level": rules.knowledge_level(questionnaire, values),
            "tolerance": risk["tolerance"],
            "capacity": risk["capacity"],
            "effective_risk": risk["effective"],
            "completeness": {k: score[k] for k in ("score", "displayed", "ready")},
        }
        self.doc.frontmatter["status"] = "stable" if self.stage == "complete" else "draft"
        self.doc.frontmatter["sources"] = self._sources()
        self.doc.body = render_profile_body(questionnaire, self, values, risk, score)
        text = okf.render(self.doc)
        with trace.step(
            "storage", "store", trace.t("Écriture du profil", "Profile written"), profile_key(self.client_id)
        ) as info:
            if self.etag is None:
                self.etag = store.put_text(profile_key(self.client_id), text, if_none_match=True)
            else:
                self.etag = store.put_text(profile_key(self.client_id), text, if_match=self.etag)
            info["outputs"] = {"key": profile_key(self.client_id), "stage": self.stage}
        if self.new_journal:
            self._append_journal(store, trace)
        if self.index_dirty:
            write_client_index(store, self.client_id, self.locale, has_portfolio=self.has_portfolio_doc(store))
            self.index_dirty = False
        self.created = False

    def has_portfolio_doc(self, store: Store) -> bool:
        return (self.data.get("portfolio") or {}).get("status") in {"draft", "confirmed"} or store.exists(
            portfolio_key(self.client_id)
        )

    def _sources(self) -> list[dict[str, Any]]:
        sources = []
        for field_id, fact in sorted(self.facts.items()):
            provenance = fact.get("provenance", "")
            sources.append(
                {
                    "id": f"{provenance.replace(':', '-')}-{field_id}",
                    "title": f"{field_id} ({provenance})",
                    "resource": provenance,
                    "retrieved_at": fact.get("at"),
                }
            )
        return sources

    def _append_journal(self, store: Store, trace: Trace) -> None:
        key = journal_key(self.client_id)
        with trace.step("storage", "store", trace.t("Ajout au journal", "Journal appended"), key) as info:
            for _ in range(4):
                obj = store.get(key)
                doc = okf.parse(obj.text) if obj else new_journal_doc(self.locale)
                entries = list(doc.data.get("entries") or [])
                entries.extend(self.new_journal)
                doc.data["entries"] = entries
                doc.frontmatter["generated"] = {"by": "agent:A1", "at": clock.iso()}
                doc.body = render_journal_body(entries, self.locale)
                try:
                    if obj is None:
                        store.put_text(key, okf.render(doc), if_none_match=True)
                    else:
                        store.put_text(key, okf.render(doc), if_match=obj.etag)
                    break
                except ConflictError:
                    continue
            else:
                raise ConflictError(key)
            info["outputs"] = {"key": key, "entries_added": len(self.new_journal)}
        self.new_journal = []


def load_journal_entries(store: Store, client_id: str, limit: int = 30) -> list[dict[str, Any]]:
    obj = store.get(journal_key(client_id))
    if obj is None:
        return []
    entries = okf.parse(obj.text).data.get("entries") or []
    return list(entries)[-limit:]


def new_journal_doc(locale: str) -> okf.OkfDoc:
    now = clock.iso()
    return okf.new_doc(
        type="Profile Journal",
        title="Journal du profil" if locale != "en" else "Profile journal",
        description="Chaque réponse et chaque mise à jour du profil, avec sa provenance et sa date.",
        tags=["profil-investisseur", "journal"],
        owners=["alphaforge-a1"],
        sensitivity="client",
        generated_by="agent:A1",
        at=now,
        status="stable",
        sources=[],
        data={"entries": []},
    )


def write_client_index(store: Store, client_id: str, locale: str, *, has_portfolio: bool) -> None:
    now = clock.iso()
    en = locale == "en"
    lines = [
        "# " + ("Client knowledge base" if en else "Base du client"),
        "",
        (
            "Fictitious profile built with AlphaForge AI (simulation only, no personalised advice)."
            if en
            else "Profil fictif construit avec AlphaForge AI (simulation seulement, aucun conseil personnalisé)."
        ),
        "",
        "- [" + ("Investor profile" if en else "Profil investisseur") + "](profil.md)",
        "- [" + ("Profile journal" if en else "Journal du profil") + "](journal.md)",
    ]
    if has_portfolio:
        lines.append("- [" + ("Existing portfolio" if en else "Portefeuille existant") + "](portefeuille-existant.md)")
    lines.append("- " + ("Execution traces: `traces/`" if en else "Traces d'exécution : `traces/`"))
    doc = okf.new_doc(
        type="Index",
        title="Base du client" if not en else "Client knowledge base",
        description="Documents OKF d'un investisseur : profil, journal, portefeuille existant et traces.",
        tags=["profil-investisseur", "index"],
        owners=["alphaforge-a1"],
        sensitivity="client",
        generated_by="agent:A1",
        at=now,
        status="stable",
        sources=[],
        data={"client_id": client_id},
        body="\n".join(lines) + "\n",
    )
    store.put_text(index_key(client_id), okf.render(doc))


def render_journal_body(entries: list[dict[str, Any]], locale: str) -> str:
    en = locale == "en"
    lines = [
        "# " + ("Profile journal" if en else "Journal du profil"),
        "",
        "| "
        + (" | ".join(["Date", "Type", "Field" if en else "Champ", "Value" if en else "Valeur", "Provenance"]))
        + " |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in entries[-300:]:
        value = entry.get("text") if entry.get("kind") == "message" else entry.get("value")
        text = value if isinstance(value, str) else ("" if value is None else str(value))
        text = text.replace("|", "\\|").replace("\n", " ")
        if len(text) > 120:
            text = text[:119] + "…"
        target = entry.get("field") or entry.get("question_id") or ""
        lines.append(
            f"| {entry.get('at', '')} | {entry.get('kind', '')} | {target} | {text} | {entry.get('provenance', '')} |"
        )
    return "\n".join(lines) + "\n"


def render_profile_body(
    q: Questionnaire,
    session: ClientSession,
    values: dict[str, Any],
    risk: dict[str, Any],
    score: dict[str, Any],
) -> str:
    locale = session.locale
    en = locale == "en"
    level = rules.knowledge_level(q, values)
    level_text = q.fields["knowledge.level"].value_label(level, locale) if level else "—"
    lines = [
        "# " + ("Investor profile" if en else "Profil investisseur"),
        "",
        "> "
        + (
            "Fictitious profile, simulation only: no real transaction and no personalised financial advice."
            if en
            else "Profil fictif, simulation seulement : aucune transaction réelle ni conseil financier personnalisé."
        ),
        "",
        f"- {'Stage' if en else 'Étape'} : `{session.stage}`",
        f"- {'Knowledge level' if en else 'Niveau de connaissances'} : {level_text}",
        f"- {'Risk tolerance' if en else 'Tolérance au risque'} : "
        f"{rules.level_label(q, risk['tolerance'], locale) or '—'}"
        f" · {'Risk capacity' if en else 'Capacité'} : {rules.level_label(q, risk['capacity'], locale) or '—'}"
        f" · {'Effective risk' if en else 'Risque effectif'} : "
        f"{rules.level_label(q, risk['effective'], locale, effective=True) or '—'}",
        f"- {'Completeness' if en else 'Complétude'} : {round(score['score'] * 100)} % "
        f"({'threshold' if en else 'seuil'} {round(q.threshold * 100)} %, "
        f"{'displayed cap' if en else 'plafond affiché'} {round(q.cap * 100)} %)",
        "",
    ]
    by_dimension: dict[str, list[str]] = {}
    for spec in q.fields.values():
        fact = session.facts.get(spec.id)
        if not fact:
            continue
        row = (
            f"| {spec.label_text(locale)} | {format_field_value(spec, fact['value'], locale).replace('|', '/')} "
            f"| {fact.get('provenance', '')} | {fact.get('at', '')} |"
        )
        by_dimension.setdefault(spec.dimension, []).append(row)
    for dimension, rows in by_dimension.items():
        lines += [
            f"## {dimension}",
            "",
            "| " + ("Field | Value | Provenance | Date" if en else "Champ | Valeur | Provenance | Date") + " |",
            "| --- | --- | --- | --- |",
            *rows,
            "",
        ]
    if score["missing"]:
        lines += ["## " + ("Missing fields" if en else "Champs manquants"), ""]
        lines += [f"- {item['label']} (`{item['dimension']}.{item['field']}`)" for item in score["missing"]]
        lines.append("")
    return "\n".join(lines)
