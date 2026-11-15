"""Runtimes ``router`` (A0), ``expert`` (E1 à E7) et ``researcher`` (CONTRACTS.md, section 11).

Même schéma que les collecteurs (section 4) : la tâche est acceptée aussitôt, exécutée en arrière-plan comme tâche
asynchrone de ``BedrockAgentCoreApp`` (``/ping`` à ``HealthyBusy``), puis un marqueur est écrit, que la tâche
réussisse ou non. Step Functions sonde les marqueurs des experts et d'A0; un expert sonde ceux de ses chercheurs.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from .. import clock, starter
from ..agentkit import ModelFactory, bedrock_model_factory
from ..collect import fetchers, staging
from ..config import Settings
from ..errors import AppError, error_response, ok_response
from ..store import Store
from ..trace import Trace
from . import expert as expert_mod
from . import researcher as researcher_mod
from . import router as router_mod
from .launcher import AgentCoreLauncher, Launcher, LocalLauncher, resolve_runtime_arn
from .packs import DEPTH_CAPS, SUBJECTS

logger = logging.getLogger("alphaforge.research")
ROLE_ACTIONS = {"researcher": ("research",), "expert": ("research",), "router": ("route", "compose")}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_TICKERS = 40
MAX_QUESTION = 800


def _since(value: Any) -> str:
    if value is None:
        return (clock.today() - timedelta(days=7)).isoformat()
    if not isinstance(value, str) or not DATE.match(value):
        raise AppError("bad_request", "since doit suivre AAAA-MM-JJ.", {"since": value})
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise AppError("bad_request", "since n'est pas une date valide.", {"since": value}) from exc
    if parsed > clock.today():
        raise AppError("bad_request", "since ne peut pas être dans le futur.", {"since": value})
    if parsed < clock.today() - timedelta(days=366):
        raise AppError("bad_request", "since remonte à un an au plus.", {"since": value})
    return value


def _tickers(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return default
    if not isinstance(value, list) or len(value) > MAX_TICKERS:
        raise AppError("bad_request", f"issuers doit être une liste de {MAX_TICKERS} symboles au plus.")
    cleaned = []
    for raw in value:
        symbol = raw.strip().upper() if isinstance(raw, str) else ""
        if not fetchers.SYMBOL.match(symbol):
            raise AppError("bad_request", f"Symbole invalide : {raw!r}.", {"ticker": raw})
        cleaned.append(symbol)
    return list(dict.fromkeys(cleaned))


def _themes(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AppError("bad_request", "themes doit être une liste.")
    return [" ".join(str(t).split())[:40] for t in value if isinstance(t, str) and t.strip()][:8]


def _as_of(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or clock.parse_datetime(value) is None:
        raise AppError("bad_request", "as_of doit être une date ou un horodatage ISO.", {"as_of": value})
    return value


def _depth(value: Any) -> str:
    depth = value or "standard"
    if depth not in DEPTH_CAPS:
        raise AppError("bad_request", f"depth doit être parmi {list(DEPTH_CAPS)}.")
    return depth


def _question(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise AppError("bad_request", "question est requise.")
    return text[:MAX_QUESTION]


def _researcher_job(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        brief = researcher_mod.parse_brief(payload)
    except researcher_mod.ResearchError as exc:
        raise AppError("bad_request", str(exc)) from exc
    return {"brief": brief, "marker": f"{brief.prefix}_done.json"}


def _researcher_cap(payload: dict[str, Any], depth: str) -> int:
    """Plafond de chercheurs de l'expert : celui de la profondeur, abaissé par ``max_researchers``."""
    cap = DEPTH_CAPS[depth]
    max_researchers = payload.get("max_researchers")
    if max_researchers is not None:
        if not isinstance(max_researchers, int) or max_researchers < 1:
            raise AppError("bad_request", "max_researchers doit être un entier positif.")
        cap = min(cap, max_researchers)
    return cap


def _expert_job(payload: dict[str, Any], run_id: str) -> dict[str, Any]:
    code = payload.get("subject")
    if code not in SUBJECTS:
        raise AppError("bad_request", f"subject doit être parmi {list(SUBJECTS)}.")
    mode = payload.get("mode") or "sweep"
    if mode not in ("sweep", "question"):
        raise AppError("bad_request", "mode doit valoir sweep ou question.")
    depth = _depth(payload.get("depth") or ("quick" if mode == "sweep" else "standard"))
    default_issuers = list(starter.universe()) if mode == "sweep" else []
    cap = _researcher_cap(payload, depth)
    job = expert_mod.ExpertJob(
        run_id=run_id,
        subject=SUBJECTS[code],
        mode=mode,
        question=_question(payload.get("question")) if mode == "question" else None,
        sub_question=(" ".join(str(payload.get("sub_question") or "").split())[:400] or None),
        issuers=_tickers(payload.get("issuers"), default_issuers),
        themes=_themes(payload.get("themes")),
        since=_since(payload.get("since")),
        as_of=_as_of(payload.get("as_of")),
        depth=depth,
        max_researchers=cap,
    )
    return {"expert": job, "marker": f"{job.prefix}_done.json"}


def _router_job(payload: dict[str, Any], run_id: str) -> dict[str, Any]:
    if payload["action"] == "route":
        job = {
            "run_id": run_id,
            "question": _question(payload.get("question")),
            "issuers": _tickers(payload.get("issuers"), []),
            "themes": _themes(payload.get("themes")),
            "as_of": _as_of(payload.get("as_of")),
            "depth": _depth(payload.get("depth")),
            "since": _since(payload.get("since")),
        }
        return {"route": job, "marker": f"staging/{run_id}/router/_routed.json"}
    return {"marker": f"staging/{run_id}/router/_composed.json"}


class ResearchService:
    def __init__(  # noqa: PLR0913 - signature publique gelée (tests, server.build_service, PR #43)
        self,
        settings: Settings,
        store: Store,
        app: Any | None = None,
        *,
        model_factory: ModelFactory | None = None,
        researcher_model_factory: ModelFactory | None = None,
        launcher: Launcher | None = None,
        knowledge: Any = None,
        expert_budget_seconds: float = 1500,
    ):
        if settings.role not in ROLE_ACTIONS:
            raise ValueError(f"not a research role: {settings.role}")
        self.settings = settings
        self.store = store
        self.app = app
        self.model_factory = model_factory or bedrock_model_factory(settings)
        researcher_model = settings.researcher_model_id or settings.model_id
        self.researcher_model_id = researcher_model
        self.researcher_model_factory = researcher_model_factory or (
            bedrock_model_factory(replace(settings, model_id=researcher_model))
            if model_factory is None
            else model_factory
        )
        self._launcher = launcher
        self.knowledge = knowledge
        self.expert_budget_seconds = expert_budget_seconds
        self._running: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    @property
    def role(self) -> str:
        return self.settings.role

    # ------------------------------------------------------------------ dépendances
    def launcher(self) -> Launcher:
        if self._launcher is None:
            arn = self.settings.researcher_arn
            if not arn and self.settings.researcher_name:
                arn = resolve_runtime_arn(self.settings.researcher_name, self.settings.region)
            if arn:
                self._launcher = AgentCoreLauncher(self.store, runtime_arn=arn, region=self.settings.region)
            else:
                local_settings = replace(self.settings, role="researcher")

                def factory() -> ResearchService:
                    return ResearchService(
                        local_settings,
                        self.store,
                        None,
                        model_factory=self.researcher_model_factory,
                        researcher_model_factory=self.researcher_model_factory,
                    )

                self._launcher = LocalLauncher(self.store, factory)
        return self._launcher

    def knowledge_search(self) -> Any:
        if self.knowledge is None and self.settings.kb_id:
            from ..profile.kb import KnowledgeSearch

            self.knowledge = KnowledgeSearch(self.settings)
        return self.knowledge

    # ------------------------------------------------------------------ requêtes
    def handle(self, payload: Any) -> dict[str, Any]:
        release = self.settings.release
        try:
            if not isinstance(payload, dict):
                raise AppError("bad_request", "Le corps doit être un objet JSON.")
            action = payload.get("action")
            if not isinstance(action, str) or not action:
                raise AppError("bad_request", "action est requise.")
            if action == "health":
                return ok_response(release, role=self.role, env=self.settings.env)
            if action not in ROLE_ACTIONS[self.role]:
                raise AppError(
                    "unknown_action",
                    f"Action inconnue pour le rôle {self.role} : {action}.",
                    {"action": action, "expected": list(ROLE_ACTIONS[self.role])},
                )
            return ok_response(release, **self.accept(payload))
        except AppError as exc:
            return error_response(release, exc)
        except Exception:
            logger.exception("research request failed")
            return error_response(release, AppError("internal", "Erreur interne."))

    def _job(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not staging.RUN_ID.match(run_id):
            raise AppError("bad_request", "run_id doit suivre ^[A-Za-z0-9_-]{1,64}$.", {"run_id": run_id})
        head = {"action": payload["action"], "run_id": run_id}
        if self.role == "researcher":
            return {**head, **_researcher_job(payload)}
        if self.role == "expert":
            return {**head, **_expert_job(payload, run_id)}
        return {**head, **_router_job(payload, run_id)}

    def accept(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = self._job(payload)
        marker = job["marker"]
        response = {"accepted": True, "run_id": job["run_id"], "marker": marker}
        with self._lock:
            running = self._running.get(marker)
            if running is not None and running.is_alive():
                return {**response, "already_running": True}
            existing = self.store.get_json(marker)
            if existing is not None and existing.get("status") == "ok":
                return {**response, "already_done": True}
            task_id = self.app.add_async_task(f"{self.role}:{marker}", {"run_id": job["run_id"]}) if self.app else None
            thread = threading.Thread(
                target=self._background, args=(job, task_id), name=f"alphaforge-{self.role}", daemon=True
            )
            self._running[marker] = thread
            thread.start()
        return response

    def run_job(self, job: dict[str, Any], trace: Trace) -> dict[str, Any]:
        if self.role == "researcher":
            return researcher_mod.research(
                brief=job["brief"],
                store=self.store,
                trace=trace,
                model_factory=self.researcher_model_factory,
                model_id=self.researcher_model_id,
            )
        if self.role == "expert":
            run = expert_mod.ExpertRun(
                job=job["expert"],
                store=self.store,
                launcher=self.launcher(),
                knowledge=self.knowledge_search(),
                deadline=time.monotonic() + self.expert_budget_seconds,
            )
            return expert_mod.run_expert(
                run, trace=trace, model_factory=self.model_factory, model_id=self.settings.model_id
            )
        common = {
            "store": self.store,
            "trace": trace,
            "model_factory": self.model_factory,
            "model_id": self.settings.model_id,
        }
        if job["action"] == "route":
            return router_mod.route(job=job["route"], **common)
        return router_mod.compose(run_id=job["run_id"], **common)

    def _background(self, job: dict[str, Any], task_id: int | None) -> None:
        started_at = clock.iso()
        trace = Trace("fr")
        try:
            try:
                result = self.run_job(job, trace)
                marker = {"status": "ok", "error": None, **result}
            except AppError as exc:
                marker = {"status": "error", "error": f"{exc.code}: {exc.message}"}
            except Exception as exc:
                logger.exception("%s job %s failed", self.role, job["marker"])
                marker = {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
            document = {
                "status": marker["status"],
                "role": self.role,
                "action": job["action"],
                "run_id": job["run_id"],
                **{key: value for key, value in marker.items() if key != "status"},
                "started_at": started_at,
                "finished_at": clock.iso(),
                "release": self.settings.release,
                "trace": trace.steps[-80:],
            }
            try:
                self.store.put_json(job["marker"], document)
            except Exception:
                logger.exception("could not write marker %s", job["marker"])
        finally:
            if self.app is not None and task_id is not None:
                self.app.complete_async_task(task_id)
            with self._lock:
                self._running.pop(job["marker"], None)

    def wait(self, marker: str, timeout: float | None = None) -> None:
        """Attend la fin d'une tâche (tests et exécution locale)."""
        thread = self._running.get(marker)
        if thread is not None:
            thread.join(timeout)
