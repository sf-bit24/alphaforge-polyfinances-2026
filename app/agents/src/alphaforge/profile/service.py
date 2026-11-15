"""Runtime ``profile`` : actions de CONTRACTS.md 3.2, réponses ``ClientState`` et streaming SSE (3.4).

Les actions déterministes (``session.*``, ``base.answer``, ``portfolio.confirm``, ``portfolio.skip``,
``settings.update``, ``profile.get``, ``kb.*``) n'appellent aucun modèle. ``portfolio.submit`` appelle A2 et
``followup.reply`` appelle A1, sauf ``stop: true``.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from .. import clock, okf
from ..agentkit import ModelFactory, bedrock_model_factory
from ..collect.fetchers import fetch_yahoo_chart
from ..config import Settings
from ..errors import AppError, error_response, ok_response, pick
from ..store import ConflictError, Store
from ..trace import Emitter, Trace
from . import a1 as a1_agent
from . import a2 as a2_agent
from . import kb, rules
from . import portfolio as pf
from .questionnaire import InvalidValue, Questionnaire, default_questionnaire, reason_text
from .state import ClientSession, is_client_id, load_journal_entries, portfolio_key, trace_key
from .views import client_state

logger = logging.getLogger("alphaforge.profile")
LOCALES = ("fr", "en")
STREAMABLE = frozenset({"portfolio.submit", "followup.reply"})
MAX_MESSAGE = 4000
QUESTION_TURN = re.compile(r"^(?:a1|fb)_(\d+)_\d+$")
_DONE = object()


@dataclass
class Request:
    action: str
    payload: dict[str, Any]
    trace: Trace
    emitter: Emitter | None

    @property
    def locale_hint(self) -> str:
        value = self.payload.get("locale")
        return value if value in LOCALES else "fr"


class QueueEmitter(Emitter):
    def __init__(self, events: queue.Queue):
        self.events = events

    def trace(self, step: dict[str, Any]) -> None:
        self.events.put({"type": "trace", "step": step})

    def delta(self, text: str) -> None:
        self.events.put({"type": "delta", "text": text})


class ProfileService:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        *,
        questionnaire: Questionnaire | None = None,
        model_factory: ModelFactory | None = None,
        quote_fetcher: pf.QuoteFetcher | None = fetch_yahoo_chart,
        kb_search: kb.KnowledgeSearch | None = None,
    ):
        self.settings = settings
        self.store = store
        self.q = questionnaire or default_questionnaire()
        self.model_factory = model_factory or bedrock_model_factory(settings)
        self.quote_fetcher = quote_fetcher
        self.kb_search = kb_search or kb.KnowledgeSearch(settings)
        self.actions: dict[str, Callable[[Request], dict[str, Any]]] = {
            "health": self.health,
            "session.start": self.session_start,
            "session.resume": self.session_resume,
            "base.answer": self.base_answer,
            "portfolio.submit": self.portfolio_submit,
            "portfolio.confirm": self.portfolio_confirm,
            "portfolio.skip": self.portfolio_skip,
            "followup.reply": self.followup_reply,
            "settings.update": self.settings_update,
            "profile.get": self.profile_get,
            "kb.list": self.kb_list,
            "kb.get": self.kb_get,
        }

    # ------------------------------------------------------------------ point d'entrée
    def handle(self, payload: Any) -> dict[str, Any] | Iterator[dict[str, Any]]:
        if isinstance(payload, dict) and payload.get("stream") is True and payload.get("action") in STREAMABLE:
            return self._stream(payload)
        return self.run(payload, None)

    def run(self, payload: Any, emitter: Emitter | None) -> dict[str, Any]:
        release = self.settings.release
        if not isinstance(payload, dict):
            return error_response(release, AppError("bad_request", "Le corps doit être un objet JSON."))
        action = payload.get("action")
        req = Request(
            action=str(action), payload=payload, trace=Trace(self._initial_locale(payload), emitter), emitter=emitter
        )
        if not isinstance(action, str) or not action:
            return error_response(
                release, AppError("bad_request", pick(req.locale_hint, "action est requise.", "action is required."))
            )
        handler = self.actions.get(action)
        if handler is None:
            return error_response(
                release,
                AppError(
                    "unknown_action",
                    pick(req.locale_hint, f"Action inconnue : {action}.", f"Unknown action: {action}."),
                    {"action": action},
                ),
            )
        try:
            return ok_response(release, **handler(req))
        except AppError as exc:
            return error_response(release, exc)
        except ConflictError:
            return error_response(
                release,
                AppError(
                    "conflict",
                    pick(
                        req.locale_hint,
                        "Le profil a été modifié par une autre requête. Rechargez puis réessayez.",
                        "The profile was changed by another request. Reload and try again.",
                    ),
                ),
            )
        except Exception:
            logger.exception("profile action failed: %s", action)
            return error_response(
                release,
                AppError("internal", pick(req.locale_hint, "Erreur interne.", "Internal error.")),
            )

    def _stream(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        events: queue.Queue = queue.Queue()
        emitter = QueueEmitter(events)

        def worker() -> None:
            try:
                response = self.run(payload, emitter)
                if response.get("ok"):
                    events.put({"type": "result", "result": response})
                else:
                    events.put({"type": "error", "error": response["error"]})
            except Exception:  # pragma: no cover - run() capture déjà les erreurs
                logger.exception("stream worker failed")
                events.put(
                    {"type": "error", "error": {"code": "internal", "message": "Internal error.", "details": {}}}
                )
            finally:
                events.put(_DONE)

        threading.Thread(target=worker, name="alphaforge-stream", daemon=True).start()

        def generate() -> Iterator[dict[str, Any]]:
            while True:
                item = events.get()
                if item is _DONE:
                    return
                yield item

        return generate()

    # ------------------------------------------------------------------ utilitaires
    def _initial_locale(self, payload: dict[str, Any]) -> str:
        value = payload.get("locale")
        if value in LOCALES:
            return value
        client_id = payload.get("client_id")
        if is_client_id(client_id):
            try:
                session = ClientSession.load(self.store, client_id)
            except Exception:
                session = None
            if session is not None:
                return session.locale
        return "fr"

    def _locale_param(self, req: Request) -> str | None:
        value = req.payload.get("locale")
        if value is None:
            return None
        if value not in LOCALES:
            raise AppError(
                "bad_request",
                pick(req.locale_hint, "locale doit valoir fr ou en.", "locale must be fr or en."),
                {"locale": value},
            )
        return value

    def _client(self, req: Request) -> ClientSession:
        client_id = req.payload.get("client_id")
        if not is_client_id(client_id):
            raise AppError(
                "bad_request", pick(req.trace.locale, "client_id doit être un UUID v4.", "client_id must be a UUID v4.")
            )
        session = ClientSession.load(self.store, client_id)
        if session is None:
            raise AppError(
                "not_found",
                pick(req.trace.locale, "Client introuvable.", "Client not found."),
                {"client_id": client_id},
            )
        return session

    def _expect_stage(self, req: Request, session: ClientSession, stages: tuple[str, ...]) -> None:
        if session.stage not in stages:
            raise AppError(
                "conflict",
                pick(
                    req.trace.locale,
                    f"Action impossible à l'étape {session.stage}.",
                    f"Action not allowed at stage {session.stage}.",
                ),
                {"stage": session.stage, "expected": list(stages)},
            )

    def _portfolio(self, session: ClientSession) -> dict[str, Any] | None:
        if (session.data.get("portfolio") or {}).get("status") not in ("draft", "confirmed"):
            return None
        obj = self.store.get(portfolio_key(session.client_id))
        if obj is None:
            return None
        return okf.parse(obj.text).data.get("view")

    def _state(
        self,
        req: Request,
        session: ClientSession,
        locale: str,
        *,
        message: str | None = None,
        portfolio: Any = "load",
        documents: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        view = self._portfolio(session) if portfolio == "load" else portfolio
        return client_state(
            self.q, session, locale=locale, trace=req.trace, message=message, portfolio=view, documents=documents
        )

    def _commit(self, req: Request, session: ClientSession) -> None:
        session.commit(self.store, self.q, req.trace)
        key = trace_key(session.client_id, req.action)
        req.trace.add("storage", "store", req.trace.t("Trace enregistrée", "Trace saved"), key)
        self.store.put_json(
            key,
            {
                "action": req.action,
                "at": clock.iso(),
                "release": self.settings.release,
                "client_id": session.client_id,
                "stage": session.stage,
                "steps": req.trace.steps,
            },
        )

    def _completeness_step(self, req: Request, session: ClientSession) -> None:
        score = rules.completeness(self.q, session.values(), req.trace.locale)
        req.trace.add(
            "deterministic",
            "completeness",
            req.trace.t("Complétude calculée par le code", "Completeness computed by code"),
            f"{round(score['score'] * 100)} % / {round(self.q.threshold * 100)} %",
            outputs={"score": score["score"], "ready": score["ready"], "missing": len(score["missing"])},
        )

    def _last_message(self, session: ClientSession, locale: str) -> str | None:
        last = session.data.get("last_message") or {}
        return last.get("text") if last.get("locale") == locale else None

    # ------------------------------------------------------------------ actions
    def health(self, req: Request) -> dict[str, Any]:
        return {"role": self.settings.role, "env": self.settings.env}

    def session_start(self, req: Request) -> dict[str, Any]:
        locale = self._locale_param(req) or "fr"
        req.trace.locale = locale
        client_id = req.payload.get("client_id")
        if client_id is not None:
            if not is_client_id(client_id):
                raise AppError(
                    "bad_request", pick(locale, "client_id doit être un UUID v4.", "client_id must be a UUID v4.")
                )
            existing = ClientSession.load(self.store, client_id)
            if existing is not None:
                req.trace.add(
                    "storage",
                    "store",
                    req.trace.t("Base du client existante", "Existing client base"),
                    client_id,
                    outputs={"stage": existing.stage},
                )
                return self._state(req, existing, locale, message=self._last_message(existing, locale))
        else:
            client_id = str(uuid.uuid4())
        session = ClientSession.create(client_id, locale, self.q)
        session.journal_created()
        req.trace.add(
            "deterministic",
            "questionnaire",
            req.trace.t("Base du client créée", "Client base created"),
            client_id,
            outputs={"questionnaire_version": self.q.version, "stage": session.stage},
        )
        first = self.q.next_question(session.values(), session.answers)
        req.trace.add(
            "deterministic",
            "questionnaire",
            req.trace.t("Première question choisie par les règles", "First question chosen by the rules"),
            first.id if first else None,
            outputs={"next": first.id if first else None},
        )
        self._commit(req, session)
        return self._state(req, session, locale, portfolio=None)

    def session_resume(self, req: Request) -> dict[str, Any]:
        session = self._client(req)
        locale = self._locale_param(req) or session.locale
        req.trace.locale = locale
        return self._state(req, session, locale, message=self._last_message(session, locale))

    def profile_get(self, req: Request) -> dict[str, Any]:
        session = self._client(req)
        locale = self._locale_param(req) or session.locale
        req.trace.locale = locale
        documents = [
            {"key": item["key"], "title": item["title"]}
            for item in kb.list_documents(self.store, f"clients/{session.client_id}/")
        ]
        return self._state(req, session, locale, message=self._last_message(session, locale), documents=documents)

    def base_answer(self, req: Request) -> dict[str, Any]:
        session = self._client(req)
        locale = session.locale
        req.trace.locale = locale
        self._expect_stage(req, session, ("base_questions",))
        question_id = req.payload.get("question_id")
        if "value" not in req.payload:
            raise AppError("bad_request", pick(locale, "value est requise.", "value is required."))
        question = self.q.question(question_id) if isinstance(question_id, str) else None
        if question is None:
            raise AppError(
                "invalid_answer", pick(locale, "Question inconnue.", "Unknown question."), {"question_id": question_id}
            )
        if not self.q.is_question_applicable(question, session.values()):
            raise AppError(
                "invalid_answer",
                pick(
                    locale,
                    "Cette question ne s'applique pas à ce profil.",
                    "This question does not apply to this profile.",
                ),
                {"question_id": question_id},
            )
        with req.trace.step(
            "deterministic",
            "questionnaire",
            req.trace.t("Réponse validée par les règles", "Answer validated by the rules"),
            question.id,
            inputs={"question_id": question.id, "kind": question.kind},
        ) as info:
            try:
                value = self.q.validate_answer(question, req.payload.get("value"))
            except InvalidValue as exc:
                info["title"] = req.trace.t("Réponse refusée", "Answer rejected")
                info["outputs"] = {"reason": exc.reason}
                raise AppError(
                    "invalid_answer",
                    reason_text(exc.reason, locale),
                    {"question_id": question.id, "reason": exc.reason, **exc.params},
                ) from exc
            info["outputs"] = {"field": question.field.id, "value": value}
        session.record_answer(question.id, value)
        session.set_fact(question.field.id, value, f"base:{question.id}", question_id=question.id)
        self._prune_branches(session)
        values = session.values()
        if question.field.dimension == "knowledge":
            level = rules.knowledge_level(self.q, values)
            if level:
                req.trace.add(
                    "deterministic",
                    "questionnaire",
                    req.trace.t("Niveau de connaissances calculé", "Knowledge level computed"),
                    req.trace.t("min(auto-évaluation, niveau mesuré + 1)", "min(self-assessment, measured level + 1)"),
                    outputs={
                        "knowledge_level": level,
                        "measured_points": rules.measured_knowledge_points(self.q, values),
                    },
                )
        next_question = self.q.next_question(values, session.answers)
        if next_question is not None:
            req.trace.add(
                "deterministic",
                "questionnaire",
                req.trace.t("Question suivante choisie par les règles", "Next question chosen by the rules"),
                req.trace.t(f"{next_question.id} après {question.id}", f"{next_question.id} after {question.id}"),
                inputs={"question_id": question.id},
                outputs={"next": next_question.id},
            )
        else:
            stage = "existing_portfolio" if values.get("context.has_existing_portfolio") else "followups"
            risk = rules.risk_profile(self.q, values)
            req.trace.add(
                "deterministic",
                "questionnaire",
                req.trace.t(
                    "Risque effectif calculé : min(tolérance, capacité)",
                    "Effective risk computed: min(tolerance, capacity)",
                ),
                None,
                outputs=risk,
            )
            session.set_stage(stage, f"base:{question.id}", req.trace, reason="questions de base terminées")
        self._completeness_step(req, session)
        self._commit(req, session)
        return self._state(req, session, locale)

    def _prune_branches(self, session: ClientSession) -> None:
        """Retire les réponses de base devenues non applicables après une correction (branche abandonnée)."""
        changed = True
        while changed:
            changed = False
            values = session.values()
            for question_id in list(session.answers):
                question = self.q.question(question_id)
                if question is None or self.q.is_question_applicable(question, values):
                    continue
                del session.answers[question_id]
                fact = session.facts.get(question.field.id)
                if fact and fact.get("provenance") == f"base:{question_id}":
                    session.set_fact(question.field.id, None, f"base:{question_id}", question_id=question_id)
                changed = True

    def settings_update(self, req: Request) -> dict[str, Any]:
        session = self._client(req)
        locale = self._locale_param(req)
        has_level = "knowledge_level" in req.payload
        if locale is None and not has_level:
            raise AppError(
                "bad_request",
                pick(session.locale, "Indiquez locale ou knowledge_level.", "Provide locale or knowledge_level."),
            )
        if locale is not None:
            session.data["locale"] = locale
            req.trace.locale = locale
            req.trace.add(
                "deterministic",
                "questionnaire",
                req.trace.t("Langue changée", "Language changed"),
                locale,
                outputs={"locale": locale},
            )
        else:
            req.trace.locale = session.locale
        if has_level:
            level = req.payload.get("knowledge_level")
            if level is not None and level not in rules.LEVELS_KNOWLEDGE:
                raise AppError(
                    "bad_request",
                    pick(req.trace.locale, "knowledge_level invalide.", "Invalid knowledge_level."),
                    {"allowed": list(rules.LEVELS_KNOWLEDGE)},
                )
            session.set_fact("knowledge.level", level, "settings")
            req.trace.add(
                "deterministic",
                "questionnaire",
                req.trace.t("Niveau de connaissances fixé dans les réglages", "Knowledge level set in the settings"),
                None,
                outputs={"knowledge_level": rules.knowledge_level(self.q, session.values())},
            )
        self._commit(req, session)
        return self._state(req, session, session.locale)

    def portfolio_skip(self, req: Request) -> dict[str, Any]:
        session = self._client(req)
        req.trace.locale = session.locale
        self._expect_stage(req, session, ("existing_portfolio", "portfolio_review"))
        session.data["portfolio"] = {**(session.data.get("portfolio") or {}), "status": "skipped"}
        session.set_stage("followups", "settings", req.trace, reason="portefeuille non analysé")
        self._commit(req, session)
        return self._state(req, session, session.locale, portfolio=None)

    def portfolio_submit(self, req: Request) -> dict[str, Any]:
        session = self._client(req)
        locale = session.locale
        req.trace.locale = locale
        self._expect_stage(req, session, ("existing_portfolio", "portfolio_review"))
        with req.trace.step(
            "deterministic", "A2", req.trace.t("Entrée du portefeuille validée", "Portfolio input validated")
        ) as info:
            prepared = a2_agent.prepare_input(req.payload.get("text"), req.payload.get("files"), locale)
            info["outputs"] = {"text_chars": prepared.text_chars, "files": prepared.files, "skipped": prepared.skipped}
        turn = session.next_turn()
        values = session.values()
        outcome = a2_agent.run_a2(
            prepared,
            locale=locale,
            knowledge_level=rules.knowledge_level(self.q, values),
            trace=req.trace,
            emitter=req.emitter,
            model_factory=self.model_factory,
            model_id=self.settings.model_id,
            quote_fetcher=self.quote_fetcher,
            guardrail=self.settings.guardrail_enabled,
        )
        req.trace.add(
            "deterministic",
            "A2",
            req.trace.t(
                "Positions résolues et expositions calculées par le code",
                "Positions resolved and exposures computed by code",
            ),
            None,
            outputs={
                "positions": len(outcome.view["positions"]),
                "unresolved": len(outcome.view["unresolved"]),
                "total_value_cad": outcome.view["exposures"]["total_value_cad"],
                "flags": outcome.view["exposures"]["flags"],
            },
            sources=outcome.view["sources"],
        )
        self._write_portfolio(req, session, outcome.view, turn, prepared)
        session.data["portfolio"] = {"status": "draft", "turn": turn}
        session.set_stage("portfolio_review", f"a2:{turn}", req.trace, reason="positions proposées par A2")
        session.remember_message("A2", outcome.message, locale)
        session.index_dirty = True
        self._commit(req, session)
        return self._state(req, session, locale, message=outcome.message, portfolio=outcome.view)

    def portfolio_confirm(self, req: Request) -> dict[str, Any]:
        session = self._client(req)
        locale = session.locale
        req.trace.locale = locale
        self._expect_stage(req, session, ("portfolio_review",))
        positions = req.payload.get("positions")
        if not isinstance(positions, list):
            raise AppError("bad_request", pick(locale, "positions doit être une liste.", "positions must be a list."))
        raws = pf.positions_to_raws(positions)
        if not raws:
            raise AppError("invalid_answer", pick(locale, "Aucune position exploitable.", "No usable position."))
        with req.trace.step(
            "deterministic", "A2", req.trace.t("Expositions calculées par le code", "Exposures computed by code")
        ) as info:
            view = pf.build_view(raws, status="confirmed", quote_fetcher=self.quote_fetcher)
            info["outputs"] = {
                "positions": len(view["positions"]),
                "unresolved": len(view["unresolved"]),
                "total_value_cad": view["exposures"]["total_value_cad"],
                "flags": view["exposures"]["flags"],
            }
            info["sources"] = view["sources"]
        turn = (session.data.get("portfolio") or {}).get("turn") or session.turn
        provenance = f"a2:{turn}"
        self._write_portfolio(req, session, view, turn, None)
        session.set_fact("context.existing_portfolio_value_cad", view["exposures"]["total_value_cad"], provenance)
        session.set_fact("context.portfolio_flags", view["exposures"]["flags"], provenance)
        accounts = sorted(
            {p["account_type"] for p in view["positions"] if p.get("account_type") and p["account_type"] != "unknown"},
            key=pf.ACCOUNT_TYPES.index,
        )
        if accounts and session.values().get("constraints.account_types") is None:
            session.set_fact("constraints.account_types", accounts, provenance)
        session.data["portfolio"] = {"status": "confirmed", "turn": turn}
        session.set_stage("followups", provenance, req.trace, reason="portefeuille confirmé")
        session.index_dirty = True
        self._completeness_step(req, session)
        self._commit(req, session)
        return self._state(req, session, locale, portfolio=view)

    def _write_portfolio(
        self,
        req: Request,
        session: ClientSession,
        view: dict[str, Any],
        turn: int,
        prepared: a2_agent.PreparedInput | None,
    ) -> None:
        key = portfolio_key(session.client_id)
        existing = self.store.get(key)
        data: dict[str, Any] = {"view": view, "turn": turn}
        if existing is not None:
            previous = okf.parse(existing.text).data
            if prepared is None and previous.get("input"):
                data["input"] = previous["input"]
        if prepared is not None:
            data["input"] = {"text_chars": prepared.text_chars, "files": prepared.files, "skipped": prepared.skipped}
        confirmed = view["status"] == "confirmed"
        doc = okf.new_doc(
            type="Existing Portfolio",
            title="Portefeuille existant" if session.locale != "en" else "Existing portfolio",
            description=(
                "Positions du portefeuille existant, prix sourcés, expositions et constats calculés par le code."
            ),
            tags=["portefeuille-existant", "profil-investisseur"],
            owners=["alphaforge-a2"],
            sensitivity="client",
            generated_by="agent:A2",
            at=clock.iso(),
            status="stable" if confirmed else "draft",
            stale_after=clock.iso(clock.utcnow() + timedelta(days=30)),
            sources=view["sources"],
            data=data,
            body=render_portfolio_body(view, session.locale),
        )
        with req.trace.step("storage", "store", req.trace.t("Écriture du portefeuille", "Portfolio written"), key):
            self.store.put_text(key, okf.render(doc))

    def followup_reply(self, req: Request) -> dict[str, Any]:
        session = self._client(req)
        locale = session.locale
        req.trace.locale = locale
        self._expect_stage(req, session, ("followups", "complete"))
        answers = req.payload.get("answers") or []
        message = req.payload.get("message")
        stop = req.payload.get("stop") is True
        if not isinstance(answers, list):
            raise AppError("bad_request", pick(locale, "answers doit être une liste.", "answers must be a list."))
        if message is not None and (not isinstance(message, str) or len(message) > MAX_MESSAGE):
            raise AppError(
                "bad_request",
                pick(
                    locale,
                    f"message doit être un texte de {MAX_MESSAGE} caractères au plus.",
                    f"message must be text of at most {MAX_MESSAGE} characters.",
                ),
            )
        message = (message or "").strip() or None
        pending = {item["id"]: item for item in session.data.get("pending_questions") or []}
        validated = []
        for item in answers:
            question_id = item.get("question_id") if isinstance(item, dict) else None
            question = pending.get(question_id)
            if question is None:
                raise AppError(
                    "invalid_answer",
                    pick(locale, "Cette question n'est pas en attente.", "This question is not pending."),
                    {"question_id": question_id},
                )
            try:
                value = a1_agent.validate_pending_answer(self.q, question, item.get("value"))
            except InvalidValue as exc:
                raise AppError(
                    "invalid_answer",
                    reason_text(exc.reason, locale),
                    {"question_id": question_id, "reason": exc.reason, **exc.params},
                ) from exc
            validated.append((question, value))
        new_answers = []
        for question, value in validated:
            match = QUESTION_TURN.match(question["id"])
            provenance = f"a1:{match.group(1) if match else session.turn}"
            spec = self.q.fields.get(question.get("field") or "")
            if spec is not None and value is not None and self.q.applicable(spec.when, session.values()):
                session.set_fact(spec.id, value, provenance, question_id=question["id"])
            else:
                session.journal_answer(question["id"], value, provenance)
            session.mark_answered(question["id"], value)
            pending.pop(question["id"], None)
            new_answers.append(
                {
                    "question_id": question["id"],
                    "field": question.get("field"),
                    "value": value,
                    "prompt": question.get("prompt"),
                }
            )
        session.data["pending_questions"] = list(pending.values())
        if validated:
            req.trace.add(
                "deterministic",
                "questionnaire",
                req.trace.t("Réponses validées par les règles", "Answers validated by the rules"),
                None,
                outputs={"answers": [{"question_id": a["question_id"], "field": a["field"]} for a in new_answers]},
            )
        if stop:
            score = rules.completeness(self.q, session.values(), locale)
            if not score["ready"]:
                raise AppError(
                    "conflict",
                    pick(
                        locale,
                        "L'arrêt n'est possible qu'à partir de 70 % de complétude.",
                        "Stopping is only possible from 70% completeness.",
                    ),
                    {"score": score["score"], "threshold": score["threshold"]},
                )
            session.data["completion"] = {**(session.data.get("completion") or {}), "stopped": True}
            session.data["pending_questions"] = []
            session.set_stage("complete", "settings", req.trace, reason="l'investisseur s'arrête")
            self._completeness_step(req, session)
            self._commit(req, session)
            return self._state(req, session, locale)

        stage_before = session.stage
        turn = session.next_turn()
        if session.stage == "complete":
            session.set_stage("followups", f"a1:{turn}", req.trace, reason="nouvelle réponse après complétude")
        portfolio_view = self._portfolio(session)
        journal = load_journal_entries(self.store, session.client_id) + session.new_journal
        try:
            outcome = a1_agent.run_a1(
                self.q,
                session,
                locale=locale,
                turn=turn,
                trace=req.trace,
                emitter=req.emitter,
                model_factory=self.model_factory,
                model_id=self.settings.model_id,
                kb_search=self.kb_search,
                journal=journal,
                new_answers=new_answers,
                investor_message=message,
                portfolio=portfolio_view
                if (session.data.get("portfolio") or {}).get("status") == "confirmed"
                else None,
                guardrail=self.settings.guardrail_enabled,
            )
        except AppError:
            # Les réponses validées sont des faits : elles sont gardées même si A1 échoue. Le message libre
            # n'est pas inscrit au journal (garde-fou d'entrée non franchi ou modèle indisponible).
            if validated or session.stage != stage_before:
                self._commit(req, session)
            raise
        if message:
            session.journal_message(message, locale, f"a1:{turn}")
        for update in outcome.updates:
            session.set_fact(update["field"], update["value"], f"a1:{turn}")
        session.remember_questions(outcome.questions, turn)
        if outcome.complete:
            session.data["completion"] = {**(session.data.get("completion") or {}), "a1_complete": True}
            session.set_stage("complete", f"a1:{turn}", req.trace, reason="A1 juge le profil complet")
        session.remember_message("A1", outcome.message, locale)
        self._completeness_step(req, session)
        self._commit(req, session)
        return self._state(req, session, locale, message=outcome.message, portfolio=portfolio_view)

    def kb_list(self, req: Request) -> dict[str, Any]:
        prefix = kb.check_prefix(req.payload.get("prefix"), req.locale_hint)
        client_id = req.payload.get("client_id")
        if prefix.startswith("clients/") and client_id is not None and prefix.split("/")[1] != client_id:
            raise AppError("not_found", pick(req.locale_hint, "Base introuvable.", "Base not found."))
        return {"items": kb.list_documents(self.store, prefix)}

    def kb_get(self, req: Request) -> dict[str, Any]:
        key = kb.check_key(req.payload.get("key"), req.payload.get("client_id"), req.locale_hint)
        obj = self.store.get(key)
        if obj is None:
            raise AppError(
                "not_found", pick(req.locale_hint, "Document introuvable.", "Document not found."), {"key": key}
            )
        return {"key": key, "content": obj.text}


def render_portfolio_body(view: dict[str, Any], locale: str) -> str:
    en = locale == "en"
    exposures = view["exposures"]
    lines = [
        "# " + ("Existing portfolio" if en else "Portefeuille existant"),
        "",
        "> "
        + (
            "Fictitious portfolio, simulation only. Prices, values and exposures are computed by code."
            if en
            else "Portefeuille fictif, simulation seulement. Prix, valeurs et expositions calculés par le code."
        ),
        "",
        f"- {'Status' if en else 'Statut'} : `{view['status']}`",
        f"- {'Total value' if en else 'Valeur totale'} : {exposures['total_value_cad']} CAD",
        f"- {'USD/CAD rate' if en else 'Taux USD/CAD'} : {view['fx']['rate']}"
        f" ({view['fx']['date']}, {view['fx']['source']})",
        f"- {'Flags' if en else 'Constats'} : {', '.join(exposures['flags']) or '—'}",
        "",
        "| id | ticker | "
        + (
            "name | class | qty | price | price date | source | value CAD"
            if en
            else "nom | classe | quantité | prix | date du prix | source | valeur CAD"
        )
        + " |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for p in view["positions"]:
        name = str(p.get("name") or "").replace("|", "/")
        lines.append(
            f"| {p['id']} | {p.get('ticker') or '—'} | {name or '—'} | {p.get('asset_class')} | "
            f"{p.get('quantity') if p.get('quantity') is not None else '—'} | "
            f"{p.get('price') if p.get('price') is not None else '—'} | {p.get('price_date') or '—'} | "
            f"{p.get('price_source') or '—'} | {p.get('value_cad') if p.get('value_cad') is not None else '—'} |"
        )
    if view["unresolved"]:
        lines += ["", "## " + ("Unresolved lines" if en else "Lignes non évaluées"), ""]
        lines += [f"- {str(u['raw']).replace('|', '/')} : {u['reason']}" for u in view["unresolved"]]
    lines += [
        "",
        "## " + ("Limits" if en else "Limites"),
        "",
        "- "
        + (
            "A portfolio shows what the investor owns, not what they need (objective, horizon, reasons)."
            if en
            else "Un portefeuille montre ce que l'investisseur possède, pas ce dont il a besoin "
            "(objectif, horizon, raisons des positions)."
        ),
        "- "
        + (
            "Prices are the last close of the starter dataset (2026-11-12) or of Yahoo Finance; they are not "
            "exchange-certified."
            if en
            else "Les prix sont la dernière clôture du jeu de départ (2026-11-12) ou de "
            "Yahoo Finance; ils ne sont pas certifiés par une bourse."
        ),
        "",
    ]
    return "\n".join(lines)
