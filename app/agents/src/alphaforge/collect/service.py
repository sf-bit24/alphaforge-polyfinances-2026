"""Runtimes de collecte ``press`` (A4), ``data`` (A5) et ``supervisor`` (A6) (CONTRACTS.md, sections 4 et 6).

La tâche est acceptée aussitôt, puis exécutée en arrière-plan comme tâche asynchrone de ``BedrockAgentCoreApp``
(``add_async_task`` / ``complete_async_task``) : ``/ping`` répond ``HealthyBusy`` tant qu'elle tourne. À la fin,
le marqueur ``staging/<run_id>/<rôle>/_done.json`` est écrit, que la tâche réussisse ou non.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import date, timedelta
from typing import Any

from .. import clock, starter
from ..agentkit import ModelFactory, bedrock_model_factory
from ..config import Settings
from ..errors import AppError, error_response, ok_response
from ..store import Store
from ..trace import Trace
from . import data as data_collector
from . import fetchers, staging
from . import press as press_collector
from . import supervisor as supervisor_collector

logger = logging.getLogger("alphaforge.collect")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ROLE_ACTIONS = {"press": "collect", "data": "collect", "supervisor": "curate"}
MAX_TICKERS = 40


class CollectorService:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        app: Any | None = None,
        *,
        model_factory: ModelFactory | None = None,
        budget_seconds: float = 240,
    ):
        if settings.role not in ROLE_ACTIONS:
            raise ValueError(f"not a collector role: {settings.role}")
        self.settings = settings
        self.store = store
        self.app = app
        self.model_factory = model_factory or bedrock_model_factory(settings)
        self.budget_seconds = budget_seconds
        self._running: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    @property
    def role(self) -> str:
        return self.settings.role

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
            if action != ROLE_ACTIONS[self.role]:
                raise AppError(
                    "unknown_action",
                    f"Action inconnue pour le rôle {self.role} : {action}.",
                    {"action": action, "expected": ROLE_ACTIONS[self.role]},
                )
            return ok_response(release, **self.accept(payload))
        except AppError as exc:
            return error_response(release, exc)
        except Exception:
            logger.exception("collector request failed")
            return error_response(release, AppError("internal", "Erreur interne."))

    def _job(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not staging.RUN_ID.match(run_id):
            raise AppError("bad_request", "run_id doit suivre ^[A-Za-z0-9_-]{1,64}$.", {"run_id": run_id})
        job: dict[str, Any] = {"run_id": run_id}
        if self.role == "supervisor":
            return job
        since = payload.get("since")
        if since is None:
            since = (clock.today() - timedelta(days=7)).isoformat()
        elif not isinstance(since, str) or not DATE.match(since):
            raise AppError("bad_request", "since doit suivre AAAA-MM-JJ.", {"since": since})
        else:
            try:
                parsed = date.fromisoformat(since)
            except ValueError as exc:
                raise AppError("bad_request", "since n'est pas une date valide.", {"since": since}) from exc
            if parsed > clock.today():
                raise AppError("bad_request", "since ne peut pas être dans le futur.", {"since": since})
            if parsed < clock.today() - timedelta(days=60):
                raise AppError("bad_request", "since remonte à 60 jours au plus.", {"since": since})
        tickers = payload.get("tickers")
        if tickers is None:
            tickers = list(starter.universe())
        elif not isinstance(tickers, list) or not tickers or len(tickers) > MAX_TICKERS:
            raise AppError("bad_request", f"tickers doit être une liste de 1 à {MAX_TICKERS} symboles.")
        else:
            cleaned = []
            for raw in tickers:
                symbol = raw.strip().upper() if isinstance(raw, str) else ""
                if not fetchers.SYMBOL.match(symbol):
                    raise AppError("bad_request", f"Symbole invalide : {raw!r}.", {"ticker": raw})
                cleaned.append(symbol)
            tickers = list(dict.fromkeys(cleaned))
        job.update(since=since, tickers=tickers)
        return job

    def accept(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = self._job(payload)
        run_id = job["run_id"]
        marker = staging.marker_key(run_id, self.role)
        response = {"accepted": True, "run_id": run_id, "marker": marker}
        with self._lock:
            running = self._running.get(run_id)
            if running is not None and running.is_alive():
                return {**response, "already_running": True}
            existing = self.store.get_json(marker)
            if existing is not None and existing.get("status") == "ok":
                return {**response, "already_done": True}
            task_id = self.app.add_async_task(f"{self.role}:{run_id}", {"run_id": run_id}) if self.app else None
            thread = threading.Thread(
                target=self._background, args=(job, task_id), name=f"alphaforge-{self.role}", daemon=True
            )
            self._running[run_id] = thread
            thread.start()
        return response

    def run_job(self, job: dict[str, Any], trace: Trace) -> dict[str, Any]:
        common = {
            "store": self.store,
            "trace": trace,
            "model_factory": self.model_factory,
            "model_id": self.settings.model_id,
            "budget_seconds": self.budget_seconds,
        }
        if self.role == "press":
            return press_collector.collect(run_id=job["run_id"], since=job["since"], tickers=job["tickers"], **common)
        if self.role == "data":
            return data_collector.collect(run_id=job["run_id"], since=job["since"], tickers=job["tickers"], **common)
        return supervisor_collector.curate(run_id=job["run_id"], **common)

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
                logger.exception("%s run %s failed", self.role, job["run_id"])
                marker = {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
            if self.role == "supervisor":
                marker.setdefault("written", [])
                marker.setdefault("rejected", [])
            else:
                marker.setdefault("items", 0)
                marker.setdefault("keys", [])
            document = {
                "status": marker["status"],
                "role": self.role,
                "run_id": job["run_id"],
                **{k: v for k, v in marker.items() if k not in ("status",)},
                "started_at": started_at,
                "finished_at": clock.iso(),
                "release": self.settings.release,
                "trace": trace.steps[-80:],
            }
            try:
                self.store.put_json(staging.marker_key(job["run_id"], self.role), document)
            except Exception:
                logger.exception("could not write marker for %s", job["run_id"])
        finally:
            if self.app is not None and task_id is not None:
                self.app.complete_async_task(task_id)
            with self._lock:
                self._running.pop(job["run_id"], None)

    def wait(self, run_id: str, timeout: float | None = None) -> None:
        """Attend la fin d'un passage (tests et exécution locale)."""
        thread = self._running.get(run_id)
        if thread is not None:
            thread.join(timeout)
