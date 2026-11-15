"""Éléments collectés (``staging/<run_id>/<role>/<id>.json``) et marqueurs ``_done.json`` (CONTRACTS.md, section 4)."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import urllib.parse
from typing import Any

RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ITEM_KINDS = ("news", "series", "quote")
_TRACKING = re.compile(r"^(utm_|oc$|ncid$|guccounter$|soc_|cmpid$|guce_)")


def staging_prefix(run_id: str, role: str) -> str:
    return f"staging/{run_id}/{role}/"


def marker_key(run_id: str, role: str) -> str:
    return f"staging/{run_id}/{role}/_done.json"


def item_key(run_id: str, role: str, item_id: str) -> str:
    return f"staging/{run_id}/{role}/{item_id}.json"


def short_hash(value: str, length: int = 12) -> str:
    return hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).hexdigest()[:length]


def normalize_url(url: str) -> str:
    """URL canonique pour les doublons : schéma et hôte en minuscules, sans fragment ni paramètres de suivi."""
    parts = urllib.parse.urlsplit(url.strip())
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k)]
    return urllib.parse.urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urllib.parse.urlencode(query), "")
    )


def slugify(text: str, limit: int = 70) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return (slug[:limit].rstrip("-")) or "element"


def title_key(title: str) -> str:
    return slugify(title, 60)


def news_item_id(url: str) -> str:
    return "news-" + short_hash(normalize_url(url))


def series_slug(series_id: str) -> str:
    return slugify(series_id.replace(".", "-"), 40)


def new_item(
    *,
    item_id: str,
    kind: str,
    title: str,
    url: str,
    source: str,
    published_at: str,
    observed_at: str | None,
    retrieved_at: str,
    language: str,
    tickers: list[str],
    summary: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    if kind not in ITEM_KINDS:
        raise ValueError(kind)
    return {
        "id": item_id,
        "kind": kind,
        "title": title,
        "url": url,
        "source": source,
        "published_at": published_at,
        "observed_at": observed_at,
        "retrieved_at": retrieved_at,
        "language": language,
        "tickers": tickers,
        "summary": summary,
        "data": data,
    }
