"""Lecture des bases OKF (``kb.list``, ``kb.get``) et recherche dans la base générale (Knowledge Base).

La recherche passe par ``bedrock-agent-runtime`` ``Retrieve`` quand ``ALPHAFORGE_KB_ID`` est posé;
sinon elle ne renvoie rien (développement local). Un filtre facultatif porte sur les métadonnées des fichiers
compagnons (``type``, ``ticker``, ``kind``, ``published_epoch``; CONTRACTS.md 5.1) : ``retrieval_filter`` le construit.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import boto3
from botocore.config import Config

from .. import okf
from ..config import Settings
from ..errors import AppError, pick
from ..store import Store, StoreError, validate_key, validate_prefix
from . import kb_links
from .state import is_client_id

logger = logging.getLogger("alphaforge.kb")
MAX_LIST = 500
CHUNK_ID_KEY = "x-amz-bedrock-kb-chunk-id"
# Opérateurs de RetrievalFilter permis sur S3 Vectors (startsWith, stringContains et listContains ne le sont pas).
_LOGICAL_OPERATORS = ("andAll", "orAll")
_COMPARISONS = {
    "equals": (str, int, float, bool),
    "notEquals": (str, int, float, bool),
    "greaterThan": (int, float),
    "greaterThanOrEquals": (int, float),
    "lessThan": (int, float),
    "lessThanOrEquals": (int, float),
    "in": (list,),
    "notIn": (list,),
}
TRACE_JSON = re.compile(r"^clients/[0-9a-f-]{36}/traces/[A-Za-z0-9._-]+\.json$")


# Une demande de documents mal formée ne vient pas de l'investisseur : le message ne cite ni clé ni chemin.
LIST_UNAVAILABLE_FR = "Ces documents ne peuvent pas être affichés. Rechargez la page, puis réessayez."
LIST_UNAVAILABLE_EN = "These documents cannot be shown. Reload the page, then try again."
DOCUMENT_UNAVAILABLE_FR = "Ce document ne peut pas être affiché. Rechargez la page, puis réessayez."
DOCUMENT_UNAVAILABLE_EN = "This document cannot be shown. Reload the page, then try again."


def check_prefix(prefix: Any, locale: str) -> str:
    if not isinstance(prefix, str):
        raise AppError("bad_request", pick(locale, LIST_UNAVAILABLE_FR, LIST_UNAVAILABLE_EN))
    try:
        validate_prefix(prefix)
    except StoreError as exc:
        raise AppError("bad_request", pick(locale, LIST_UNAVAILABLE_FR, LIST_UNAVAILABLE_EN)) from exc
    if prefix.startswith("general/"):
        return prefix
    parts = prefix.split("/")
    if len(parts) >= 3 and parts[0] == "clients" and is_client_id(parts[1]):
        return prefix
    raise AppError(
        "bad_request",
        pick(locale, LIST_UNAVAILABLE_FR, LIST_UNAVAILABLE_EN),
    )


def list_documents(store: Store, prefix: str) -> list[dict[str, Any]]:
    """Documents d'une base, avec leurs liens vers les autres documents listés et leurs symboles (``kb_links``)."""
    infos = [info for info in store.list(prefix, limit=MAX_LIST * 2) if info.key.endswith(".md")][:MAX_LIST]
    known = {info.key for info in infos}

    def describe(info: Any) -> tuple[dict[str, Any], kb_links.Relations] | None:
        obj = store.get(info.key)
        if obj is None:
            return None
        try:
            doc = okf.parse(obj.text)
        except okf.OkfError:
            unreadable = {"key": info.key, "title": None, "type": None, "description": None}
            return {**unreadable, "updated_at": info.last_modified}, kb_links.Relations()
        if doc.data.get("retired") is True:
            return None  # note retirée de la base du client (le runtime n'a pas s3:DeleteObject)
        summary = okf.summary(doc)
        item = {
            "key": info.key,
            "title": summary["title"],
            "type": summary["type"],
            "description": summary["description"],
            "updated_at": summary["generated_at"] or info.last_modified,
        }
        return item, kb_links.relations(info.key, doc, known)

    with ThreadPoolExecutor(max_workers=8) as pool:
        described = [entry for entry in pool.map(describe, infos) if entry is not None]
    return sorted(kb_links.attach(described), key=lambda item: item["key"])


def check_key(key: Any, client_id: Any, locale: str) -> str:
    if not isinstance(key, str):
        raise AppError("bad_request", pick(locale, DOCUMENT_UNAVAILABLE_FR, DOCUMENT_UNAVAILABLE_EN))
    try:
        validate_key(key)
    except StoreError as exc:
        raise AppError("bad_request", pick(locale, DOCUMENT_UNAVAILABLE_FR, DOCUMENT_UNAVAILABLE_EN)) from exc
    if key.startswith("general/") and key.endswith(".md"):
        return key
    if key.startswith("clients/"):
        owner = key.split("/")[1] if key.count("/") >= 2 else ""
        if not (key.endswith(".md") or TRACE_JSON.match(key)):
            raise AppError("bad_request", pick(locale, DOCUMENT_UNAVAILABLE_FR, DOCUMENT_UNAVAILABLE_EN))
        if not client_id:
            raise AppError(
                "bad_request",
                pick(locale, DOCUMENT_UNAVAILABLE_FR, DOCUMENT_UNAVAILABLE_EN),
            )
        if client_id != owner:
            raise AppError("not_found", pick(locale, "Document introuvable.", "Document not found."))
        return key
    raise AppError(
        "bad_request",
        pick(locale, DOCUMENT_UNAVAILABLE_FR, DOCUMENT_UNAVAILABLE_EN),
    )


def check_filter(node: Any, depth: int = 0) -> dict[str, Any]:
    """Vérifie un ``RetrievalFilter`` avant l'appel : une erreur de forme ne doit pas devenir une liste vide."""
    if not isinstance(node, dict) or len(node) != 1:
        raise ValueError("a retrieval filter has exactly one operator")
    ((operator, operand),) = node.items()
    if operator in _LOGICAL_OPERATORS:
        if depth >= 2 or not isinstance(operand, list) or len(operand) < 2:
            raise ValueError(f"{operator} needs at least two filters, with one level of nesting at most")
        for child in operand:
            check_filter(child, depth + 1)
        return node
    types = _COMPARISONS.get(operator)
    if types is None:
        raise ValueError(f"unsupported retrieval filter operator {operator!r} (S3 Vectors)")
    if not isinstance(operand, dict) or set(operand) != {"key", "value"} or not isinstance(operand["key"], str):
        raise ValueError(f"{operator} takes {{key, value}}")
    value = operand["value"]
    if not isinstance(value, types) or (bool not in types and isinstance(value, bool)):
        raise ValueError(f"{operator} does not accept {type(value).__name__} values")
    if isinstance(value, list) and not all(isinstance(item, str) for item in value):
        raise ValueError(f"{operator} takes a list of strings")
    return node


def retrieval_filter(
    *, equals: dict[str, Any] | None = None, at_most: dict[str, int | float] | None = None
) -> dict[str, Any] | None:
    """``RetrievalFilter`` : ``equals`` pour chaque paire de ``equals``, ``lessThanOrEquals`` pour ``at_most``.

    Exemple : ``retrieval_filter(equals={"ticker": "SHOP.TO"}, at_most={"published_epoch": 1794497400})``. Plusieurs
    conditions sont réunies par ``andAll``; une seule est renvoyée telle quelle (``andAll`` en demande deux).
    """
    conditions = [{"equals": {"key": key, "value": value}} for key, value in (equals or {}).items()]
    conditions += [{"lessThanOrEquals": {"key": key, "value": value}} for key, value in (at_most or {}).items()]
    if not conditions:
        return None
    node = conditions[0] if len(conditions) == 1 else {"andAll": conditions}
    return check_filter(node)


class KnowledgeSearch:
    """Recherche dans la base générale indexée par Bedrock Knowledge Bases (``Retrieve``)."""

    def __init__(self, settings: Settings, client: Any | None = None):
        self.kb_id = settings.kb_id
        self.region = settings.region
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.kb_id)

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "bedrock-agent-runtime",
                region_name=self.region,
                config=Config(connect_timeout=5, read_timeout=20, retries={"max_attempts": 2, "mode": "standard"}),
            )
        return self._client

    def search(self, query: str, limit: int = 4, *, filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Passages de la base générale; ``filter`` (``RetrievalFilter``, voir ``retrieval_filter``) est facultatif.

        Chaque résultat : ``source`` (URI S3), ``score``, ``excerpt`` et ``chunk_id`` (identifiant du passage dans la
        Knowledge Base, ``None`` s'il manque). Un filtre mal formé lève ``ValueError`` avant tout appel.
        """
        if filter is not None:
            check_filter(filter)
        if not self.enabled or not query.strip():
            return []
        vector_search: dict[str, Any] = {"numberOfResults": max(1, min(limit, 8))}
        if filter is not None:
            vector_search["filter"] = filter
        try:
            response = self._get_client().retrieve(
                knowledgeBaseId=self.kb_id,
                retrievalQuery={"text": query[:1000]},
                retrievalConfiguration={"vectorSearchConfiguration": vector_search},
            )
        except Exception as exc:
            logger.warning("knowledge base retrieve failed: %s", type(exc).__name__)
            return []
        results = []
        for item in response.get("retrievalResults", [])[:limit]:
            location = item.get("location") or {}
            uri = (location.get("s3Location") or {}).get("uri") or location.get("type")
            text = ((item.get("content") or {}).get("text") or "").strip()
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            results.append(
                {
                    "source": uri,
                    "score": round(float(item.get("score") or 0), 3),
                    "excerpt": text[:700] + ("…" if len(text) > 700 else ""),
                    "chunk_id": metadata.get(CHUNK_ID_KEY),
                }
            )
        return results
