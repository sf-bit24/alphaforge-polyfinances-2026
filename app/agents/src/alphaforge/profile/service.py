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
from .questionnaire import (
    InvalidValueError,
    Questionnaire,
    QuestionSpec,
    band_brief,
    default_questionnaire,
    labeled,
    reason_text,
)
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


# Messages des erreurs que l'investisseur ne peut pas causer lui-même (demande mal formée, service en panne).
BAD_REQUEST_FR = "Votre demande n'a pas pu être lue. Rechargez la page, puis réessayez."
BAD_REQUEST_EN = "Your request could not be read. Reload the page, then try again."
UNAVAILABLE_FR = "Le service ne répond pas pour l'instant : réessayez dans un instant."
UNAVAILABLE_EN = "The service is not answering right now: try again in a moment."
PROFILE_UNREADABLE_FR = "Votre profil sur cet appareil n'a pas pu être lu. Rechargez la page, puis réessayez."
PROFILE_UNREADABLE_EN = "Your profile on this device could not be read. Reload the page, then try again."


def _answers_param(payload: dict[str, Any], locale: str) -> list[Any]:
    answers = payload.get("answers") or []
    if not isinstance(answers, list):
        raise AppError("bad_request", pick(locale, BAD_REQUEST_FR, BAD_REQUEST_EN))
    return answers


def _message_param(payload: dict[str, Any], locale: str) -> str | None:
    message = payload.get("message")
    if message is not None and (not isinstance(message, str) or len(message) > MAX_MESSAGE):
        raise AppError(
            "bad_request",
            pick(
                locale,
                f"Votre message est trop long : {MAX_MESSAGE} caractères au plus.",
                f"Your message is too long: {MAX_MESSAGE} characters at most.",
            ),
        )
    return (message or "").strip() or None


class _PendingQuestions:
    """Questions en attente d'une session, le temps de lire les réponses de l'investisseur.

    Les tables des tranches (nombres et tranches) et les champs visés par les confirmations vivent hors des
    questions : une question répondue les quitte toutes à la fois, et ``save`` réécrit ce qui reste dans la session.
    """

    def __init__(self, questionnaire: Questionnaire, session: ClientSession):
        self.questionnaire = questionnaire
        self.session = session
        self.questions = {item["id"]: item for item in session.data.get("pending_questions") or []}
        self.choices = dict(session.data.get("pending_choices") or {})
        # Absent d'une session écrite avant les tranches : le fait est alors écrit sans sa tranche.
        self.bands = dict(session.data.get("pending_bands") or {})
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
                    pick(
                        locale,
                        "Cette question n'attend plus de réponse. Rechargez la page pour voir les questions à jour.",
                        "This question no longer needs an answer. Reload the page to see the current questions.",
                    ),
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
        bands = self.bands.pop(question["id"], None) or {}
        option = band = None
        if table and isinstance(value, str) and value in table:
            # Tranche choisie : le code écrit sa valeur numérique, garde l'identifiant au journal et la tranche
            # avec le fait.
            option, value = value, table[value]
            band = bands.get(option)
        if spec is not None and value is not None and self.questionnaire.applicable(spec.when, session.values()):
            session.set_fact(spec.id, value, provenance, question_id=question["id"], option=option, band=band)
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
            # A1 lit la tranche choisie : la valeur n'en est que le chiffre prudent.
            **({"band": band_brief(band, session.locale)} if band else {}),
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
        self.session.data["pending_bands"] = self.bands
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
            return error_response(release, AppError("bad_request", BAD_REQUEST_FR))
        action = payload.get("action")
        request = Request(
            action=str(action), payload=payload, trace=Trace(self._initial_locale(payload), emitter), emitter=emitter
        )
        if not isinstance(action, str) or not action:
            return error_response(
                release,
                AppError("bad_request", pick(request.locale_hint, BAD_REQUEST_FR, BAD_REQUEST_EN)),
            )
        handler = self.actions.get(action)
        if handler is None:
            return error_response(
                release,
                AppError(
                    "unknown_action",
                    pick(request.locale_hint, BAD_REQUEST_FR, BAD_REQUEST_EN),
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
                        "Votre profil a été modifié entre-temps, peut-être dans un autre onglet. "
                        "Rechargez la page, puis réessayez.",
                        "Your profile was changed in the meantime, perhaps in another tab. "
                        "Reload the page, then try again.",
                    ),
                ),
            )
        except Exception:
            logger.exception("profile action failed: %s", request.action)
            return error_response(
                release,
                AppError("internal", pick(request.locale_hint, UNAVAILABLE_FR, UNAVAILABLE_EN)),
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
                pick(
                    request.locale_hint,
                    "Cette langue n'est pas offerte : choisissez le français ou l'anglais.",
                    "This language is not offered: choose French or English.",
                ),
                {"locale": value},
            )
        return value

    def _client(self, request: Request) -> ClientSession:
        client_id = request.payload.get("client_id")
        if not is_client_id(client_id):
            raise AppError(
                "bad_request",
                pick(request.trace.locale, PROFILE_UNREADABLE_FR, PROFILE_UNREADABLE_EN),
            )
        session = ClientSession.load(self.store, client_id)
        if session is None:
            raise AppError(
                "not_found",
                pick(
                    request.trace.locale,
                    "Nous ne trouvons pas votre profil. Rechargez la page pour en commencer un nouveau.",
                    "We cannot find your profile. Reload the page to start a new one.",
                ),
                {"client_id": client_id},
            )
        return session

    def _expect_stage(self, request: Request, session: ClientSession, stages: tuple[str, ...]) -> None:
        if session.stage not in stages:
            raise AppError(
                "conflict",
                pick(
                    request.trace.locale,
                    "Cette action n'est pas possible à cette étape du profil. "
                    "Rechargez la page pour voir où vous en êtes.",
                    "This action is not possible at this step of your profile. Reload the page to see where you are.",
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
        request.trace.add(
            "storage", "store", request.trace.t("Étapes enregistrées", "Steps saved"), None, inputs={"key": key}
        )
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
            request.trace.t("Complétude calculée selon des règles fixes", "Completeness computed with fixed rules"),
            request.trace.t(
                f"{round(score['score'] * 100)} % du profil rempli; à partir de "
                f"{round(self.questionnaire.threshold * 100)} %, vous pouvez passer à la suite.",
                f"{round(score['score'] * 100)}% of the profile filled in; from "
                f"{round(self.questionnaire.threshold * 100)}%, you can move on.",
            ),
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
                raise AppError("bad_request", pick(locale, PROFILE_UNREADABLE_FR, PROFILE_UNREADABLE_EN))
            existing = ClientSession.load(self.store, client_id)
            if existing is not None:
                request.trace.add(
                    "storage",
                    "store",
                    request.trace.t("Profil retrouvé", "Profile found"),
                    None,
                    outputs={"client_id": client_id, "stage": existing.stage},
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
            request.trace.t("Profil créé", "Profile created"),
            None,
            outputs={
                "client_id": client_id,
                "questionnaire_version": self.questionnaire.version,
                "stage": session.stage,
            },
        )
        first = self.questionnaire.next_question(session.values(), session.answers)
        request.trace.add(
            "deterministic",
            "questionnaire",
            request.trace.t(
                "Première question choisie selon des règles fixes", "First question chosen with fixed rules"
            ),
            None,
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
        session.set_fact(
            question.field.id,
            value,
            f"base:{question.id}",
            question_id=question.id,
            option=option,
            band=question.option_band(option) if option is not None else None,
        )
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
            raise AppError(
                "bad_request",
                pick(locale, "Choisissez une réponse avant de continuer.", "Choose an answer before continuing."),
            )
        question = self.questionnaire.question(question_id) if isinstance(question_id, str) else None
        if question is None:
            raise AppError(
                "invalid_answer",
                pick(
                    locale,
                    "Cette question n'existe plus. Rechargez la page pour voir les questions à jour.",
                    "This question no longer exists. Reload the page to see the current questions.",
                ),
                {"question_id": question_id},
            )
        if not self.questionnaire.is_question_applicable(question, session.values()):
            raise AppError(
                "invalid_answer",
                pick(
                    locale,
                    "Cette question ne s'applique pas à votre profil.",
                    "This question does not apply to your profile.",
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
            trace.t("Réponse vérifiée selon des règles fixes", "Answer checked with fixed rules"),
            question.field.label_text(trace.locale),
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
            trace.t(
                "Votre propre évaluation, sans dépasser d'un niveau ce que montrent vos réponses.",
                "Your own assessment, at most one level above what your answers show.",
            ),
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
                trace.t("Question suivante choisie selon des règles fixes", "Next question chosen with fixed rules"),
                trace.t(
                    f"Prochain sujet : {next_question.field.label_text(trace.locale)}",
                    f"Next topic: {next_question.field.label_text(trace.locale)}",
                ),
                inputs={"question_id": question.id},
                outputs={"next": next_question.id},
            )
            return
        stage = "existing_portfolio" if values.get("context.has_existing_portfolio") else "followups"
        risk = rules.risk_profile(self.questionnaire, values)
        trace.add(
            "deterministic",
            "questionnaire",
            trace.t("Risque effectif calculé", "Effective risk computed"),
            trace.t(
                "Le plus prudent entre votre tolérance au risque et votre capacité à en prendre.",
                "The more cautious of your risk tolerance and your capacity to take risk.",
            ),
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
                pick(
                    session.locale,
                    "Choisissez une langue ou un niveau de connaissances.",
                    "Choose a language or a knowledge level.",
                ),
            )
        if locale is not None:
            session.data["locale"] = locale
            request.trace.locale = locale
            request.trace.add(
                "deterministic",
                "questionnaire",
                request.trace.t("Langue changée", "Language changed"),
                request.trace.t("Français", "English"),
                outputs={"locale": locale},
            )
        else:
            request.trace.locale = session.locale
        if has_level:
            level = request.payload.get("knowledge_level")
            if level is not None and level not in rules.LEVELS_KNOWLEDGE:
                raise AppError(
                    "bad_request",
                    pick(
                        request.trace.locale,
                        "Ce niveau de connaissances n'existe pas : choisissez-en un dans la liste.",
                        "This knowledge level does not exist: choose one from the list.",
                    ),
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
            "deterministic", "A2", request.trace.t("Portefeuille reçu et vérifié", "Portfolio received and checked")
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
                "Positions reconnues et expositions calculées selon des règles fixes",
                "Positions identified and exposures computed with fixed rules",
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
            raise AppError("bad_request", pick(locale, BAD_REQUEST_FR, BAD_REQUEST_EN))
        raws = positions_to_raws(positions)
        if not raws:
            raise AppError(
                "invalid_answer",
                pick(
                    locale,
                    "Aucune position utilisable : ajoutez au moins une ligne avec un nom ou un symbole.",
                    "No usable position: add at least one line with a name or a symbol.",
                ),
            )
        with request.trace.step(
            "deterministic",
            "A2",
            request.trace.t("Expositions calculées selon des règles fixes", "Exposures computed with fixed rules"),
        ) as info:
            view = build_view(raws, status="confirmed", quote_fetcher=self.quote_fetcher, locale=locale)
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
                "Positions of your existing portfolio, with their prices and sources, and the exposures and findings "
                "computed with fixed rules."
                if session.locale == "en"
                else "Positions de votre portefeuille existant, avec leurs prix et leurs sources, et les expositions "
                "et constats calculés selon des règles fixes."
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
            "storage", "store", request.trace.t("Portefeuille enregistré", "Portfolio saved"), inputs={"key": key}
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
                request.trace.t("Réponses vérifiées selon des règles fixes", "Answers checked with fixed rules"),
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
                    "Vous pourrez vous arrêter quand votre profil sera rempli à 70 %. "
                    "Répondez encore à quelques questions.",
                    "You can stop once your profile is 70% complete. Answer a few more questions.",
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
            # Les réponses validées sont des faits : elles sont gardées même si A1 échoue, avec le passage de
            # complete à followups qu'elles entraînent. Sans réponse validée, rien n'est enregistré, étape comprise :
            # un message refusé (garde-fou) ou un modèle indisponible ne rouvre pas un profil complet (#77). Le
            # message libre n'est jamais inscrit au journal dans ces cas.
            if new_answers:
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
                request.trace.t("Confirmations demandées", "Confirmations requested"),
                request.trace.t(
                    "Yan a compris ces réponses dans votre message : confirmez-les d'un clic pour qu'elles soient "
                    "retenues.",
                    "Yan understood these answers from your message: confirm them with one click so they are kept.",
                ),
                outputs={
                    "questions": [{"id": question_id, "field": field_id} for question_id, field_id in targets.items()]
                },
            )
        session.remember_questions(
            questions,
            turn,
            choices=outcome.choices,
            confirmations=targets,
            reasons=outcome.reasons,
            bands=outcome.bands,
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
                request.trace.t("Notes de Yan non écrites", "Yan's notes not written"),
                request.trace.t("Votre profil reste complet.", "Your profile stays complete."),
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
            raise AppError(
                "not_found",
                pick(request.locale_hint, "Ces documents sont introuvables.", "These documents cannot be found."),
            )
        return {"items": kb.list_documents(self.store, prefix)}

    def kb_get(self, request: Request) -> dict[str, Any]:
        key = kb.check_key(request.payload.get("key"), request.payload.get("client_id"), request.locale_hint)
        stored = self.store.get(key)
        if stored is None:
            raise AppError(
                "not_found", pick(request.locale_hint, "Document introuvable.", "Document not found."), {"key": key}
            )
        return {"key": key, "content": stored.text}


# Le document du portefeuille existant nomme les constats et les catégories comme l'écran (français, anglais).
FLAG_LABELS = {
    "concentration_single_position": ("Concentration sur une position", "Single-position concentration"),
    "home_bias_canada": ("Biais domestique (Canada)", "Home bias (Canada)"),
    "concentration_sector": ("Concentration sectorielle", "Sector concentration"),
    "crypto_exposure_high": ("Cryptoactifs élevés", "High crypto-assets"),
    "cash_heavy": ("Beaucoup d'encaisse", "Cash heavy"),
    "few_holdings": ("Peu de positions", "Few holdings"),
    "unvalued_positions": ("Lignes non évaluées", "Unvalued lines"),
}
ASSET_CLASS_LABELS = {
    "equity": ("Action", "Stock"),
    "etf_equity": ("FNB d'actions", "Equity ETF"),
    "etf_bond": ("FNB d'obligations", "Bond ETF"),
    "etf_commodity": ("FNB de matières premières", "Commodity ETF"),
    "bond": ("Obligation", "Bond"),
    "cash": ("Encaisse", "Cash"),
    "crypto": ("Cryptoactif", "Crypto-asset"),
    "fund": ("Fonds", "Fund"),
    "other": ("Autre", "Other"),
}


def _label(labels: dict[str, tuple[str, str]], key: Any, *, en: bool) -> str:
    pair = labels.get(str(key))
    return (pair[1] if en else pair[0]) if pair else str(key)


def _summary_lines(view: dict[str, Any], *, en: bool) -> list[str]:
    """Titre, avertissement, synthèse et en-tête du tableau des positions; le séparateur suit la langue."""
    exposures = view["exposures"]
    locale = "en" if en else "fr"
    status = {"draft": ("To be confirmed", "À confirmer"), "confirmed": ("Confirmed", "Confirmé")}.get(view["status"])
    status = (status[0] if en else status[1]) if status else str(view["status"])
    total = f"{exposures['total_value_cad']} CAD"
    flags = ", ".join(_label(FLAG_LABELS, flag, en=en) for flag in exposures["flags"])
    return [
        "# " + ("Existing portfolio" if en else "Portefeuille existant"),
        "",
        "> "
        + (
            "Fictitious portfolio, simulation only. Prices, values and exposures are computed with fixed rules."
            if en
            else "Portefeuille fictif, simulation seulement. "
            "Prix, valeurs et expositions calculés selon des règles fixes."
        ),
        "",
        f"- {labeled('Status' if en else 'Statut', status, locale)}",
        f"- {labeled('Total value' if en else 'Valeur totale', total, locale)}",
        f"- {labeled('USD/CAD rate' if en else 'Taux USD/CAD', str(view['fx']['rate']), locale)}"
        f" ({view['fx']['date']}, {'Bank of Canada' if en else 'Banque du Canada'})",
        f"- {labeled('Flags' if en else 'Constats', flags or '—', locale)}",
        "",
        "| "
        + (
            "symbol | name | class | qty | price | price date | source | value CAD"
            if en
            else "symbole | nom | classe | quantité | prix | date du prix | source | valeur CAD"
        )
        + " |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]


def _position_row(position: dict[str, Any], source_titles: dict[str, str], *, en: bool) -> str:
    """Ligne d'une position; sa source de prix est citée par son titre, jamais par sa clé."""
    name = str(position.get("name") or "").replace("|", "/")
    source = position.get("price_source")
    source_text = str(source_titles.get(source) or source or "—").replace("|", "/")
    asset_class = _label(ASSET_CLASS_LABELS, position.get("asset_class"), en=en)
    return (
        f"| {position.get('ticker') or '—'} | {name or '—'} | {asset_class} | "
        f"{position.get('quantity') if position.get('quantity') is not None else '—'} | "
        f"{position.get('price') if position.get('price') is not None else '—'} | "
        f"{position.get('price_date') or '—'} | "
        f"{source_text} | "
        f"{position.get('value_cad') if position.get('value_cad') is not None else '—'} |"
    )


def _unresolved_lines(view: dict[str, Any], *, en: bool) -> list[str]:
    if not view["unresolved"]:
        return []
    locale = "en" if en else "fr"
    return [
        "",
        "## " + ("Unresolved lines" if en else "Lignes non évaluées"),
        "",
        *(
            f"- {labeled(str(line['raw']).replace('|', '/'), str(line['reason']), locale)}"
            for line in view["unresolved"]
        ),
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
            "Prices are the last close in our market data (2026-11-12) or on Yahoo Finance; they are not "
            "exchange-certified."
            if en
            else "Les prix sont la dernière clôture de nos données de marché (2026-11-12) ou de "
            "Yahoo Finance; ils ne sont pas certifiés par une bourse."
        ),
        "",
    ]


def render_portfolio_body(view: dict[str, Any], locale: str) -> str:
    en = locale == "en"
    lines = _summary_lines(view, en=en)
    titles = {source.get("resource"): source.get("title") for source in view.get("sources") or []}
    lines += [_position_row(position, titles, en=en) for position in view["positions"]]
    lines += _unresolved_lines(view, en=en)
    lines += _limit_lines(en=en)
    return "\n".join(lines)
