"""Erreurs applicatives et enveloppe de réponse commune (CONTRACTS.md, section 2)."""

from __future__ import annotations

from typing import Any

ERROR_CODES = frozenset(
    {
        "bad_request",
        "unknown_action",
        "not_found",
        "invalid_answer",
        "conflict",
        "model_error",
        "guardrail_blocked",
        "internal",
    }
)


class AppError(Exception):
    """Erreur renvoyée au client sous la forme ``{"ok": false, "error": {...}}``."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        if code not in ERROR_CODES:
            raise ValueError(f"unknown error code {code!r}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


def ok_response(release: str, **fields: Any) -> dict[str, Any]:
    return {"ok": True, "release": release, **fields}


def error_response(release: str, error: AppError) -> dict[str, Any]:
    return {"ok": False, "release": release, "error": error.to_dict()}


def pick(locale: str | None, fr: str, en: str) -> str:
    """Choisit le texte dans la langue de la requête (français par défaut)."""
    return en if locale == "en" else fr
