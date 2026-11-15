"""Horloge UTC unique, remplaçable dans les tests."""

from __future__ import annotations

from datetime import UTC, date, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime | None = None, *, ms: bool = False) -> str:
    """Horodatage ISO 8601 en UTC, suffixe ``Z`` (``2026-11-14T23:10:00Z``)."""
    value = (dt or utcnow()).astimezone(UTC)
    if ms:
        return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def compact(dt: datetime | None = None) -> str:
    """Horodatage pour les noms de fichiers de trace (``20261114T231000.120Z``)."""
    value = (dt or utcnow()).astimezone(UTC)
    return value.strftime("%Y%m%dT%H%M%S.") + f"{value.microsecond // 1000:03d}Z"


def today() -> date:
    return utcnow().date()


def parse_datetime(value: str | None) -> datetime | None:
    """Lit une date ou un horodatage ISO; une date seule vaut minuit UTC. ``None`` si illisible."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=UTC)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
