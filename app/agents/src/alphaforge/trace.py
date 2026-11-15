"""Étapes de trace (``TraceStep``, CONTRACTS.md 3.3) et diffusion des événements de streaming (3.4).

Une trace ne contient ni raisonnement interne du modèle ni secret : le titre et le détail décrivent
l'action observable (outil appelé, entrées résumées, résultat).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from . import clock

KINDS = ("deterministic", "agent", "model", "tool", "storage", "guardrail")
# A7 (détecteur de lacunes), A8 (scénariste vidéo), polly et mediaconvert : fonctionnalité vidéo tldoole.
ACTORS = (
    "questionnaire",
    "completeness",
    "A1",
    "A2",
    "A4",
    "A5",
    "A6",
    "A7",
    "A8",
    "store",
    "guardrail",
    "polly",
    "mediaconvert",
)

_MAX_STRING = 300
_MAX_ITEMS = 20


def compact_value(value: Any, depth: int = 0) -> Any:
    """Réduit une valeur pour la trace : chaînes tronquées, listes et dictionnaires bornés."""
    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING else value[: _MAX_STRING - 1] + "…"
    if isinstance(value, bool | int | float) or value is None:
        return value
    if depth >= 4:
        return "…"
    if isinstance(value, dict):
        items = list(value.items())[:_MAX_ITEMS]
        return {str(k): compact_value(v, depth + 1) for k, v in items}
    if isinstance(value, list | tuple | set):
        seq = list(value)
        out = [compact_value(v, depth + 1) for v in seq[:_MAX_ITEMS]]
        if len(seq) > _MAX_ITEMS:
            out.append(f"… (+{len(seq) - _MAX_ITEMS})")
        return out
    return str(value)[:_MAX_STRING]


class Emitter:
    """Reçoit les étapes et les morceaux de message au fil de l'eau (streaming SSE)."""

    def trace(self, step: dict[str, Any]) -> None:  # pragma: no cover - interface
        pass

    def delta(self, text: str) -> None:  # pragma: no cover - interface
        pass


class NullEmitter(Emitter):
    pass


class Trace:
    def __init__(self, locale: str = "fr", emitter: Emitter | None = None):
        self.locale = locale
        self.emitter = emitter or NullEmitter()
        self.steps: list[dict[str, Any]] = []

    def t(self, fr: str, en: str) -> str:
        return en if self.locale == "en" else fr

    def add(
        self,
        kind: str,
        actor: str,
        title: str,
        detail: str | None = None,
        *,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        sources: list[dict[str, Any]] | None = None,
        duration_ms: int = 0,
        at: str | None = None,
    ) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"unknown trace kind {kind!r}")
        if actor not in ACTORS:
            raise ValueError(f"unknown trace actor {actor!r}")
        step = {
            "id": f"st_{len(self.steps) + 1:02d}",
            "at": at or clock.iso(ms=True),
            "kind": kind,
            "actor": actor,
            "title": title,
            "detail": detail,
            "inputs": compact_value(inputs or {}),
            "outputs": compact_value(outputs or {}),
            "sources": [compact_value(source) for source in (sources or [])],
            "duration_ms": int(duration_ms),
        }
        self.steps.append(step)
        self.emitter.trace(step)
        return step

    @contextmanager
    def step(
        self,
        kind: str,
        actor: str,
        title: str,
        detail: str | None = None,
        *,
        inputs: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Mesure une action; l'appelant remplit ``outputs``, ``sources`` ou ``detail`` du dictionnaire rendu."""
        started_at = clock.iso(ms=True)
        started = time.perf_counter()
        info: dict[str, Any] = {"detail": detail, "outputs": {}, "sources": []}
        try:
            yield info
        finally:
            self.add(
                kind,
                actor,
                info.get("title") or title,
                info.get("detail"),
                inputs=inputs,
                outputs=info.get("outputs"),
                sources=info.get("sources"),
                duration_ms=int((time.perf_counter() - started) * 1000),
                at=started_at,
            )
