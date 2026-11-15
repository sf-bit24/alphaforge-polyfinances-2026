"""Lancement des chercheurs par un expert : une session AgentCore par chercheur, ou un fil local en développement.

- ``AgentCoreLauncher`` appelle ``InvokeAgentRuntime`` sur le runtime ``researcher`` (ARN dans
  ``ALPHAFORGE_RESEARCHER_ARN``), avec un ``runtimeSessionId`` propre à chaque chercheur : chaque chercheur tourne
  dans sa microVM. Le runtime accepte la mission aussitôt et travaille en arrière-plan; l'expert sonde ensuite le
  marqueur ``staging/<run_id>/researchers/<sujet>-<rk>/_done.json``, comme Step Functions le fait pour A4 et A5.
- ``LocalLauncher`` exécute la même mission dans un fil du processus (magasin local, tests, poste de travail).

Le code de l'expert, pas le modèle, décide si un lancement est permis (plafonds de ``packs``).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..store import Store

logger = logging.getLogger("alphaforge.research")
POLL_SECONDS = 5.0
MAX_PARALLEL = 6


def session_id(run_id: str, subject: str, researcher: str) -> str:
    """Identifiant de session AgentCore (33 caractères au moins), stable pour un chercheur d'une exécution."""
    return f"{run_id}-{subject}-{researcher}".ljust(48, "0")[:100]


def marker_key(run_id: str, subject: str, researcher: str) -> str:
    return f"staging/{run_id}/researchers/{subject}-{researcher}/_done.json"


class Launcher(ABC):
    def __init__(self, store: Store, *, poll_seconds: float = POLL_SECONDS):
        self.store = store
        self.poll_seconds = poll_seconds

    @abstractmethod
    def start(self, brief: dict[str, Any]) -> None:
        """Lance une mission; lève une exception si le lancement est refusé."""

    def run(self, briefs: list[dict[str, Any]], timeout: float) -> list[dict[str, Any]]:
        """Lance les missions en parallèle, puis attend leurs marqueurs; rend un résultat par mission."""
        results: list[dict[str, Any]] = [{} for _ in briefs]

        def launch(index: int) -> None:
            brief = briefs[index]
            try:
                self.start(brief)
                results[index] = {"brief": brief, "launched": True}
            except Exception as exc:
                logger.warning("researcher launch failed: %s", type(exc).__name__)
                results[index] = {"brief": brief, "launched": False, "error": f"lancement refusé : {exc}"[:300]}

        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, max(1, len(briefs)))) as pool:
            list(pool.map(launch, range(len(briefs))))
        deadline = time.monotonic() + timeout
        pending = {i for i, result in enumerate(results) if result.get("launched")}
        while pending and time.monotonic() < deadline:
            for index in sorted(pending):
                brief = briefs[index]
                marker = self.store.get_json(marker_key(brief["run_id"], brief["subject"], brief["researcher"]))
                if marker is not None:
                    results[index]["marker"] = marker
                    pending.discard(index)
            if pending:
                time.sleep(self.poll_seconds)
        for index in pending:
            results[index]["error"] = "marqueur absent dans le délai"
        for result in results:
            marker = result.get("marker") or {}
            key = marker.get("findings_key")
            findings = []
            if key:
                document = self.store.get_json(key) or {}
                findings = document.get("findings") or []
            result["findings"] = findings
        return results


class AgentCoreLauncher(Launcher):
    def __init__(self, store: Store, *, runtime_arn: str, region: str, client: Any | None = None, **kwargs: Any):
        super().__init__(store, **kwargs)
        self.runtime_arn = runtime_arn
        self.region = region
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "bedrock-agentcore",
                region_name=self.region,
                config=Config(connect_timeout=10, read_timeout=60, retries={"max_attempts": 3, "mode": "adaptive"}),
            )
        return self._client

    def start(self, brief: dict[str, Any]) -> None:
        payload = json.dumps({"action": "research", **brief}).encode("utf-8")
        response = self._get_client().invoke_agent_runtime(
            agentRuntimeArn=self.runtime_arn,
            runtimeSessionId=session_id(brief["run_id"], brief["subject"], brief["researcher"]),
            contentType="application/json",
            accept="application/json",
            payload=payload,
        )
        body = response.get("response")
        raw = body.read() if hasattr(body, "read") else body
        answer = json.loads(raw) if raw else {}
        if not answer.get("ok"):
            raise RuntimeError((answer.get("error") or {}).get("message") or "réponse invalide du chercheur")


def resolve_runtime_arn(name: str, region: str, client: Any | None = None) -> str:
    """ARN d'un runtime AgentCore à partir de son nom (l'ARN porte un suffixe aléatoire, connu après création)."""
    if client is None:
        import boto3

        client = boto3.client("bedrock-agentcore-control", region_name=region)
    token = None
    while True:
        page = client.list_agent_runtimes(**({"nextToken": token} if token else {}), maxResults=100)
        for runtime in page.get("agentRuntimes") or []:
            if runtime.get("agentRuntimeName") == name:
                return runtime["agentRuntimeArn"]
        token = page.get("nextToken")
        if not token:
            raise RuntimeError(f"runtime AgentCore introuvable : {name}")


class LocalLauncher(Launcher):
    """Exécute chaque mission dans un fil, avec le même service que le runtime ``researcher``."""

    def __init__(self, store: Store, service_factory: Callable[[], Any], **kwargs: Any):
        super().__init__(store, **kwargs)
        self.service_factory = service_factory
        self._threads: list[threading.Thread] = []

    def start(self, brief: dict[str, Any]) -> None:
        service = self.service_factory()
        answer = service.handle({"action": "research", **brief})
        if not answer.get("ok"):
            raise RuntimeError((answer.get("error") or {}).get("message") or "mission refusée")
