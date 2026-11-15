"""Documents OKF : frontmatter YAML puis corps Markdown (CONTRACTS.md, section 5).

``parse`` et ``render`` font un aller-retour sans perte : les dates sont gardées en chaînes ISO,
et une date YAML non citée (écrite à la main dans un seed) est relue comme chaîne.

``kb_metadata`` donne le fichier compagnon ``<clé>.metadata.json`` qu'indexe la Knowledge Base (attributs
filtrables ``type``, ``ticker``, ``kind``, ``published_epoch``; CONTRACTS.md, section 5.1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import yaml

from . import clock

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
    "Profile Note",  # note de la base d'un client, écrite par A1 avec son skill (profile/skills/)
    # Recherche par experts (A0, E1 à E7, CONTRACTS.md section 11).
    "Fact",
    "Market Signal",
    "Regulatory Filing",
    "Research Brief",
    # Volet finance : caractéristiques calculées d'un titre (general/donnees/features/) et décision simulée
    # (clients/<id>/decisions/, écrite par finance/debate/okf_bridge.py).
    "Stock Features",
    "Portfolio Decision",
)
REQUIRED_KEYS = ("type", "title", "description", "tags", "status", "owners", "sensitivity", "generated", "sources")
KEY_ORDER = (*REQUIRED_KEYS[:8], "stale_after", "sources", "data")
STATUSES = ("draft", "stable")
SENSITIVITIES = ("client", "public")

# Preuves ESG (CONTRACTS.md, section 11.5) : un fait de la recherche porte ``data.esg = {kind, metric, period}``.
# Listes fermées, vérifiées par le chercheur, par A6 et par le lecteur du volet finance.
ESG_KINDS = ("emissions", "incident", "index_exclusion", "sector_activity")
# ``sector_activity`` relie un titre à une catégorie d'exclusion du questionnaire (preferences.exclusions).
ESG_ACTIVITIES = ("tobacco", "weapons", "fossil_fuels", "gambling", "alcohol")
_ESG_METRIC = re.compile(r"^[a-z0-9_]{1,40}$")
_ESG_PERIOD = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def esg_problems(esg: Any) -> list[str]:
    """Raisons de refuser un bloc ``data.esg`` ; liste vide s'il est conforme."""
    if not isinstance(esg, dict):
        return ["data.esg doit être un objet {kind, metric, period}"]
    problems = []
    extra = sorted(set(esg) - {"kind", "metric", "period"})
    if extra:
        problems.append(f"champs ESG inconnus : {extra}")
    kind, metric, period = esg.get("kind"), esg.get("metric"), esg.get("period")
    if kind not in ESG_KINDS:
        problems.append(f"esg.kind {kind!r} hors de la liste {ESG_KINDS}")
    if not isinstance(metric, str) or not _ESG_METRIC.match(metric):
        problems.append(f"esg.metric {metric!r} : minuscules, chiffres et _ (40 au plus)")
    elif kind == "sector_activity" and metric not in ESG_ACTIVITIES:
        problems.append(f"esg.metric {metric!r} : une activité sectorielle est l'une de {ESG_ACTIVITIES}")
    if not isinstance(period, str) or not _ESG_PERIOD.match(period):
        problems.append(f"esg.period {period!r} : AAAA, AAAA-MM ou AAAA-MM-JJ")
    return problems


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


# Clés à valeur imposée : (clé, valeurs permises, début du message d'écart).
_ENUM_KEYS = (
    ("type", DOC_TYPES, "unknown type"),
    ("status", STATUSES, "invalid status"),
    ("sensitivity", SENSITIVITIES, "invalid sensitivity"),
)
_LIST_KEYS = ("tags", "owners")


def _source_problems(sources: Any) -> list[str]:
    if not isinstance(sources, list):
        return ["sources must be a list"]
    return [
        f"source {index} needs id and title"
        for index, source in enumerate(sources)
        if not isinstance(source, dict) or not source.get("id") or not source.get("title")
    ]


def validate(doc: OkfDoc) -> list[str]:
    """Liste les écarts au format (vide si le document est conforme)."""
    meta = doc.frontmatter
    problems = [f"missing key {key}" for key in REQUIRED_KEYS if key not in meta]
    for key, allowed, message in _ENUM_KEYS:
        if meta.get(key) not in allowed:
            problems.append(f"{message} {meta.get(key)!r}")
    problems += [f"{key} must be a list" for key in _LIST_KEYS if not isinstance(meta.get(key), list)]
    generated = meta.get("generated")
    if not isinstance(generated, dict) or not generated.get("by") or not generated.get("at"):
        problems.append("generated must have by and at")
    problems += _source_problems(meta.get("sources"))
    if "data" in meta and not isinstance(meta["data"], dict):
        problems.append("data must be a mapping")
    return problems


def new_doc(  # noqa: PLR0913 - un argument nommé par clé du frontmatter (CONTRACTS.md, section 5), passé par mot-clé
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


# --------------------------------------------------------------------------- métadonnées de la Knowledge Base

KB_METADATA_SUFFIX = ".metadata.json"
# Suffixes de bourse canadiens de Yahoo Finance : un slug ``shop-to`` redevient ``SHOP.TO``.
_EXCHANGE_SLUG = re.compile(r"^([A-Z0-9][A-Z0-9-]*)-(TO|V|NE|CN)$")
_TICKER = re.compile(r"^[A-Z0-9^][A-Z0-9.=^-]{0,19}$")
# Type de document -> ``kind`` quand ``data.kind`` est absent.
_DEFAULT_KINDS = {"Stock Features": "features"}


def canonical_ticker(value: Any) -> str | None:
    """Forme canonique d'un symbole : majuscules, suffixe de bourse avec un point (``SHOP.TO``).

    Accepte ``SHOP.TO``, l'étiquette d'actualité ``shop.to`` et le slug de données ``shop-to``. Un tiret qui ne
    précède pas un suffixe canadien est gardé (``BTC-USD``, ``BRK-B``). ``None`` si la valeur n'est pas un symbole.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    if "." not in text:
        match = _EXCHANGE_SLUG.match(text)
        if match:
            text = f"{match.group(1)}.{match.group(2)}"
    return text if _TICKER.match(text) else None


def kb_metadata_key(doc_key: str) -> str:
    """Clé du fichier compagnon : la clé du document suivie de ``.metadata.json`` (règle de Bedrock)."""
    return doc_key + KB_METADATA_SUFFIX


def published_epoch(value: Any) -> int | None:
    """Date de publication en secondes UTC depuis l'époque Unix (une date seule vaut minuit UTC)."""
    parsed = clock.parse_datetime(value) if isinstance(value, str) else None
    return int(parsed.timestamp()) if parsed is not None else None


def _doc_ticker(data: dict[str, Any]) -> str | None:
    for candidate in (data.get("ticker"), data.get("symbol")):
        ticker = canonical_ticker(candidate)
        if ticker:
            return ticker
    tickers = data.get("tickers")
    if isinstance(tickers, list):
        # Une actualité peut citer plusieurs titres : seul le premier (celui de la recherche) est filtrable.
        for candidate in tickers:
            ticker = canonical_ticker(candidate)
            if ticker:
                return ticker
    return None


def _doc_published_epoch(doc_type: str, data: dict[str, Any]) -> int | None:
    if doc_type == "Stock Features":
        # Le document n'est connu qu'une fois publiée la plus récente de ses entrées.
        features = data.get("features") if isinstance(data.get("features"), dict) else {}
        epochs = [
            published_epoch(feature.get("published_at")) for feature in features.values() if isinstance(feature, dict)
        ]
        known = [epoch for epoch in epochs if epoch is not None]
        return max(known) if known else None
    if doc_type == "Company Fundamentals":
        # Même règle : la plus récente des publications de ses périodes et de ses bilans.
        entries = [e for name in ("periods", "balance_sheets") for e in data.get(name) or [] if isinstance(e, dict)]
        known = [epoch for epoch in (published_epoch(e.get("published_at")) for e in entries) if epoch is not None]
        return max(known) if known else None
    return published_epoch(data.get("published_at"))


def kb_metadata(doc_key: str, frontmatter: dict[str, Any]) -> dict[str, Any]:
    """Contenu de ``<doc_key>.metadata.json`` au format S3 de Bedrock Knowledge Bases.

    Attributs (tous filtrables, aucun n'entre dans l'embedding) :
    - ``type`` (STRING) : type OKF du document;
    - ``ticker`` (STRING) : symbole canonique (``canonical_ticker``) de ``data.ticker``, ``data.symbol`` ou du
      premier de ``data.tickers``; absent pour une série macroéconomique;
    - ``kind`` (STRING) : ``data.kind`` (``news``, ``series``, ``quote``), ``features`` pour Stock Features;
    - ``published_epoch`` (NUMBER) : date de publication en secondes UTC (``data.published_at``; pour Stock
      Features, la plus récente des ``published_at`` de ses caractéristiques). Absent si inconnue : un filtre
      ``lessThanOrEquals`` sur cet attribut écarte alors le document, ce qui évite toute anticipation.
    Seuls ``equals``, ``in`` et les comparaisons numériques sont permis sur S3 Vectors (pas ``startsWith``).
    """
    if not isinstance(doc_key, str) or not doc_key.startswith("general/") or not doc_key.endswith(".md"):
        raise OkfError(f"only general/*.md documents are indexed: {doc_key!r}")
    doc_type = frontmatter.get("type")
    if doc_type not in DOC_TYPES:
        raise OkfError(f"unknown type {doc_type!r}")
    data = frontmatter.get("data") if isinstance(frontmatter.get("data"), dict) else {}
    attributes: dict[str, Any] = {"type": doc_type}
    ticker = _doc_ticker(data)
    if ticker:
        attributes["ticker"] = ticker
    kind = data.get("kind") if isinstance(data.get("kind"), str) and data.get("kind") else _DEFAULT_KINDS.get(doc_type)
    if kind:
        attributes["kind"] = kind
    epoch = _doc_published_epoch(doc_type, data)
    if epoch is not None:
        attributes["published_epoch"] = epoch

    def typed(value: Any) -> dict[str, Any]:
        if isinstance(value, int):
            return {"type": "NUMBER", "numberValue": value}
        return {"type": "STRING", "stringValue": value}

    return {
        "metadataAttributes": {
            name: {"value": typed(value), "includeForEmbedding": False} for name, value in attributes.items()
        }
    }
