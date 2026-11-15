"""Documents OKF : frontmatter YAML puis corps Markdown (CONTRACTS.md, section 5).

``parse`` et ``render`` font un aller-retour sans perte : les dates sont gardées en chaînes ISO,
et une date YAML non citée (écrite à la main dans un seed) est relue comme chaîne.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import yaml

DOC_TYPES = (
    "Investor Profile",
    "Existing Portfolio",
    "Profile Journal",
    "News",
    "Data Series",
    "Methodology",
    "Financial Concept",
    "Company Fundamentals",
    "Index",
    # Recherche par experts (A0, E1 à E7, CONTRACTS.md section 11).
    "Fact",
    "Market Signal",
    "Regulatory Filing",
    "Research Brief",
    # Fonctionnalité vidéo tldoole.
    "Concept Gaps",
    "Learning Video",
)
REQUIRED_KEYS = ("type", "title", "description", "tags", "status", "owners", "sensitivity", "generated", "sources")
KEY_ORDER = (*REQUIRED_KEYS[:8], "stale_after", "sources", "data")
STATUSES = ("draft", "stable")
SENSITIVITIES = ("client", "public")


class OkfError(ValueError):
    pass


@dataclass
class OkfDoc:
    frontmatter: dict[str, Any]
    body: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def data(self) -> dict[str, Any]:
        value = self.frontmatter.get("data")
        if not isinstance(value, dict):
            value = {}
            self.frontmatter["data"] = value
        return value

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title") or "")

    @property
    def type(self) -> str:
        return str(self.frontmatter.get("type") or "")


def _normalize(value: Any) -> Any:
    if isinstance(value, datetime):
        text = value.isoformat()
        return text.replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_normalize(v) for v in value]
    return value


def parse(text: str) -> OkfDoc:
    """Sépare le frontmatter YAML du corps Markdown."""
    if text.startswith("﻿"):
        text = text[1:]
    if not text.startswith("---"):
        raise OkfError("missing YAML frontmatter")
    lines = text.splitlines(keepends=True)
    if lines[0].strip() != "---":
        raise OkfError("frontmatter must start with ---")
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        raise OkfError("unterminated frontmatter")
    raw = "".join(lines[1:end])
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise OkfError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(meta, dict):
        raise OkfError("frontmatter must be a mapping")
    body = "".join(lines[end + 1 :])
    if body.startswith("\n"):
        body = body[1:]
    return OkfDoc(frontmatter=_normalize(meta), body=body)


def _ordered(meta: dict[str, Any]) -> dict[str, Any]:
    ordered = {key: meta[key] for key in KEY_ORDER if key in meta}
    for key, value in meta.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def render(doc: OkfDoc) -> str:
    meta = _ordered(_normalize(doc.frontmatter))
    dumped = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=False, width=110)
    body = doc.body if doc.body.endswith("\n") or not doc.body else doc.body + "\n"
    return f"---\n{dumped}---\n\n{body}"


def validate(doc: OkfDoc) -> list[str]:
    """Liste les écarts au format (vide si le document est conforme)."""
    problems = []
    meta = doc.frontmatter
    for key in REQUIRED_KEYS:
        if key not in meta:
            problems.append(f"missing key {key}")
    if meta.get("type") not in DOC_TYPES:
        problems.append(f"unknown type {meta.get('type')!r}")
    if meta.get("status") not in STATUSES:
        problems.append(f"invalid status {meta.get('status')!r}")
    if meta.get("sensitivity") not in SENSITIVITIES:
        problems.append(f"invalid sensitivity {meta.get('sensitivity')!r}")
    if not isinstance(meta.get("tags"), list):
        problems.append("tags must be a list")
    if not isinstance(meta.get("owners"), list):
        problems.append("owners must be a list")
    generated = meta.get("generated")
    if not isinstance(generated, dict) or not generated.get("by") or not generated.get("at"):
        problems.append("generated must have by and at")
    sources = meta.get("sources")
    if not isinstance(sources, list):
        problems.append("sources must be a list")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, dict) or not source.get("id") or not source.get("title"):
                problems.append(f"source {index} needs id and title")
    if "data" in meta and not isinstance(meta["data"], dict):
        problems.append("data must be a mapping")
    return problems


def new_doc(
    *,
    type: str,
    title: str,
    description: str,
    tags: list[str],
    owners: list[str],
    sensitivity: str,
    generated_by: str,
    at: str,
    status: str = "stable",
    stale_after: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    data: dict[str, Any] | None = None,
    body: str = "",
) -> OkfDoc:
    meta: dict[str, Any] = {
        "type": type,
        "title": title,
        "description": description,
        "tags": list(tags),
        "status": status,
        "owners": list(owners),
        "sensitivity": sensitivity,
        "generated": {"by": generated_by, "at": at},
    }
    if stale_after:
        meta["stale_after"] = stale_after
    meta["sources"] = list(sources or [])
    meta["data"] = dict(data or {})
    return OkfDoc(frontmatter=meta, body=body)


def summary(doc: OkfDoc) -> dict[str, Any]:
    """Champs affichés par ``kb.list``."""
    meta = doc.frontmatter
    generated = meta.get("generated") if isinstance(meta.get("generated"), dict) else {}
    return {
        "title": meta.get("title"),
        "type": meta.get("type"),
        "description": meta.get("description"),
        "generated_at": generated.get("at") if generated else None,
    }
