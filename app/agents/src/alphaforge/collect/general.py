"""Écriture des documents de la base générale, avec le fichier compagnon de la Knowledge Base (CONTRACTS.md, 5.1).

``write_document`` écrit d'abord ``<clé>.metadata.json`` (``okf.kb_metadata``), puis le document : le document est la
dernière écriture, et une reprise réécrit les deux. ``write_stock_features`` valide puis écrit un document
« Stock Features » (``general/donnees/features/<ticker-slug>/<as_of>.md``, en ajout seulement). Il ne calcule rien :
les définitions et les valeurs des caractéristiques appartiennent au volet finance.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from typing import Any

from .. import clock, okf
from ..store import ConflictError, Store
from . import staging

FEATURES_PREFIX = "general/donnees/features/"
FEATURES_STALE_DAYS = 35
FEATURES_KEYS = ("ticker", "as_of", "feature_set", "features", "missing", "inputs")
FEATURE_KEYS = (
    "value",
    "unit",
    "currency",
    "status",
    "observed_at",
    "published_at",
    "formula",
    "source_key",
    "source_sha256",
)
_FEATURE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FEATURE_SET = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_FORMULA = 500


class FeaturesError(ValueError):
    """Document Stock Features refusé; ``problems`` dit pourquoi, un écart par ligne."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def write_document(store: Store, key: str, doc: okf.OkfDoc, *, create_only: bool = False) -> str:
    """Écrit le fichier compagnon puis le document OKF; renvoie l'ETag du document.

    ``create_only`` : le document ne doit pas exister (``ConflictError`` sinon, sans rien écrire). Le document est
    écrit avec ``If-None-Match``; son compagnon, écrit juste avant, décrit la même clé.
    """
    problems = okf.validate(doc)
    if problems:
        raise okf.OkfError("; ".join(problems))
    metadata = okf.kb_metadata(key, doc.frontmatter)
    if create_only and store.exists(key):
        raise ConflictError(key)
    store.put_json(okf.kb_metadata_key(key), metadata)
    return store.put_text(key, okf.render(doc), if_none_match=create_only)


def features_key(ticker: str, as_of: str) -> str:
    return f"{FEATURES_PREFIX}{staging.series_slug(ticker)}/{as_of}.md"


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_measure(where: str, feature: dict[str, Any], problems: list[str]) -> None:
    """Valeur, statut, unité et devise d'une caractéristique."""
    value = feature["value"]
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value)
    ):
        problems.append(f"{where}.value must be a finite number or null")
    if not _nonempty_str(feature["status"]):
        problems.append(f"{where}.status is required")
    elif value is None and feature["status"] == "ok":
        problems.append(f"{where}: status ok needs a value")
    if not _nonempty_str(feature["unit"]):
        problems.append(f"{where}.unit is required")
    if feature["currency"] is not None and not (
        isinstance(feature["currency"], str) and _CURRENCY.match(feature["currency"])
    ):
        problems.append(f"{where}.currency must be a three-letter code or null")


def _check_dates(where: str, feature: dict[str, Any], as_of_end: Any, problems: list[str]) -> None:
    """Observation au plus égale à la publication, publication avant la fin du jour ``as_of`` (aucune anticipation)."""
    observed = clock.parse_datetime(feature["observed_at"])
    published = clock.parse_datetime(feature["published_at"])
    if observed is None:
        problems.append(f"{where}.observed_at is missing or unreadable")
    if published is None:
        problems.append(f"{where}.published_at is missing or unreadable")
    if observed is not None and published is not None and observed > published:
        problems.append(f"{where}: observed_at is after published_at")
    if published is not None and as_of_end is not None and published >= as_of_end:
        problems.append(f"{where}: published_at is after as_of (look-ahead)")


def _check_provenance(where: str, feature: dict[str, Any], problems: list[str]) -> None:
    """Formule, clé et empreinte sha256 de la source d'une caractéristique."""
    if not _nonempty_str(feature["formula"]) or len(feature["formula"]) > MAX_FORMULA:
        problems.append(f"{where}.formula is required ({MAX_FORMULA} characters at most)")
    if not _nonempty_str(feature["source_key"]):
        problems.append(f"{where}.source_key is required")
    if not (isinstance(feature["source_sha256"], str) and _SHA256.match(feature["source_sha256"])):
        problems.append(f"{where}.source_sha256 must be 64 lowercase hexadecimal characters")


def _check_feature(name: str, feature: Any, as_of_end: Any, problems: list[str]) -> None:
    where = f"features.{name}"
    if not isinstance(feature, dict):
        problems.append(f"{where} must be a mapping")
        return
    missing = [k for k in FEATURE_KEYS if k not in feature]
    extra = sorted(set(feature) - set(FEATURE_KEYS))
    if missing:
        problems.append(f"{where} misses {missing}")
    if extra:
        problems.append(f"{where} has unknown keys {extra}")
    if missing:
        return
    _check_measure(where, feature, problems)
    _check_dates(where, feature, as_of_end, problems)
    _check_provenance(where, feature, problems)


def _read_as_of(as_of: Any) -> tuple[Any, Any]:
    """``(as_of, fin du jour as_of)``; la fin vaut ``None`` si ``as_of`` n'est pas une date ``AAAA-MM-JJ``."""
    as_of_end = None
    if isinstance(as_of, str) and _DATE.match(as_of):
        try:
            as_of_end = clock.parse_datetime((date.fromisoformat(as_of) + timedelta(days=1)).isoformat())
        except ValueError:
            as_of = None
    return as_of, as_of_end


def _check_features(features: Any, as_of_end: Any, problems: list[str]) -> dict[str, Any]:
    """Les caractéristiques nommées selon ``_FEATURE_NAME``, chacune vérifiée; ``{}`` si ce n'est pas un mapping."""
    if not isinstance(features, dict):
        problems.append("features must be a mapping")
        return {}
    for name, feature in features.items():
        if not (isinstance(name, str) and _FEATURE_NAME.match(name)):
            problems.append(f"feature name {name!r} must match [a-z][a-z0-9_]*")
            continue
        _check_feature(name, feature, as_of_end, problems)
    return features


def _check_missing(missing: Any, features: dict[str, Any], problems: list[str]) -> list[Any]:
    """Noms des caractéristiques non calculées : uniques, sans recouper ``features``; ``[]`` si illisibles."""
    if not isinstance(missing, list) or not all(isinstance(m, str) and _FEATURE_NAME.match(m) for m in missing):
        problems.append("missing must be a list of feature names")
        return []
    if len(set(missing)) != len(missing) or set(missing) & set(features):
        problems.append("missing must be unique and never repeat a computed feature")
    return missing


def _check_inputs(inputs: Any, problems: list[str]) -> tuple[list[Any], set[str]]:
    """Entrées ``{key, etag}`` et l'ensemble de leurs clés; ``[]`` si ``inputs`` n'est pas une liste."""
    input_keys: set[str] = set()
    if not isinstance(inputs, list):
        problems.append("inputs must be a list")
        return [], input_keys
    for index, entry in enumerate(inputs):
        if not isinstance(entry, dict) or set(entry) != {"key", "etag"}:
            problems.append(f"inputs[{index}] must be {{key, etag}}")
        elif not _nonempty_str(entry["key"]) or not _nonempty_str(entry["etag"]):
            problems.append(f"inputs[{index}] needs a key and an etag")
        else:
            input_keys.add(entry["key"])
    return inputs, input_keys


def _check_sources(features: dict[str, Any], input_keys: set[str], problems: list[str]) -> None:
    """Chaque ``source_key`` figure dans ``inputs`` et ne porte qu'une empreinte."""
    sha_by_source: dict[str, set[str]] = {}
    for feature in features.values():
        if isinstance(feature, dict) and _nonempty_str(feature.get("source_key")):
            sha_by_source.setdefault(feature["source_key"], set()).add(str(feature.get("source_sha256")))
    for source, shas in sorted(sha_by_source.items()):
        if source not in input_keys:
            problems.append(f"source_key {source!r} is not listed in inputs")
        if len(shas) > 1:
            problems.append(f"source_key {source!r} has several sha256")


def validate_stock_features(payload: Any) -> dict[str, Any]:
    """Vérifie ``data`` d'un document Stock Features (CONTRACTS.md, section 5); renvoie ``data`` normalisé.

    Contrôles : clés connues seulement; symbole lisible (mis en forme canonique); ``as_of`` ``AAAA-MM-JJ``;
    chaque caractéristique porte ses neuf champs, une valeur finie (ou ``null`` hors statut ``ok``), une date
    d'observation au plus égale à sa publication, une publication au plus tard le jour ``as_of`` (aucune
    anticipation), une formule et l'empreinte sha256 de sa source; ``missing`` ne recoupe pas ``features``;
    chaque ``source_key`` figure dans ``inputs`` avec son ETag, et garde une seule empreinte.
    """
    if not isinstance(payload, dict):
        raise FeaturesError(["payload must be a mapping"])
    problems: list[str] = []
    extra = sorted(set(payload) - set(FEATURES_KEYS))
    if extra:
        problems.append(f"unknown keys {extra}")
    ticker = okf.canonical_ticker(payload.get("ticker"))
    if ticker is None:
        problems.append("ticker is missing or not a symbol")
    as_of, as_of_end = _read_as_of(payload.get("as_of"))
    if as_of_end is None:
        problems.append("as_of must be a YYYY-MM-DD date")
    feature_set = payload.get("feature_set")
    if not (isinstance(feature_set, str) and _FEATURE_SET.match(feature_set)):
        problems.append("feature_set must match [a-z0-9][a-z0-9._-]*")
    features = _check_features(payload.get("features"), as_of_end, problems)
    missing = _check_missing(payload.get("missing", []), features, problems)
    if not features and not missing:
        problems.append("features and missing are both empty")
    inputs, input_keys = _check_inputs(payload.get("inputs", []), problems)
    _check_sources(features, input_keys, problems)
    if problems:
        raise FeaturesError(problems)
    return {
        "ticker": ticker,
        "as_of": as_of,
        "feature_set": feature_set,
        "features": {name: dict(feature) for name, feature in features.items()},
        "missing": list(missing),
        "inputs": [dict(entry) for entry in inputs],
    }


def stock_features_doc(data: dict[str, Any], *, now: str, generated_by: str) -> okf.OkfDoc:
    """Document OKF d'un ``data`` déjà validé : le texte vient du code, chaque valeur reste celle reçue."""
    ticker, as_of, features = data["ticker"], data["as_of"], data["features"]
    etags = {entry["key"]: entry["etag"] for entry in data["inputs"]}
    sources: dict[str, dict[str, Any]] = {}
    for feature in features.values():
        key = feature["source_key"]
        entry = sources.setdefault(
            key,
            {
                "id": f"input-{feature['source_sha256'][:12]}",
                "title": "Données utilisées pour le calcul",
                "resource": key,
                "sha256": feature["source_sha256"],
                "etag": etags.get(key),
                "published_at": feature["published_at"],
            },
        )
        if clock.parse_datetime(feature["published_at"]) > clock.parse_datetime(entry["published_at"]):
            entry["published_at"] = feature["published_at"]
    rows = [
        f"| {name} | {feature['value'] if feature['value'] is not None else '—'} | {feature['unit']} | "
        f"{feature['currency'] or '—'} | {feature['status']} | {feature['observed_at']} | {feature['published_at']} |"
        for name, feature in sorted(features.items())
    ]
    body = [
        f"# Caractéristiques de {ticker} au {as_of}",
        "",
        "- Calculées selon des règles fixes, à partir des données citées en sources.",
        "",
        "## Valeurs",
        "",
        "| Caractéristique | Valeur | Unité | Devise | Statut | Observée le | Publiée le |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *rows,
        "",
        "## Formules",
        "",
        *[
            f"- {name} : {f['formula']}"
            for name, f in sorted(features.items())
        ],
        "",
        "## Non calculées",
        "",
        *([f"- {name}" for name in data["missing"]] or ["- aucune"]),
        "",
        "## Limites",
        "",
        "- Valeurs calculées selon des règles fixes à partir des données citées; aucune n'est estimée ni rédigée.",
        "- Données passées seulement : ces caractéristiques décrivent l'historique, ce ne sont pas des prévisions.",
        "- Un document n'entre dans une simulation qu'à partir de la publication de sa plus récente entrée.",
        "",
    ]
    return okf.new_doc(
        type="Stock Features",
        title=f"Caractéristiques de {ticker} au {as_of}",
        description=(
            f"{ticker} au {as_of} : {len(features)} caractéristiques calculées selon des règles fixes, "
            f"{len(data['missing'])} non calculées."
        ),
        tags=list(
            dict.fromkeys(
                ["donnees", "caracteristiques", staging.series_slug(ticker), staging.slugify(data["feature_set"], 30)]
            )
        ),
        owners=["alphaforge-finance"],
        sensitivity="public",
        generated_by=generated_by,
        at=now,
        status="stable",
        stale_after=clock.iso(clock.parse_datetime(as_of) + timedelta(days=FEATURES_STALE_DAYS)),
        sources=list(sources.values()),
        data=data,
        body="\n".join(body),
    )


def write_stock_features(
    store: Store, payload: dict[str, Any], *, generated_by: str = "code:finance-features", now: str | None = None
) -> str:
    """Valide et écrit un document Stock Features avec son fichier compagnon; renvoie la clé du document.

    En ajout seulement : ``ConflictError`` si le document de ce titre à cette date existe déjà.
    ``FeaturesError`` (avec ``problems``) si ``payload`` ne suit pas le contrat.
    """
    if not _nonempty_str(generated_by):
        raise FeaturesError(["generated_by is required"])
    data = validate_stock_features(payload)
    doc = stock_features_doc(data, now=now or clock.iso(), generated_by=generated_by)
    key = features_key(data["ticker"], data["as_of"])
    write_document(store, key, doc, create_only=True)
    return key
