"""Application ``BedrockAgentCoreApp`` : un seul code, un runtime par ``AGENT_ROLE`` (``config.ROLES``).

Chaque service n'est importé que pour son rôle : ``portfolio`` charge le volet finance (numpy, cvxpy) à sa première
construction, jamais au démarrage des autres runtimes.

``POST /invocations`` reçoit le JSON de CONTRACTS.md; une réponse générateur devient un flux SSE
(``text/event-stream``, un événement JSON par ligne ``data:``). ``GET /ping`` est servi par l'application :
``HealthyBusy`` tant qu'une tâche de collecte tourne.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from . import otel
from .config import ROLES, Settings
from .store import Store, make_store

logger = logging.getLogger("alphaforge")


def _local_seed_dir() -> Path | None:
    """``app/knowledge/general`` quand le code tourne depuis le dépôt (jamais dans le zip déployé)."""
    parents = Path(__file__).resolve().parents
    candidate = parents[3] / "knowledge" / "general" if len(parents) > 3 else None
    return candidate if candidate is not None and candidate.is_dir() else None


def seed_local_general(store: Store, directory: Path) -> int:
    """Copie dans le magasin local les documents ``general/`` versionnés qui y manquent (Terraform le fait en AWS)."""
    written = 0
    for path in sorted(directory.rglob("*.md")):
        key = "general/" + path.relative_to(directory).as_posix()
        if not store.exists(key):
            store.put_text(key, path.read_text(encoding="utf-8"))
            written += 1
    return written


def build_service(settings: Settings, app: Any, store: Store | None = None) -> Any:
    if store is None:
        store = make_store(settings)
        seed_dir = _local_seed_dir() if settings.store == "local" else None
        if seed_dir is not None:
            count = seed_local_general(store, seed_dir)
            if count:
                logger.info("local store: %d general/ documents seeded from %s", count, seed_dir)
    if settings.role == "profile":
        from .profile.service import ProfileService

        return ProfileService(settings, store)
    if settings.role in ("press", "data", "supervisor"):
        from .collect.service import CollectorService

        return CollectorService(settings, store, app)
    if settings.role in ("router", "expert", "researcher"):
        from .research.service import ResearchService

        return ResearchService(settings, store, app)
    if settings.role == "portfolio":
        from .portfolio_service import PortfolioService

        return PortfolioService(settings, store, app)
    raise ValueError(f"AGENT_ROLE must be one of {ROLES}, got {settings.role!r}")


def create_app(
    settings: Settings | None = None, store: Store | None = None, service: Any | None = None
) -> BedrockAgentCoreApp:
    settings = settings or Settings.from_env()
    app = BedrockAgentCoreApp()
    handler = service or build_service(settings, app, store)

    @app.entrypoint
    def invoke(payload: Any, context: Any = None) -> Any:
        return handler.handle(payload)

    app.state.alphaforge_service = handler
    app.state.alphaforge_settings = settings
    logger.info(
        "alphaforge runtime ready: role=%s env=%s store=%s otel=%s",
        settings.role,
        settings.env,
        settings.store,
        "on" if otel.state["active"] else "off",
    )
    return app


def serve(app: BedrockAgentCoreApp) -> None:
    settings: Settings = app.state.alphaforge_settings
    host = os.environ.get("ALPHAFORGE_HOST") or ("0.0.0.0" if settings.store == "s3" else None)  # noqa: S104
    port = int(os.environ.get("PORT") or "8080")
    app.run(port=port, host=host)


def configure_logging() -> None:
    level = getattr(logging, os.environ.get("ALPHAFORGE_LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # Sous ADOT (alphaforge/otel.py), l'instrumentation des journaux a déjà posé le format (avec trace_id et span_id) :
    # basicConfig ne fait alors rien, d'où le niveau posé à part.
    logging.getLogger().setLevel(level)
