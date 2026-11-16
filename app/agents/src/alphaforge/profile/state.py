"""Base OKF d'un client : profil, journal, index et traces (CONTRACTS.md, section 5).

Le runtime est sans état entre deux invocations : chaque requête relit ``profil.md`` (et son ETag), modifie
l'état en mémoire, puis écrit une seule fois avec une précondition sur l'ETag. Une écriture concurrente sur
le même profil donne ``ConflictError``. Les faits passent tous par ``set_fact`` (champ connu, valeur validée,
provenance ``base:<question>``, ``a1:<tour>``, ``a2:<tour>`` ou ``settings``).
"""

from __future__ import annotations

import contextlib
import re
from datetime import timedelta
from typing import Any

from .. import clock, okf
from ..store import ConflictError, Store
from ..trace import Trace
from . import rules
from .questionnaire import Questionnaire, default_questionnaire, fact_band, format_fact, labeled

UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
STAGES = ("base_questions", "existing_portfolio", "portfolio_review", "followups", "complete")
SCHEMA = "alphaforge.profile/1"
PROVENANCE = re.compile(r"^(base:q_[a-z0-9_]+|a1:\d+|a2:\d+|settings)$")
ASKED_HISTORY = 24
JOURNAL_WRITE_ATTEMPTS = 4
JOURNAL_BODY_ENTRIES = 300
JOURNAL_CELL_MAX = 120


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


def _check_provenance(provenance: str) -> None:
    if not PROVENANCE.match(provenance):
        raise ValueError(f"invalid provenance {provenance!r}")


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
        stored = store.get(profile_key(client_id))
        if stored is None:
            return None
        return cls(client_id, okf.parse(stored.text), stored.etag)

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
            description=(
                "Your profile in five dimensions, your knowledge level and how complete it is."
                if locale == "en"
                else "Votre profil en cinq dimensions, votre niveau de connaissances et sa complétude."
            ),
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

    def confirmed_facts(self) -> dict[str, dict[str, Any]]:
        """Faits confirmés. Un fait tiré d'un texte libre (``confirmed: false``) n'y entre qu'après la
        confirmation de l'investisseur; s'il remplace une valeur confirmée, c'est elle (``replaces``) qui compte
        en attendant. Un fait sans la clé ``confirmed`` est confirmé."""
        out = {}
        for field_id, fact in self.facts.items():
            if fact.get("confirmed") is not False:
                out[field_id] = fact
            elif isinstance(fact.get("replaces"), dict):
                out[field_id] = fact["replaces"]
        return out

    def values(self) -> dict[str, Any]:
        """Valeurs confirmées : complétude, scores, conditions ``when``, arrêt et ``ProfileView`` ne voient pas
        une valeur qui attend sa confirmation."""
        return {field_id: fact.get("value") for field_id, fact in self.confirmed_facts().items()}

    def bands(self) -> dict[str, dict[str, Any]]:
        """Tranches des faits confirmés répondus par une tranche, par champ (``band`` du fait)."""
        return {
            field_id: band for field_id, fact in self.confirmed_facts().items() if (band := fact_band(fact)) is not None
        }

    def unconfirmed(self) -> dict[str, dict[str, Any]]:
        """Faits tirés d'un texte libre qui attendent la confirmation de l'investisseur."""
        return {field_id: fact for field_id, fact in self.facts.items() if fact.get("confirmed") is False}

    def next_turn(self) -> int:
        self.data["turn"] = self.turn + 1
        return self.turn

    # ------------------------------------------------------------------ écritures en mémoire
    def set_stage(self, stage: str, provenance: str, trace: Trace | None = None, *, reason: str | None = None) -> None:
        """Change d'étape et l'inscrit au journal (``kind: stage``, ``value``, ``previous``, ``note``)."""
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage}")
        _check_provenance(provenance)
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
                f"{stage_label(previous, trace.locale)} → {stage_label(stage, trace.locale)}",
                inputs={"from": previous},
                outputs={"stage": stage, "reason": reason},
            )

    def set_fact(  # noqa: PLR0913 - signature gardée : le service, A1 et les tests l'appellent par mots-clés
        self,
        field_id: str,
        value: Any,
        provenance: str,
        *,
        question_id: str | None = None,
        at: str | None = None,
        option: str | None = None,
        band: dict[str, Any] | None = None,
        confirmed: bool = True,
    ) -> Any:
        """Écrit un fait validé et l'inscrit au journal (``kind: answer``, ``field``, ``value``, ``question_id``?,
        ``option``?, ``previous``?). ``option`` est l'identifiant de la tranche choisie quand un clic écrit un
        nombre; ``band`` (``QuestionSpec.option_band``, ``tranche_bands``) est cette tranche, gardée avec le fait
        pour que tout ce qui le montre la cite. ``confirmed=False`` marque une valeur tirée d'un texte libre, à
        faire confirmer."""
        _check_provenance(provenance)
        at = at or clock.iso()
        existing = self.facts.get(field_id) or {}
        previous = existing.get("value")
        if value is None:
            self.facts.pop(field_id, None)
        else:
            self.facts[field_id] = {"value": value, "provenance": provenance, "at": at}
            if band:
                self.facts[field_id]["band"] = band
            if not confirmed:
                self.facts[field_id]["confirmed"] = False
                # Une valeur confirmée remplacée par un texte libre reste en vigueur jusqu'à la confirmation.
                replaced = existing.get("replaces") if existing.get("confirmed") is False else existing
                if replaced:
                    self.facts[field_id]["replaces"] = {
                        k: replaced[k] for k in ("value", "provenance", "at", "band") if k in replaced
                    }
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

    def confirm_fact(self, field_id: str, provenance: str, *, question_id: str) -> None:
        """L'investisseur confirme une valeur tirée d'un texte libre : ``kind: answer`` avec ``question_id``."""
        _check_provenance(provenance)
        fact = self.facts[field_id]
        fact.pop("confirmed", None)
        fact.pop("replaces", None)
        self.new_journal.append(
            {
                "at": clock.iso(),
                "kind": "answer",
                "provenance": provenance,
                "field": field_id,
                "value": fact.get("value"),
                "question_id": question_id,
            }
        )

    def reject_fact(self, field_id: str, provenance: str, *, question_id: str | None = None) -> None:
        """L'investisseur refuse une valeur tirée d'un texte libre : la valeur confirmée qu'elle remplaçait revient,
        sinon le champ redevient manquant. Le journal garde la valeur refusée dans ``previous``."""
        replaced = (self.facts.get(field_id) or {}).get("replaces")
        if isinstance(replaced, dict):
            rejected = self.facts[field_id]["value"]
            self.facts[field_id] = dict(replaced)
            entry: dict[str, Any] = {
                "at": clock.iso(),
                "kind": "answer",
                "provenance": provenance,
                "field": field_id,
                "value": replaced["value"],
                "previous": rejected,
            }
            if question_id:
                entry["question_id"] = question_id
            self.new_journal.append(entry)
        else:
            self.set_fact(field_id, None, provenance, question_id=question_id)

    def record_answer(self, question_id: str, value: Any) -> None:
        self.answers[question_id] = {"value": value, "at": clock.iso()}

    def journal_answer(self, question_id: str, value: Any, provenance: str) -> None:
        """Réponse à une question libre d'A1 (sans champ du profil) : ``kind: answer`` avec ``field`` nul."""
        _check_provenance(provenance)
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
        _check_provenance(provenance)
        if not provenance.startswith("a1:"):
            raise ValueError(f"invalid provenance {provenance!r}")
        self.new_journal.append(
            {"at": clock.iso(), "kind": "message", "provenance": provenance, "text": text, "locale": locale}
        )

    def remember_message(self, actor: str, text: str | None, locale: str) -> None:
        self.data["last_message"] = (
            {"actor": actor, "text": text, "locale": locale, "at": clock.iso()} if text else None
        )

    def remember_questions(  # noqa: PLR0913 - une table par information gardée hors des questions, par mots-clés
        self,
        questions: list[dict[str, Any]],
        turn: int,
        *,
        choices: dict[str, dict[str, Any]] | None = None,
        confirmations: dict[str, str] | None = None,
        reasons: dict[str, str] | None = None,
        bands: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Questions envoyées à l'investisseur. Les tables des tranches (identifiant → nombre) restent hors des
        questions, dans ``pending_choices``, avec les tranches elles-mêmes (identifiant → ``band``) dans
        ``pending_bands``, et le champ visé par une question de confirmation ``cf_`` dans
        ``pending_confirmations``. ``followup_counts`` compte les questions générées par A1 et les
        questions ouvertes envoyées dans la session (``asked`` est tronqué et contient aussi le secours)."""
        self.data["pending_questions"] = questions
        ids = {question["id"] for question in questions}
        self.data["pending_choices"] = {
            question_id: table for question_id, table in (choices or {}).items() if question_id in ids
        }
        self.data["pending_bands"] = {
            question_id: table for question_id, table in (bands or {}).items() if question_id in ids
        }
        self.data["pending_confirmations"] = {
            question_id: field_id for question_id, field_id in (confirmations or {}).items() if question_id in ids
        }
        counts = dict(self.data.get("followup_counts") or {})
        counts["generated"] = int(counts.get("generated") or 0) + sum(
            question.get("source") == "a1" for question in questions
        )
        counts["open"] = int(counts.get("open") or 0) + sum(question.get("kind") == "text" for question in questions)
        self.data["followup_counts"] = counts
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
                    **({"reason": reasons[question["id"]]} if reasons and question["id"] in reasons else {}),
                }
            )
        self.data["asked"] = asked[-ASKED_HISTORY:]

    def clear_pending(self) -> None:
        self.data["pending_questions"] = []
        self.data["pending_choices"] = {}
        self.data["pending_bands"] = {}
        self.data["pending_confirmations"] = {}

    def mark_answered(self, question_id: str, value: Any) -> None:
        for item in self.data.get("asked") or []:
            if item.get("id") == question_id:
                item["answered"] = True
                item["answer"] = value

    # ------------------------------------------------------------------ persistance
    def _refresh_document(self, questionnaire: Questionnaire) -> None:
        """Met à jour les valeurs dérivées, l'état, les sources et le corps de ``profil.md`` avant l'écriture."""
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
        self.doc.frontmatter["sources"] = self._sources(questionnaire)
        self.doc.body = render_profile_body(questionnaire, self, values, risk, score)

    def _write_profile(self, store: Store, trace: Trace) -> None:
        """Écrit ``profil.md`` avec la précondition sur l'ETag lu (création seulement s'il n'y en a pas)."""
        text = okf.render(self.doc)
        with trace.step(
            "storage",
            "store",
            trace.t("Profil enregistré", "Profile saved"),
            inputs={"key": profile_key(self.client_id)},
        ) as info:
            if self.etag is None:
                self.etag = store.put_text(profile_key(self.client_id), text, if_none_match=True)
            else:
                self.etag = store.put_text(profile_key(self.client_id), text, if_match=self.etag)
            info["outputs"] = {"key": profile_key(self.client_id), "stage": self.stage}

    def commit(self, store: Store, questionnaire: Questionnaire, trace: Trace) -> None:
        self._refresh_document(questionnaire)
        self._write_profile(store, trace)
        if self.new_journal:
            self._append_journal(store, trace)
        if self.index_dirty:
            write_client_index(
                store,
                self.client_id,
                self.locale,
                has_portfolio=self.has_portfolio_doc(store),
                notes=(self.data.get("brain") or {}).get("documents"),
            )
            self.index_dirty = False
        self.created = False

    def has_portfolio_doc(self, store: Store) -> bool:
        return (self.data.get("portfolio") or {}).get("status") in {"draft", "confirmed"} or store.exists(
            portfolio_key(self.client_id)
        )

    def _sources(self, questionnaire: Questionnaire) -> list[dict[str, Any]]:
        sources = []
        for field_id, fact in sorted(self.facts.items()):
            provenance = fact.get("provenance", "")
            sources.append(
                {
                    "id": f"{provenance.replace(':', '-')}-{field_id}",
                    "title": fact_source_title(field_id, provenance, self.locale, questionnaire),
                    "resource": provenance,
                    "retrieved_at": fact.get("at"),
                }
            )
        return sources

    def _try_append_journal(self, store: Store, key: str) -> bool:
        """Relit le journal, y ajoute les nouvelles entrées et l'écrit; faux si une autre écriture est passée avant."""
        stored = store.get(key)
        doc = okf.parse(stored.text) if stored else new_journal_doc(self.locale)
        entries = list(doc.data.get("entries") or [])
        entries.extend(self.new_journal)
        doc.data["entries"] = entries
        doc.frontmatter["generated"] = {"by": "agent:A1", "at": clock.iso()}
        doc.body = render_journal_body(entries, self.locale)
        try:
            if stored is None:
                store.put_text(key, okf.render(doc), if_none_match=True)
            else:
                store.put_text(key, okf.render(doc), if_match=stored.etag)
        except ConflictError:
            return False
        return True

    def _append_journal(self, store: Store, trace: Trace) -> None:
        key = journal_key(self.client_id)
        with trace.step(
            "storage", "store", trace.t("Journal du profil mis à jour", "Profile journal updated"), inputs={"key": key}
        ) as info:
            if not any(self._try_append_journal(store, key) for _ in range(JOURNAL_WRITE_ATTEMPTS)):
                raise ConflictError(key)
            info["outputs"] = {"key": key, "entries_added": len(self.new_journal)}
        self.new_journal = []


def load_journal_entries(store: Store, client_id: str, limit: int = 30) -> list[dict[str, Any]]:
    stored = store.get(journal_key(client_id))
    if stored is None:
        return []
    entries = okf.parse(stored.text).data.get("entries") or []
    return list(entries)[-limit:]


def new_journal_doc(locale: str) -> okf.OkfDoc:
    now = clock.iso()
    return okf.new_doc(
        type="Profile Journal",
        title="Journal du profil" if locale != "en" else "Profile journal",
        description=(
            "Each answer and each update of your profile, with where it came from and its date."
            if locale == "en"
            else "Chaque réponse et chaque mise à jour de votre profil, avec son origine et sa date."
        ),
        tags=["profil-investisseur", "journal"],
        owners=["alphaforge-a1"],
        sensitivity="client",
        generated_by="agent:A1",
        at=now,
        status="stable",
        sources=[],
        data={"entries": []},
    )


def _render_index_body(locale: str, *, has_portfolio: bool, notes: list[dict[str, Any]] | None) -> str:
    is_english = locale == "en"
    lines = [
        "# " + ("Your personal documents" if is_english else "Vos documents personnels"),
        "",
        (
            "Fictitious profile built with AlphaForge AI (simulation only, no personalised advice)."
            if is_english
            else "Profil fictif construit avec AlphaForge AI (simulation seulement, aucun conseil personnalisé)."
        ),
        "",
        "- [" + ("Investor profile" if is_english else "Profil investisseur") + "](profil.md)",
        "- [" + ("Profile journal" if is_english else "Journal du profil") + "](journal.md)",
    ]
    if has_portfolio:
        lines.append(
            "- [" + ("Existing portfolio" if is_english else "Portefeuille existant") + "](portefeuille-existant.md)"
        )
    if notes:
        lines += ["", "## " + ("Yan's notes" if is_english else "Notes de Yan"), ""]
        lines += [f"- [{note.get('title') or note['path']}]({note['path']})" for note in notes]
    return "\n".join(lines) + "\n"


def write_client_index(
    store: Store,
    client_id: str,
    locale: str,
    *,
    has_portfolio: bool,
    notes: list[dict[str, Any]] | None = None,
) -> None:
    now = clock.iso()
    doc = okf.new_doc(
        type="Index",
        title="Vos documents personnels" if locale != "en" else "Your personal documents",
        description=(
            "Your profile, its journal, your existing portfolio and Yan's notes."
            if locale == "en"
            else "Votre profil, son journal, votre portefeuille existant et les notes de Yan."
        ),
        tags=["profil-investisseur", "index"],
        owners=["alphaforge-a1"],
        sensitivity="client",
        generated_by="agent:A1",
        at=now,
        status="stable",
        sources=[],
        data={"client_id": client_id},
        body=_render_index_body(locale, has_portfolio=has_portfolio, notes=notes),
    )
    store.put_text(index_key(client_id), okf.render(doc))


# Ce que l'investisseur lit de l'étape, de l'origine d'un fait et du genre d'une entrée du journal (français, anglais).
STAGE_LABELS = {
    "base_questions": ("Questions de base", "Basic questions"),
    "existing_portfolio": ("Portefeuille existant", "Existing portfolio"),
    "portfolio_review": ("Vérification du portefeuille", "Portfolio review"),
    "followups": ("Questions de Yan", "Yan's questions"),
    "complete": ("Profil complet", "Profile complete"),
}
ORIGIN_LABELS = {
    "base": ("questionnaire", "questionnaire"),
    "a1": ("échange avec Yan", "conversation with Yan"),
    "a2": ("portefeuille existant", "existing portfolio"),
    "settings": ("réglages", "settings"),
}
ENTRY_LABELS = {"stage": ("Étape", "Step"), "answer": ("Réponse", "Answer"), "message": ("Message", "Message")}
DIMENSION_LABELS = {
    "knowledge": ("Connaissances", "Knowledge"),
    "objective": ("Objectif", "Objective"),
    "horizon": ("Horizon", "Horizon"),
    "risk_tolerance": ("Tolérance au risque", "Risk tolerance"),
    "risk_capacity": ("Capacité à prendre des risques", "Risk capacity"),
    "constraints": ("Contraintes", "Constraints"),
    "preferences": ("Préférences", "Preferences"),
    "behavior": ("Comportement", "Behaviour"),
    "context": ("Contexte", "Context"),
}


def _shown(labels: dict[str, tuple[str, str]], key: str | None, locale: str) -> str:
    pair = labels.get(key or "")
    if pair is None:
        return key or "—"
    return pair[1] if locale == "en" else pair[0]


def stage_label(stage: str | None, locale: str) -> str:
    """Nom de l'étape tel que l'investisseur le lit (« Questions de base »), jamais son code."""
    return _shown(STAGE_LABELS, stage, locale) if stage else "—"


def origin_label(provenance: str | None, locale: str) -> str:
    """Origine d'un fait en mots simples (« questionnaire », « échange avec Yan »), jamais sa provenance brute."""
    return _shown(ORIGIN_LABELS, (provenance or "").split(":", 1)[0], locale)


def fact_source_title(
    field_id: str, provenance: str | None, locale: str, questionnaire: Questionnaire | None = None
) -> str:
    """Titre de la source d'un fait : le nom du champ et son origine (« Horizon de placement (questionnaire) »)."""
    spec = (questionnaire or default_questionnaire()).fields.get(field_id)
    label = spec.label_text(locale) if spec else field_id
    return f"{label} ({origin_label(provenance, locale)})"


def _journal_value(entry: dict[str, Any], questionnaire: Questionnaire, locale: str) -> str:
    """Valeur d'une entrée du journal en clair : le texte, le nom de l'étape ou la valeur telle que le profil la
    montre; une valeur que le questionnaire ne sait pas montrer est écrite telle quelle."""
    kind, value = entry.get("kind"), entry.get("value")
    if kind == "message":
        value = entry.get("text")
    elif kind == "stage":
        value = stage_label(value if isinstance(value, str) else None, locale)
    elif entry.get("field") in questionnaire.fields and value is not None:
        with contextlib.suppress(TypeError, ValueError, KeyError):
            value = questionnaire.format_value(entry["field"], value, locale)
    return value if isinstance(value, str) else ("" if value is None else str(value))


def _journal_target(entry: dict[str, Any], questionnaire: Questionnaire, locale: str) -> str:
    """Ce que vise l'entrée : le nom du champ; une question sans champ est une question de Yan."""
    spec = questionnaire.fields.get(entry.get("field") or "")
    if spec is not None:
        return spec.label_text(locale)
    if entry.get("question_id"):
        return "Yan's question" if locale == "en" else "Question de Yan"
    return ""


def _journal_row(entry: dict[str, Any], questionnaire: Questionnaire, locale: str) -> str:
    text = _journal_value(entry, questionnaire, locale).replace("|", "\\|").replace("\n", " ")
    if len(text) > JOURNAL_CELL_MAX:
        text = text[: JOURNAL_CELL_MAX - 1] + "…"
    target = _journal_target(entry, questionnaire, locale).replace("|", "/")
    kind = _shown(ENTRY_LABELS, entry.get("kind"), locale)
    origin = origin_label(entry.get("provenance"), locale)
    return f"| {str(entry.get('at', ''))[:10]} | {kind} | {target} | {text} | {origin} |"


def render_journal_body(entries: list[dict[str, Any]], locale: str) -> str:
    is_english = locale == "en"
    questionnaire = default_questionnaire()
    lines = [
        "# " + ("Profile journal" if is_english else "Journal du profil"),
        "",
        "| "
        + (
            " | ".join(
                [
                    "Date",
                    "Event" if is_english else "Événement",
                    "Item" if is_english else "Élément",
                    "Value" if is_english else "Valeur",
                    "Origin" if is_english else "Origine",
                ]
            )
        )
        + " |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [_journal_row(entry, questionnaire, locale) for entry in entries[-JOURNAL_BODY_ENTRIES:]]
    return "\n".join(lines) + "\n"


def _risk_line(questionnaire: Questionnaire, risk: dict[str, Any], locale: str) -> str:
    tolerance = rules.level_label(questionnaire, risk["tolerance"], locale) or "—"
    capacity = rules.level_label(questionnaire, risk["capacity"], locale) or "—"
    effective = rules.level_label(questionnaire, risk["effective"], locale, effective=True) or "—"
    if locale == "en":
        parts = (("Risk tolerance", tolerance), ("Risk capacity", capacity), ("Effective risk", effective))
    else:
        parts = (("Tolérance au risque", tolerance), ("Capacité", capacity), ("Risque effectif", effective))
    return "- " + " · ".join(labeled(label, text, locale) for label, text in parts)


def _completeness_line(questionnaire: Questionnaire, score: float, locale: str) -> str:
    reached, threshold = round(score * 100), round(questionnaire.threshold * 100)
    if locale == "en":
        return f"- Completeness: {reached}% ({threshold}% is enough to move on)"
    return f"- {labeled('Complétude', f'{reached} % ({threshold} % suffit pour passer à la suite)', locale)}"


def _fact_rows_by_dimension(questionnaire: Questionnaire, session: ClientSession, locale: str) -> dict[str, list[str]]:
    """Lignes du tableau des faits de chaque dimension, dans l'ordre des champs du questionnaire."""
    unconfirmed_mark = " (to be confirmed)" if locale == "en" else " (à confirmer)"
    rows: dict[str, list[str]] = {}
    for spec in questionnaire.fields.values():
        fact = session.facts.get(spec.id)
        if not fact:
            continue
        shown = format_fact(spec, fact, locale).replace("|", "/")
        if fact.get("confirmed") is False:
            shown += unconfirmed_mark
        origin = origin_label(fact.get("provenance"), locale)
        row = f"| {spec.label_text(locale)} | {shown} | {origin} | {str(fact.get('at', ''))[:10]} |"
        rows.setdefault(spec.dimension, []).append(row)
    return rows


def _fact_table_lines(questionnaire: Questionnaire, session: ClientSession, locale: str) -> list[str]:
    header = "| " + ("Item | Value | Origin | Date" if locale == "en" else "Élément | Valeur | Origine | Date") + " |"
    lines: list[str] = []
    for dimension, rows in _fact_rows_by_dimension(questionnaire, session, locale).items():
        title = _shown(DIMENSION_LABELS, dimension, locale)
        lines += [f"## {title}", "", header, "| --- | --- | --- | --- |", *rows, ""]
    return lines


def _missing_field_lines(missing: list[dict[str, Any]], locale: str) -> list[str]:
    if not missing:
        return []
    title = "## " + ("Still to answer" if locale == "en" else "Reste à préciser")
    return [title, "", *(f"- {item['label']}" for item in missing), ""]


def render_profile_body(
    questionnaire: Questionnaire,
    session: ClientSession,
    values: dict[str, Any],
    risk: dict[str, Any],
    score: dict[str, Any],
) -> str:
    locale = session.locale
    is_english = locale == "en"
    level = rules.knowledge_level(questionnaire, values)
    level_text = questionnaire.fields["knowledge.level"].value_label(level, locale) if level else "—"
    lines = [
        "# " + ("Investor profile" if is_english else "Profil investisseur"),
        "",
        "> "
        + (
            "Fictitious profile, simulation only: no real transaction and no personalised financial advice."
            if is_english
            else "Profil fictif, simulation seulement : aucune transaction réelle ni conseil financier personnalisé."
        ),
        "",
        f"- {labeled('Step' if is_english else 'Étape', stage_label(session.stage, locale), locale)}",
        f"- {labeled('Knowledge level' if is_english else 'Niveau de connaissances', level_text, locale)}",
        _risk_line(questionnaire, risk, locale),
        _completeness_line(questionnaire, score["score"], locale),
        "",
        *_fact_table_lines(questionnaire, session, locale),
        *_missing_field_lines(score["missing"], locale),
    ]
    return "\n".join(lines)
