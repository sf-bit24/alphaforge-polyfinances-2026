"""Catalogue des concepts de tldoole (``concepts.yaml``) et repérage de leurs mentions dans un texte."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CATALOG_PATH = Path(__file__).with_name("concepts.yaml")
LOCALES = ("fr", "en")
ACCENTS = ("blue", "yellow", "green", "coral", "violet")


class CatalogError(ValueError):
    pass


def normalize(text: str | None) -> str:
    """Minuscules, sans accents, apostrophes droites, espaces simples : la forme comparée aux alias."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'").lower()
    return re.sub(r"\s+", " ", text).strip()


def _alias_pattern(alias: str) -> re.Pattern[str]:
    alias = normalize(alias)
    if alias.endswith("*"):
        return re.compile(r"(?<![a-z0-9])" + re.escape(alias[:-1]) + r"[a-z0-9'-]*")
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])")


@dataclass(frozen=True)
class Concept:
    id: str
    label: dict[str, str]
    title: dict[str, str]
    accent: str
    aliases: dict[str, tuple[str, ...]]
    signals: tuple[str, ...]
    key_points: dict[str, tuple[str, ...]]
    fact_hints: tuple[dict[str, Any], ...]
    source_ids: tuple[str, ...]

    def text(self, field: str, locale: str) -> str:
        values = getattr(self, field)
        return values.get(locale) or values["fr"]

    def points(self, locale: str) -> list[str]:
        return list(self.key_points.get(locale) or self.key_points["fr"])

    def patterns(self) -> list[re.Pattern[str]]:
        return [_alias_pattern(alias) for locale in LOCALES for alias in self.aliases.get(locale, ())]

    def mentioned_in(self, text: str) -> list[str]:
        """Alias de ce concept présents dans ``text`` (forme normalisée)."""
        normalized = normalize(text)
        found = []
        for pattern in self.patterns():
            match = pattern.search(normalized)
            if match:
                found.append(match.group(0))
        return found


@dataclass(frozen=True)
class Catalog:
    version: int
    concepts: dict[str, Concept]
    sources: dict[str, dict[str, str]]

    def get(self, concept_id: str) -> Concept | None:
        return self.concepts.get(concept_id)

    def ids(self) -> list[str]:
        return list(self.concepts)

    def source_entries(self, concept: Concept, retrieved_at: str | None = None) -> list[dict[str, Any]]:
        entries = []
        for source_id in concept.source_ids:
            source = self.sources[source_id]
            entry = {"id": source_id, "title": source["title"], "resource": source["resource"]}
            if retrieved_at:
                entry["retrieved_at"] = retrieved_at
            entries.append(entry)
        return entries

    def brief(self, locale: str) -> list[dict[str, str]]:
        """Résumé envoyé aux agents : identifiant, libellé et première phrase de définition."""
        return [
            {"id": c.id, "label": c.text("label", locale), "definition": c.points(locale)[0]}
            for c in self.concepts.values()
        ]


def _localized(raw: Any, field: str, concept_id: str) -> dict[str, str]:
    if not isinstance(raw, dict) or not all(isinstance(raw.get(loc), str) and raw[loc] for loc in LOCALES):
        raise CatalogError(f"{concept_id}: {field} needs fr and en")
    return {loc: raw[loc] for loc in LOCALES}


def parse_catalog(data: dict[str, Any]) -> Catalog:
    sources = data.get("sources") or {}
    if not isinstance(sources, dict):
        raise CatalogError("sources must be a mapping")
    for source_id, source in sources.items():
        if not isinstance(source, dict) or not source.get("title") or not source.get("resource"):
            raise CatalogError(f"source {source_id} needs title and resource")
    concepts: dict[str, Concept] = {}
    for raw in data.get("concepts") or []:
        concept_id = raw.get("id")
        if not isinstance(concept_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", concept_id):
            raise CatalogError(f"invalid concept id {concept_id!r}")
        if concept_id in concepts:
            raise CatalogError(f"duplicate concept {concept_id}")
        accent = raw.get("accent", "blue")
        if accent not in ACCENTS:
            raise CatalogError(f"{concept_id}: unknown accent {accent!r}")
        aliases = raw.get("aliases") or {}
        points = raw.get("key_points") or {}
        for loc in LOCALES:
            if not points.get(loc):
                raise CatalogError(f"{concept_id}: key_points.{loc} is required")
        if len(points["fr"]) != len(points["en"]):
            raise CatalogError(f"{concept_id}: key_points fr and en differ in length")
        source_ids = tuple(raw.get("sources") or ())
        if not source_ids:
            raise CatalogError(f"{concept_id}: at least one source is required")
        for source_id in source_ids:
            if source_id not in sources:
                raise CatalogError(f"{concept_id}: unknown source {source_id}")
        concepts[concept_id] = Concept(
            id=concept_id,
            label=_localized(raw.get("label"), "label", concept_id),
            title=_localized(raw.get("title"), "title", concept_id),
            accent=accent,
            aliases={loc: tuple(aliases.get(loc) or ()) for loc in LOCALES},
            signals=tuple(raw.get("signals") or ()),
            key_points={loc: tuple(points[loc]) for loc in LOCALES},
            fact_hints=tuple(dict(hint) for hint in raw.get("fact_hints") or ()),
            source_ids=source_ids,
        )
    if not concepts:
        raise CatalogError("empty catalog")
    return Catalog(version=int(data.get("version", 1)), concepts=concepts, sources=dict(sources))


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        return parse_catalog(yaml.safe_load(handle))
