"""Liens et symboles des documents d'une base OKF, pour ``kb.list`` (CONTRACTS.md, section 3.2).

``links`` : les documents de la même base vers lesquels pointe le corps, par ses liens Markdown. Un lien se lit
relatif au dossier du document (``../methodologie/x.md``, comme dans les seeds), sinon relatif à la racine de la base
(``faits/<source>/<date>-<hash>.md``, comme dans l'index et les synthèses de recherche). Un lien vers l'extérieur,
vers un document absent de la liste ou vers le document lui-même ne compte pas. Une base ne pointe jamais vers une
autre : seules ses propres clés sont candidates.

``tickers`` : les symboles canoniques dont parle le document. D'abord ceux que ses champs déclarent (``data.ticker``,
``data.symbol``, ``data.tickers``), puis ses tags (frontmatter et ``data.tags``) qui nomment un symbole déclaré
ailleurs dans la base. La forme seule ne suffit pas à un tag : ``taux``, ``faits`` ou ``e2`` ont celle d'un symbole.
"""

from __future__ import annotations

import posixpath
import re
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .. import okf

_MARKDOWN_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


@dataclass(frozen=True)
class Relations:
    """Ce qu'un document dit de ses voisins, avant le croisement avec le reste de la liste."""

    links: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)
    tag_tickers: list[str] = field(default_factory=list)


def base_root(key: str) -> str:
    """Racine de la base d'une clé : ``general/`` ou ``clients/<client_id>/``."""
    parts = key.split("/")
    depth = 2 if parts[0] == "clients" else 1
    return "/".join(parts[:depth]) + "/"


def _link_path(raw: str) -> str | None:
    """Chemin d'un lien Markdown, sans ancre ni paramètres; ``None`` pour une adresse externe ou absolue."""
    path = urllib.parse.unquote(raw.split("#", 1)[0].split("?", 1)[0]).strip()
    if not path or path.startswith("/") or _SCHEME.match(path):
        return None
    return path


def resolve_link(key: str, raw: str, known: set[str]) -> str | None:
    """Clé visée par un lien du document ``key`` : relative à son dossier, sinon à la racine de sa base."""
    path = _link_path(raw)
    if path is None:
        return None
    root = base_root(key)
    candidates = (
        posixpath.normpath(posixpath.join(posixpath.dirname(key), path)),
        posixpath.normpath(root + path),
    )
    # Un lien ne sort jamais de sa base, même si ``known`` en contenait une autre.
    return next((candidate for candidate in candidates if candidate.startswith(root) and candidate in known), None)


def document_links(key: str, body: str, known: set[str]) -> list[str]:
    """Documents de ``known`` vers lesquels pointe le corps, dans l'ordre du texte et sans doublon."""
    found: list[str] = []
    for raw in _MARKDOWN_LINK.findall(body):
        target = resolve_link(key, raw, known)
        if target is not None and target != key and target not in found:
            found.append(target)
    return found


def _canonical(values: Iterable[Any]) -> list[str]:
    tickers: list[str] = []
    for value in values:
        ticker = okf.canonical_ticker(value)
        if ticker is not None and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def declared_tickers(data: dict[str, Any]) -> list[str]:
    """Symboles que les champs du document déclarent : ``ticker``, ``symbol``, puis ``tickers``."""
    return _canonical([data.get("ticker"), data.get("symbol"), *_as_list(data.get("tickers"))])


def tag_candidates(frontmatter: dict[str, Any]) -> list[str]:
    """Tags du frontmatter et de ``data.tags`` qui ont la forme d'un symbole; la base doit encore les confirmer."""
    data = frontmatter.get("data")
    data_tags = _as_list(data.get("tags")) if isinstance(data, dict) else []
    return _canonical([*_as_list(frontmatter.get("tags")), *data_tags])


def relations(key: str, doc: okf.OkfDoc, known: set[str]) -> Relations:
    return Relations(
        links=document_links(key, doc.body, known),
        tickers=declared_tickers(doc.data),
        tag_tickers=tag_candidates(doc.frontmatter),
    )


def attach(described: list[tuple[dict[str, Any], Relations]]) -> list[dict[str, Any]]:
    """Ajoute ``links`` et ``tickers`` à chaque élément de la liste.

    Un lien ne garde que les documents listés (une note retirée n'y est plus); un tag ne devient un symbole que si un
    document de la liste le déclare par ses champs.
    """
    listed = {item["key"] for item, _ in described}
    declared = {ticker for _, found in described for ticker in found.tickers}
    items = []
    for item, found in described:
        confirmed = [ticker for ticker in found.tag_tickers if ticker in declared and ticker not in found.tickers]
        links = [target for target in found.links if target in listed]
        items.append({**item, "links": links, "tickers": [*found.tickers, *confirmed]})
    return items
