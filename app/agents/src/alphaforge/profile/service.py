"""Runtime ``profile`` : actions de CONTRACTS.md 3.2, réponses ``ClientState`` et streaming SSE (3.4).

Les actions déterministes (``session.*``, ``base.answer``, ``portfolio.confirm``, ``portfolio.skip``,
``settings.update``, ``profile.get``, ``kb.*``) n'appellent aucun modèle. ``portfolio.submit`` appelle A2 et
``followup.reply`` appelle A1. À la fin du questionnaire (passage à ``complete``, y compris par ``stop: true``),
le service invoque aussi A1 avec son skill de base du client (``brain.run_brain``) : ``client-brain-init``, puis
``client-brain-update`` quand les faits ou les skills ont changé.

Knowledge Base du client (``client_kb``) : le magasin est enveloppé pour noter les documents ``.md`` écrits; à la fin
de chaque action (``_commit``, ou ``session.resume``, ``profile.get`` et ``session.start`` d'une base existante), un
rapprochement crée la base au premier passage, fait avancer sa création et envoie les documents. Désactivée en local.
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
from . import brain, kb, rules
from .agent_runner import AgentRunner
from .client_kb import ClientKnowledgeBases
from .portfolio import ACCOUNT_TYPES, QuoteFetcher, build_view, positions_to_raws
from .questionnaire import InvalidValueError, Questionnaire, QuestionSpec, default_questionnaire, reason_text
from .state import ClientSession, is_client_id, load_journal_entries, portfolio_key, trace_key
from .views import client_state

logger = logging.getLogger("alphaforge.profile")
LOCALES = ("fr", "en")
STREAMABLE = frozenset({"portfolio.submit", "followup.reply"})
MAX_MESSAGE = 4000
QUESTION_TURN = re.compile(r"^(?:a1|fb|cf)_(\d+)_\d+$")
_DONE = object()


@dataclass
class Request:
    action: str
    payload: dict[str, Any]
    trace: Trace
    emitter: Emitter | None
    # ``client_kb`` de la réponse, rendu par le rapprochement de la Knowledge Base du client.
    client_kb: dict[str, Any] | None = None

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


def _answers_param(payload: dict[str, Any], locale: str) -> list[Any]:
    answers = payload.get("answers") or []
    if not isinstance(answers, list):
        raise AppError("bad_request", pick(locale, "answers doit être une liste.", "answers must be a list."))
    return answers


def _message_param(payload: dict[str, Any], locale: str) -> str | None:
    message = payload.get("message")
    if message is not None and (not isinstance(message, str) or len(message) > MAX_MESSAGE):
        raise AppError(
            "bad_request",
            pick(
                locale,
                f"message doit être un texte de {MAX_MESSAGE} caractères au plus.",
                f"message must be text of at most {MAX_MESSAGE} characters.",
            ),
        )
    return (message or "").strip() or None


class _PendingQuestions:
    """Questions en attente d'une session, le temps de lire les réponses de l'investisseur.

    Les tables des tranches et les champs visés par les confirmations vivent hors des questions : une question
    répondue quitte les trois à la fois, et ``save`` réécrit ce qui reste dans la session.
    """

    def __init__(self, questionnaire: Questionnaire, session: ClientSession):
        self.questionnaire = questionnaire
        self.session = session
        self.questions = {item["id"]: item for item in session.data.get("pending_questions") or []}
        self.choices = dict(session.data.get("pending_choices") or {})
        self.confirmations = dict(session.data.get("pending_confirmations") or {})

    def validate(self, answers: list[Any], locale: str) -> list[tuple[dict[str, Any], Any]]:
        """Couples (question, valeur validée); une seule réponse refusée et rien n'est écrit."""
        validated = []
        for item in answers:
            question_id = item.get("question_id") if isinstance(item, dict) else None
            question = self.questions.get(question_id)
            if question is None:
                raise AppError(
                    "invalid_answer",
                    pick(locale, "Cette question n'est pas en attente.", "This question is not pending."),
                    {"question_id": question_id},
                )
            try:
                value = a1_agent.validate_pending_answer(self.questionnaire, question, item.get("value"))
            except InvalidValueError as exc:
                raise AppError(
                    "invalid_answer",
                    reason_text(exc.reason, locale),
                    {"question_id": question_id, "reason": exc.reason, **exc.params},
                ) from exc
            validated.append((question, value))
        return validated

    def answer(self, question: dict[str, Any], value: Any) -> dict[str, Any]:
        """Écrit une réponse validée, avec la provenance du tour qui a posé la question; rend ce que A1 en lira."""
        match = QUESTION_TURN.match(question["id"])
        provenance = f"a1:{match.group(1) if match else self.session.turn}"
        if question["id"].startswith("cf_"):
            # Confirmation d'une valeur tirée d'un texte libre : traitée avant la branche générique, qui
            # écrirait sinon le booléen dans le champ visé.
            return self._answer_confirmation(question, value, provenance)
        return self._answer_question(question, value, provenance)

    def _answer_confirmation(self, question: dict[str, Any], value: Any, provenance: str) -> dict[str, Any]:
        field_id = self.confirmations.pop(question["id"], None)
        self._confirm(field_id, value, provenance, question["id"])
        self.session.mark_answered(question["id"], value)
        self.questions.pop(question["id"], None)
        return {
            "question_id": question["id"],
            "field": field_id,
            "kind": "confirmation",
            "value": value,
            "prompt": question.get("prompt"),
        }

    def _answer_question(self, question: dict[str, Any], value: Any, provenance: str) -> dict[str, Any]:
        session = self.session
        spec = self.questionnaire.fields.get(question.get("field") or "")
        table = self.choices.pop(question["id"], None)
        option = None
        if table and isinstance(value, str) and value in table:
            # Tranche choisie : le code écrit sa valeur numérique et garde l'identifiant au journal.
            option, value = value, table[value]
        if spec is not None and value is not None and self.questionnaire.applicable(spec.when, session.values()):
            session.set_fact(spec.id, value, provenance, question_id=question["id"], option=option)
        else:
            session.journal_answer(question["id"], value, provenance)
        session.mark_answered(question["id"], option if option is not None else value)
        self.questions.pop(question["id"], None)
        return {
            "question_id": question["id"],
            "field": question.get("field"),
            "kind": question.get("kind"),
            "value": value,
            **({"option": option} if option is not None else {}),
            "prompt": question.get("prompt"),
        }

    def _confirm(self, field_id: str | None, value: Any, provenance: str, question_id: str) -> None:
        """« Oui » retire ``confirmed: false`` du fait; « Non » retire la valeur (le journal garde ``previous``)."""
        session = self.session
        fact = session.facts.get(field_id) if field_id else None
        spec = self.questionnaire.fields.get(field_id or "")
        if fact is None or spec is None or fact.get("confirmed") is not False:
            # La valeur a changé depuis (clic sur le même champ) : la réponse est seulement inscrite au journal.
            session.journal_answer(question_id, value, provenance)
        elif value is True and self.questionnaire.applicable(spec.when, session.values()):
            session.confirm_fact(field_id, provenance, question_id=question_id)
        else:
            # « Non », ou un champ qui ne s'applique plus (sa condition a été refusée) : la valeur est retirée.
            session.reject_fact(field_id, provenance, question_id=question_id)

    def save(self) -> None:
        self.session.data["pending_questions"] = list(self.questions.values())
        self.session.data["pending_choices"] = self.choices
        self.session.data["pending_confirmations"] = self.confirmations


def _view_summary(view: dict[str, Any]) -> dict[str, Any]:
    """Ce que la trace montre d'un portefeuille évalué par le code."""
    return {
        "positions": len(view["positions"]),
        "unresolved": len(view["unresolved"]),
        "total_value_cad": view["exposures"]["total_value_cad"],
        "flags": view["exposures"]["flags"],
    }


def _account_types(view: dict[str, Any]) -> list[str]:
    """Types de compte connus des positions, dans l'ordre du questionnaire."""
    return sorted(
        {
            position["account_type"]
            for position in view["positions"]
            if position.get("account_type") and position["account_type"] != "unknown"
        },
        key=ACCOUNT_TYPES.index,
    )


class ProfileService:
    def __init__(  # noqa: PLR0913 - constructeur public gelé : server.py et les tests passent ces options par mot-clé
        self,
        settings: Settings,
        store: Store,
        *,
        questionnaire: Questionnaire | None = None,
        model_factory: ModelFactory | None = None,
        quote_fetcher: QuoteFetcher | None = fetch_yahoo_chart,
        kb_search: kb.KnowledgeSearch | None = None,
        write_client_brain: bool = True,
        client_kb: ClientKnowledgeBases | None = None,
    ):
        self.settings = settings
        # Knowledge Base de chaque client : le magasin n'est enveloppé que si elle est configurée (jamais en local).
        self.client_kb = client_kb or ClientKnowledgeBases.from_settings(settings, store, can_create=True)
        self.store = self.client_kb.wrap(store)
        self.questionnaire = questionnaire or default_questionnaire()
        self.model_factory = model_factory or bedrock_model_factory(settings)
        self.quote_fetcher = quote_fetcher
        self.kb_search = kb_search or kb.KnowledgeSearch(settings)
        # À la fin du questionnaire, A1 écrit la base du client avec son skill (désactivable pour les tests).
        self.write_client_brain = write_client_brain
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
        request = Request(
            action=str(action), payload=payload, trace=Trace(self._initial_locale(payload), emitter), emitter=emitter
        )
        if not isinstance(action, str) or not action:
            return error_response(
                release,
                AppError("bad_request", pick(request.locale_hint, "action est requise.", "action is required.")),
            )
        handler = self.actions.get(action)
        if handler is None:
            return error_response(
                release,
                AppError(
                    "unknown_action",
                    pick(request.locale_hint, f"Action inconnue : {action}.", f"Unknown action: {action}."),
                    {"action": action},
                ),
            )
        return self._respond(handler, request)

    def _respond(self, handler: Callable[[Request], dict[str, Any]], request: Request) -> dict[str, Any]:
        """Réponse de l'action : l'état qu'elle rend, ou son erreur au format du contrat."""
        release = self.settings.release
        try:
            return ok_response(release, **handler(request))
        except AppError as exc:
            return error_response(release, exc)
        except ConflictError:
            return error_response(
                release,
                AppError(
                    "conflict",
                    pick(
                        request.locale_hint,
                        "Le profil a été modifié par une autre requête. Rechargez puis réessayez.",
                        "The profile was changed by another request. Reload and try again.",
                    ),
                ),
            )
        except Exception:
            logger.exception("profile action failed: %s", request.action)
            return error_response(
                release,
                AppError("internal", pick(request.locale_hint, "Erreur interne.", "Internal error.")),
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

    def _locale_param(self, request: Request) -> str | None:
        value = request.payload.get("locale")
        if value is None:
            return None
        if value not in LOCALES:
            raise AppError(
                "bad_request",
                pick(request.locale_hint, "locale doit valoir fr ou en.", "locale must be fr or en."),
                {"locale": value},
            )
        return value

    def _client(self, request: Request) -> ClientSession:
        client_id = request.payload.get("client_id")
        if not is_client_id(client_id):
            raise AppError(
                "bad_request",
                pick(request.trace.locale, "client_id doit être un UUID v4.", "client_id must be a UUID v4."),
            )
        session = ClientSession.load(self.store, client_id)
        if session is None:
            raise AppError(
                "not_found",
                pick(request.trace.locale, "Client introuvable.", "Client not found."),
                {"client_id": client_id},
            )
        return session

    def _expect_stage(self, request: Request, session: ClientSession, stages: tuple[str, ...]) -> None:
        if session.stage not in stages:
            raise AppError(
                "conflict",
                pick(
                    request.trace.locale,
                    f"Action impossible à l'étape {session.stage}.",
                    f"Action not allowed at stage {session.stage}.",
                ),
                {"stage": session.stage, "expected": list(stages)},
            )

    def _portfolio(self, session: ClientSession) -> dict[str, Any] | None:
        if (session.data.get("portfolio") or {}).get("status") not in ("draft", "confirmed"):
            return None
        stored = self.store.get(portfolio_key(session.client_id))
        if stored is None:
            return None
        return okf.parse(stored.text).data.get("view")

    def _state(
        self,
        request: Request,
        session: ClientSession,
        locale: str,
        *,
        message: str | None = None,
        portfolio: Any = "load",
    ) -> dict[str, Any]:
        """``ClientState`` de la réponse; ``portfolio="load"`` relit le portefeuille enregistré."""
        view = self._portfolio(session) if portfolio == "load" else portfolio
        return client_state(
            self.questionnaire,
            session,
            locale=locale,
            trace=request.trace,
            message=message,
            portfolio=view,
            client_kb=request.client_kb,
        )

    def _sync_client_kb(self, request: Request, client_id: str) -> None:
        """Rapprochement de la Knowledge Base du client : jamais une erreur pour l'investisseur (voir client_kb)."""
        request.client_kb = self.client_kb.sync(client_id, request.trace, create=True)

    def _commit(self, request: Request, session: ClientSession) -> None:
        session.commit(self.store, self.questionnaire, request.trace)
        # Après les écritures OKF de l'action, avant la trace : la trace enregistrée montre aussi l'indexation.
        self._sync_client_kb(request, session.client_id)
        key = trace_key(session.client_id, request.action)
        request.trace.add("storage", "store", request.trace.t("Trace enregistrée", "Trace saved"), key)
        self.store.put_json(
            key,
            {
                "action": request.action,
                "at": clock.iso(),
                "release": self.settings.release,
                "client_id": session.client_id,
                "stage": session.stage,
                "steps": request.trace.steps,
            },
        )

    def _completeness_step(self, request: Request, session: ClientSession) -> None:
        score = rules.completeness(self.questionnaire, session.values(), request.trace.locale)
        request.trace.add(
            "deterministic",
            "completeness",
            request.trace.t("Complétude calculée par le code", "Completeness computed by code"),
            f"{round(score['score'] * 100)} % / {round(self.questionnaire.threshold * 100)} %",
            outputs={"score": score["score"], "ready": score["ready"], "missing": len(score["missing"])},
        )

    def _agent_runner(self, request: Request) -> AgentRunner:
        return AgentRunner(
            model_factory=self.model_factory,
            model_id=self.settings.model_id,
            guardrail=self.settings.guardrail_enabled,
            trace=request.trace,
            emitter=request.emitter,
        )

    def _journal(self, session: ClientSession) -> list[dict[str, Any]]:
        """Journal récent du client : les entrées enregistrées, puis celles de cette requête."""
        return load_journal_entries(self.store, session.client_id) + session.new_journal

    def _last_message(self, session: ClientSession, locale: str) -> str | None:
        last = session.data.get("last_message") or {}
        return last.get("text") if last.get("locale") == locale else None

    # ------------------------------------------------------------------ actions
    def health(self, request: Request) -> dict[str, Any]:
        return {"role": self.settings.role, "env": self.settings.env}

    def session_start(self, request: Request) -> dict[str, Any]:
        locale = self._locale_param(request) or "fr"
        request.trace.locale = locale
        client_id = request.payload.get("client_id")
        if client_id is not None:
            if not is_client_id(client_id):
                raise AppError(
                    "bad_request", pick(locale, "client_id doit être un UUID v4.", "client_id must be a UUID v4.")
                )
            existing = ClientSession.load(self.store, client_id)
            if existing is not None:
                request.trace.add(
                    "storage",
                    "store",
                    request.trace.t("Base du client existante", "Existing client base"),
                    client_id,
                    outputs={"stage": existing.stage},
                )
                self._sync_client_kb(request, client_id)
                return self._state(request, existing, locale, message=self._last_message(existing, locale))
        else:
            client_id = str(uuid.uuid4())
        session = ClientSession.create(client_id, locale, self.questionnaire)
        session.journal_created()
        request.trace.add(
            "deterministic",
            "questionnaire",
            request.trace.t("Base du client créée", "Client base created"),
            client_id,
            outputs={"questionnaire_version": self.questionnaire.version, "stage": session.stage},
        )
        first = self.questionnaire.next_question(session.values(), session.answers)
        request.trace.add(
            "deterministic",
            "questionnaire",
            request.trace.t("Première question choisie par les règles", "First question chosen by the rules"),
            first.id if first else None,
            outputs={"next": first.id if first else None},
        )
        self._commit(request, session)
        return self._state(request, session, locale, portfolio=None)

    def session_resume(self, request: Request) -> dict[str, Any]:
        session = self._client(request)
        locale = self._locale_param(request) or session.locale
        request.trace.locale = locale
        self._sync_client_kb(request, session.client_id)
        return self._state(request, session, locale, message=self._last_message(session, locale))

    def profile_get(self, request: Request) -> dict[str, Any]:
        session = self._client(request)
        locale = self._locale_param(request) or session.locale
        request.trace.locale = locale
        self._sync_client_kb(request, session.client_id)
        documents = [
            {"key": item["key"], "title": item["title"]}
            for item in kb.list_documents(self.store, f"clients/{session.client_id}/")
        ]
        return client_state(
            self.questionnaire,
            session,
            locale=locale,
            trace=request.trace,
            message=self._last_message(session, locale),
            portfolio=self._portfolio(session),
            documents=documents,
            client_kb=request.client_kb,
        )

    def base_answer(self, request: Request) -> dict[str, Any]:
        session = self._client(request)
        locale = session.locale
        request.trace.locale = locale
        self._expect_stage(request, session, ("base_questions",))
        question = self._base_question(request, session)
        value, option = self._validate_base_answer(request, question, locale)
        session.record_answer(question.id, option if option is not None else value)
        session.set_fact(question.field.id, value, f"base:{question.id}", question_id=question.id, option=option)
        self._prune_branches(session)
        values = session.values()
        if question.field.dimension == "knowledge":
            self._knowledge_level_step(request, values)
        self._advance_base_questions(request, session, question, values)
        self._completeness_step(request, session)
        self._commit(request, session)
        return self._state(request, session, locale)

    def _base_question(self, request: Request, session: ClientSession) -> QuestionSpec:
        """Question de base visée par la réponse. Refuse une réponse sans valeur, une question inconnue ou une
        question qui ne s'applique pas à ce profil."""
        locale = session.locale
        question_id = request.payload.get("question_id")
        if "value" not in request.payload:
            raise AppError("bad_request", pick(locale, "value est requise.", "value is required."))
        question = self.questionnaire.question(question_id) if isinstance(question_id, str) else None
        if question is None:
            raise AppError(
                "invalid_answer", pick(locale, "Question inconnue.", "Unknown question."), {"question_id": question_id}
            )
        if not self.questionnaire.is_question_applicable(question, session.values()):
            raise AppError(
                "invalid_answer",
                pick(
                    locale,
                    "Cette question ne s'applique pas à ce profil.",
                    "This question does not apply to this profile.",
                ),
                {"question_id": question_id},
            )
        return question

    def _validate_base_answer(self, request: Request, question: QuestionSpec, locale: str) -> tuple[Any, str | None]:
        """Valeur validée de la réponse et, pour une tranche, son identifiant (la valeur est alors le nombre de la
        tranche). L'étape de trace est inscrite même quand la réponse est refusée."""
        trace = request.trace
        with trace.step(
            "deterministic",
            "questionnaire",
            trace.t("Réponse validée par les règles", "Answer validated by the rules"),
            question.id,
            inputs={"question_id": question.id, "kind": question.kind},
        ) as info:
            try:
                value = self.questionnaire.validate_answer(question, request.payload.get("value"))
            except InvalidValueError as exc:
                info["title"] = trace.t("Réponse refusée", "Answer rejected")
                info["outputs"] = {"reason": exc.reason}
                raise AppError(
                    "invalid_answer",
                    reason_text(exc.reason, locale),
                    {"question_id": question.id, "reason": exc.reason, **exc.params},
                ) from exc
            option = None
            if question.numeric_choice:
                # Tranche choisie : le code écrit sa valeur numérique et garde l'identifiant au journal.
                option, value = value, question.option_number(value)
            info["outputs"] = {"field": question.field.id, "value": value, **({"option": option} if option else {})}
        return value, option

    def _knowledge_level_step(self, request: Request, values: dict[str, Any]) -> None:
        level = rules.knowledge_level(self.questionnaire, values)
        if not level:
            return
        trace = request.trace
        trace.add(
            "deterministic",
            "questionnaire",
            trace.t("Niveau de connaissances calculé", "Knowledge level computed"),
            trace.t("min(auto-évaluation, niveau mesuré + 1)", "min(self-assessment, measured level + 1)"),
            outputs={
                "knowledge_level": level,
                "measured_points": rules.measured_knowledge_points(self.questionnaire, values),
            },
        )

    def _advance_base_questions(
        self, request: Request, session: ClientSession, question: QuestionSpec, values: dict[str, Any]
    ) -> None:
        """Question suivante choisie par les règles; après la dernière, le risque effectif et l'étape suivante."""
        trace = request.trace
        next_question = self.questionnaire.next_question(values, session.answers)
        if next_question is not None:
            trace.add(
                "deterministic",
                "questionnaire",
                trace.t("Question suivante choisie par les règles", "Next question chosen by the rules"),
                trace.t(f"{next_question.id} après {question.id}", f"{next_question.id} after {question.id}"),
                inputs={"question_id": question.id},
                outputs={"next": next_question.id},
            )
            return
        stage = "existing_portfolio" if values.get("context.has_existing_portfolio") else "followups"
        risk = rules.risk_profile(self.questionnaire, values)
        trace.add(
            "deterministic",
            "questionnaire",
            trace.t(
                "Risque effectif calculé : min(tolérance, capacité)",
                "Effective risk computed: min(tolerance, capacity)",
            ),
            None,
            outputs=risk,
        )
        session.set_stage(stage, f"base:{question.id}", trace, reason="questions de base terminées")

    def _prune_branches(self, session: ClientSession) -> None:
        """Retire les réponses de base devenues non applicables après une correction (branche abandonnée)."""
        changed = True
        while changed:
            changed = False
            values = session.values()
            for question_id in list(session.answers):
                question = self.questionnaire.question(question_id)
                if question is None or self.questionnaire.is_question_applicable(question, values):
                    continue
                del session.answers[question_id]
                fact = session.facts.get(question.field.id)
                if fact and fact.get("provenance") == f"base:{question_id}":
                    session.set_fact(question.field.id, None, f"base:{question_id}", question_id=question_id)
                changed = True

    def settings_update(self, request: Request) -> dict[str, Any]:
        session = self._client(request)
        locale = self._locale_param(request)
        has_level = "knowledge_level" in request.payload
        if locale is None and not has_level:
            raise AppError(
                "bad_request",
                pick(session.locale, "Indiquez locale ou knowledge_level.", "Provide locale or knowledge_level."),
            )
        if locale is not None:
            session.data["locale"] = locale
            request.trace.locale = locale
            request.trace.add(
                "deterministic",
                "questionnaire",
                request.trace.t("Langue changée", "Language changed"),
                locale,
                outputs={"locale": locale},
            )
        else:
            request.trace.locale = session.locale
        if has_level:
            level = request.payload.get("knowledge_level")
            if level is not None and level not in rules.LEVELS_KNOWLEDGE:
                raise AppError(
                    "bad_request",
                    pick(request.trace.locale, "knowledge_level invalide.", "Invalid knowledge_level."),
                    {"allowed": list(rules.LEVELS_KNOWLEDGE)},
                )
            session.set_fact("knowledge.level", level, "settings")
            request.trace.add(
                "deterministic",
                "questionnaire",
                request.trace.t(
                    "Niveau de connaissances fixé dans les réglages", "Knowledge level set in the settings"
                ),
                None,
                outputs={"knowledge_level": rules.knowledge_level(self.questionnaire, session.values())},
            )
        self._commit(request, session)
        return self._state(request, session, session.locale)

    def portfolio_skip(self, request: Request) -> dict[str, Any]:
        session = self._client(request)
        request.trace.locale = session.locale
        self._expect_stage(request, session, ("existing_portfolio", "portfolio_review"))
        session.data["portfolio"] = {**(session.data.get("portfolio") or {}), "status": "skipped"}
        session.set_stage("followups", "settings", request.trace, reason="portefeuille non analysé")
        self._commit(request, session)
        return self._state(request, session, session.locale, portfolio=None)

    def portfolio_submit(self, request: Request) -> dict[str, Any]:
        session = self._client(request)
        locale = session.locale
        request.trace.locale = locale
        self._expect_stage(request, session, ("existing_portfolio", "portfolio_review"))
        with request.trace.step(
            "deterministic", "A2", request.trace.t("Entrée du portefeuille validée", "Portfolio input validated")
        ) as info:
            prepared = a2_agent.prepare_input(request.payload.get("text"), request.payload.get("files"), locale)
            info["outputs"] = {"text_chars": prepared.text_chars, "files": prepared.files, "skipped": prepared.skipped}
        turn = session.next_turn()
        values = session.values()
        outcome = a2_agent.run_a2(
            prepared,
            locale=locale,
            knowledge_level=rules.knowledge_level(self.questionnaire, values),
            quote_fetcher=self.quote_fetcher,
            runner=self._agent_runner(request),
        )
        request.trace.add(
            "deterministic",
            "A2",
            request.trace.t(
                "Positions résolues et expositions calculées par le code",
                "Positions resolved and exposures computed by code",
            ),
            None,
            outputs=_view_summary(outcome.view),
            sources=outcome.view["sources"],
        )
        self._write_portfolio(request, session, outcome.view, turn, prepared)
        session.data["portfolio"] = {"status": "draft", "turn": turn}
        session.set_stage("portfolio_review", f"a2:{turn}", request.trace, reason="positions proposées par A2")
        session.remember_message("A2", outcome.message, locale)
        session.index_dirty = True
        self._commit(request, session)
        return self._state(request, session, locale, message=outcome.message, portfolio=outcome.view)

    def portfolio_confirm(self, request: Request) -> dict[str, Any]:
        session = self._client(request)
        locale = session.locale
        request.trace.locale = locale
        self._expect_stage(request, session, ("portfolio_review",))
        positions = request.payload.get("positions")
        if not isinstance(positions, list):
            raise AppError("bad_request", pick(locale, "positions doit être une liste.", "positions must be a list."))
        raws = positions_to_raws(positions)
        if not raws:
            raise AppError("invalid_answer", pick(locale, "Aucune position exploitable.", "No usable position."))
        with request.trace.step(
            "deterministic", "A2", request.trace.t("Expositions calculées par le code", "Exposures computed by code")
        ) as info:
            view = build_view(raws, status="confirmed", quote_fetcher=self.quote_fetcher)
            info["outputs"] = _view_summary(view)
            info["sources"] = view["sources"]
        turn = (session.data.get("portfolio") or {}).get("turn") or session.turn
        provenance = f"a2:{turn}"
        self._write_portfolio(request, session, view, turn, None)
        session.set_fact("context.existing_portfolio_value_cad", view["exposures"]["total_value_cad"], provenance)
        session.set_fact("context.portfolio_flags", view["exposures"]["flags"], provenance)
        accounts = _account_types(view)
        if accounts and session.values().get("constraints.account_types") is None:
            session.set_fact("constraints.account_types", accounts, provenance)
        session.data["portfolio"] = {"status": "confirmed", "turn": turn}
        session.set_stage("followups", provenance, request.trace, reason="portefeuille confirmé")
        session.index_dirty = True
        self._completeness_step(request, session)
        self._commit(request, session)
        return self._state(request, session, locale, portfolio=view)

    def _write_portfolio(
        self,
        request: Request,
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
        with request.trace.step(
            "storage", "store", request.trace.t("Écriture du portefeuille", "Portfolio written"), key
        ):
            self.store.put_text(key, okf.render(doc))

    def followup_reply(self, request: Request) -> dict[str, Any]:
        session = self._client(request)
        locale = session.locale
        request.trace.locale = locale
        self._expect_stage(request, session, ("followups", "complete"))
        answers = _answers_param(request.payload, locale)
        message = _message_param(request.payload, locale)
        new_answers = self._record_answers(request, session, answers)
        if request.payload.get("stop") is True:
            return self._stop_followups(request, session)
        return self._ask_followups(request, session, message, new_answers)

    def _record_answers(self, request: Request, session: ClientSession, answers: list[Any]) -> list[dict[str, Any]]:
        """Valide toutes les réponses aux questions en attente, puis les écrit; rend les réponses de ce tour."""
        pending = _PendingQuestions(self.questionnaire, session)
        validated = pending.validate(answers, session.locale)
        new_answers = [pending.answer(question, value) for question, value in validated]
        pending.save()
        self._drop_orphans(session, f"a1:{session.turn}" if session.turn else "settings")
        if new_answers:
            request.trace.add(
                "deterministic",
                "questionnaire",
                request.trace.t("Réponses validées par les règles", "Answers validated by the rules"),
                None,
                outputs={
                    "answers": [
                        {"question_id": answer["question_id"], "field": answer["field"]} for answer in new_answers
                    ]
                },
            )
        return new_answers

    def _stop_followups(self, request: Request, session: ClientSession) -> dict[str, Any]:
        """L'investisseur s'arrête : permis seulement quand la complétude atteint le seuil."""
        locale = session.locale
        score = rules.completeness(self.questionnaire, session.values(), locale)
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
        session.clear_pending()
        session.set_stage("complete", "settings", request.trace, reason="l'investisseur s'arrête")
        self._client_brain(request, session)
        self._completeness_step(request, session)
        self._commit(request, session)
        return self._state(request, session, locale)

    def _ask_followups(
        self, request: Request, session: ClientSession, message: str | None, new_answers: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Tour de relance : A1 lit le message et les réponses de ce tour, puis pose ses questions."""
        locale = session.locale
        stage_before = session.stage
        turn = session.next_turn()
        if session.stage == "complete":
            session.set_stage("followups", f"a1:{turn}", request.trace, reason="nouvelle réponse après complétude")
        portfolio_view = self._portfolio(session)
        is_confirmed = (session.data.get("portfolio") or {}).get("status") == "confirmed"
        turn_input = a1_agent.TurnInput(
            turn=turn,
            locale=locale,
            investor_message=message,
            new_answers=new_answers,
            journal=self._journal(session),
            portfolio=portfolio_view if is_confirmed else None,
            # Recherche dans la Knowledge Base de ce client seulement (identifiant lu dans kb.json, jamais par A1).
            client_search=self.client_kb.searcher(session.client_id),
        )
        try:
            outcome = a1_agent.run_a1(
                self.questionnaire, session, turn_input, kb_search=self.kb_search, runner=self._agent_runner(request)
            )
        except AppError:
            # Les réponses validées sont des faits : elles sont gardées même si A1 échoue. Le message libre
            # n'est pas inscrit au journal (garde-fou d'entrée non franchi ou modèle indisponible).
            if new_answers or session.stage != stage_before:
                self._commit(request, session)
            raise
        if message:
            session.journal_message(message, locale, f"a1:{turn}")
        self._remember_turn(request, session, outcome, turn)
        if outcome.complete:
            session.data["completion"] = {**(session.data.get("completion") or {}), "a1_complete": True}
            session.set_stage("complete", f"a1:{turn}", request.trace, reason="A1 juge le profil complet")
            self._client_brain(request, session)
        session.remember_message("A1", outcome.message, locale)
        self._completeness_step(request, session)
        self._commit(request, session)
        return self._state(request, session, locale, message=outcome.message, portfolio=portfolio_view)

    def _remember_turn(self, request: Request, session: ClientSession, outcome: a1_agent.A1Outcome, turn: int) -> None:
        """Écrit ce que A1 a tiré du texte libre (à confirmer) et garde les questions envoyées à l'investisseur."""
        for update in outcome.updates:
            # Valeur tirée d'un texte libre : écrite non confirmée, puis confirmée par un clic.
            session.set_fact(update["field"], update["value"], f"a1:{turn}", confirmed=False)
        confirmations, targets = a1_agent.confirmation_questions(
            self.questionnaire, session, turn=turn, locale=session.locale
        )
        questions = confirmations + outcome.questions
        if confirmations:
            request.trace.add(
                "deterministic",
                "questionnaire",
                request.trace.t("Confirmations demandées par le code", "Confirmations asked by code"),
                request.trace.t(
                    "Valeurs tirées d'un texte libre, retenues après un clic de l'investisseur.",
                    "Values taken from free text, kept once the investor confirms them.",
                ),
                outputs={
                    "questions": [{"id": question_id, "field": field_id} for question_id, field_id in targets.items()]
                },
            )
        session.remember_questions(
            questions, turn, choices=outcome.choices, confirmations=targets, reasons=outcome.reasons
        )

    def _client_brain(self, request: Request, session: ClientSession) -> None:
        """Fin du questionnaire : A1 écrit ou met à jour la base du client avec son skill. Un échec n'empêche
        pas le profil de passer à ``complete`` : il est seulement inscrit à la trace."""
        if not self.write_client_brain:
            return
        try:
            brain.run_brain(
                self.questionnaire,
                session,
                self.store,
                journal=self._journal(session),
                runner=self._agent_runner(request),
            )
        except Exception as exc:  # modèle, garde-fou ou magasin : le profil reste complet
            if not isinstance(exc, AppError):
                logger.exception("client brain failed")
            request.trace.add(
                "deterministic",
                "A1",
                request.trace.t("Base du client non écrite", "Client base not written"),
                getattr(exc, "code", type(exc).__name__),
                outputs={"error": getattr(exc, "code", type(exc).__name__)},
            )

    def _drop_orphans(self, session: ClientSession, provenance: str) -> None:
        """Retire une valeur à confirmer dont le champ ne peut plus s'appliquer, même si les autres valeurs à
        confirmer l'étaient (par exemple une part de retraits après un « non » sur le besoin de liquidité)."""
        waiting = session.unconfirmed()
        hopeful = {**session.values(), **{field_id: fact["value"] for field_id, fact in waiting.items()}}
        for field_id in waiting:
            spec = self.questionnaire.fields.get(field_id)
            if spec is not None and not self.questionnaire.applicable(spec.when, hopeful):
                session.reject_fact(field_id, provenance)

    def kb_list(self, request: Request) -> dict[str, Any]:
        prefix = kb.check_prefix(request.payload.get("prefix"), request.locale_hint)
        client_id = request.payload.get("client_id")
        if prefix.startswith("clients/") and client_id is not None and prefix.split("/")[1] != client_id:
            raise AppError("not_found", pick(request.locale_hint, "Base introuvable.", "Base not found."))
        return {"items": kb.list_documents(self.store, prefix)}

    def kb_get(self, request: Request) -> dict[str, Any]:
        key = kb.check_key(request.payload.get("key"), request.payload.get("client_id"), request.locale_hint)
        stored = self.store.get(key)
        if stored is None:
            raise AppError(
                "not_found", pick(request.locale_hint, "Document introuvable.", "Document not found."), {"key": key}
            )
        return {"key": key, "content": stored.text}


def _summary_lines(view: dict[str, Any], *, en: bool) -> list[str]:
    """Titre, avertissement, synthèse et en-tête du tableau des positions."""
    exposures = view["exposures"]
    return [
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


def _position_row(position: dict[str, Any]) -> str:
    name = str(position.get("name") or "").replace("|", "/")
    return (
        f"| {position['id']} | {position.get('ticker') or '—'} | {name or '—'} | {position.get('asset_class')} | "
        f"{position.get('quantity') if position.get('quantity') is not None else '—'} | "
        f"{position.get('price') if position.get('price') is not None else '—'} | "
        f"{position.get('price_date') or '—'} | "
        f"{position.get('price_source') or '—'} | "
        f"{position.get('value_cad') if position.get('value_cad') is not None else '—'} |"
    )


def _unresolved_lines(view: dict[str, Any], *, en: bool) -> list[str]:
    if not view["unresolved"]:
        return []
    return [
        "",
        "## " + ("Unresolved lines" if en else "Lignes non évaluées"),
        "",
        *(f"- {str(line['raw']).replace('|', '/')} : {line['reason']}" for line in view["unresolved"]),
    ]


def _limit_lines(*, en: bool) -> list[str]:
    return [
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


def render_portfolio_body(view: dict[str, Any], locale: str) -> str:
    en = locale == "en"
    lines = _summary_lines(view, en=en)
    lines += [_position_row(position) for position in view["positions"]]
    lines += _unresolved_lines(view, en=en)
    lines += _limit_lines(en=en)
    return "\n".join(lines)
