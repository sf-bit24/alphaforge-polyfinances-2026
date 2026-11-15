"""Lecture des réponses archivées : un seul arbre pour JSON, CSV, XML, RSS et Atom, des aperçus paginés, des
localisateurs et la vérification des nombres.

Principe (énoncé et version 1) : le code produit les chiffres, le modèle les explique. Un chercheur ne recopie
jamais une valeur : il donne un localisateur (``observations[3].FXUSDCAD.v``, ``rows[12].Value``,
``items[0].title``) et le code lit la valeur dans la réponse archivée. A6 relit la même valeur avant d'écrire.

Syntaxe d'un localisateur : une suite de clés séparées par des points, d'index ``[n]`` (à partir de 0) et de
clés entre crochets ``["Date Range"]`` pour les noms qui contiennent un point, une espace ou un crochet.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from typing import Any
from xml.etree import ElementTree  # DTD et entités refusées avant l'analyse (_safe_xml)

PREVIEW_LINES = 120
MAX_VALUE_CHARS = 240
FORMATS = ("json", "csv", "xml", "feed", "text")


class DocumentError(Exception):
    pass


# ----------------------------------------------------------------------------- détection et analyse
def detect_format(content_type: str, body: bytes, url: str = "") -> str:
    media_type = (content_type or "").lower()
    head = body[:600].lstrip().lower()
    if "html" in media_type or head.startswith((b"<!doctype html", b"<html")):
        raise DocumentError("HTML refusé : seule la lecture de flux et d'API est permise (pas de pages HTML)")
    if any(
        marker in media_type for marker in ("spreadsheet", "excel", "zip", "pdf", "octet-stream")
    ) or head.startswith((b"pk\x03\x04", b"%pdf")):
        raise DocumentError("format binaire non pris en charge en phase 1 (XLSX, ZIP, PDF)")
    if "json" in media_type or head.startswith((b"{", b"[")):
        return "json"
    if "csv" in media_type or url.lower().split("?")[0].endswith(".csv"):
        return "csv"
    if "xml" in media_type or "rss" in media_type or "atom" in media_type or head.startswith(b"<"):
        return "feed" if (b"<rss" in head or b"<feed" in head or b"<rdf:rdf" in head) else "xml"
    if "text/plain" in media_type or "text/" in media_type:
        sample = body[:2000].decode("utf-8", errors="replace")
        if sample.count(",") >= 2 and "\n" in sample:
            return "csv"
        return "text"
    raise DocumentError(f"type de contenu non pris en charge : {content_type or 'inconnu'}")


def _safe_xml(text: str) -> ElementTree.Element:
    upper = text[:5000].upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise DocumentError("document XML avec DTD ou entités refusé")
    try:
        return ElementTree.fromstring(text)  # noqa: S314 - DTD et entités refusées ci-dessus
    except ElementTree.ParseError as exc:
        raise DocumentError(f"XML illisible : {exc}") from exc


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag.split(":")[-1]


def _xml_tree(element: ElementTree.Element) -> Any:
    children = list(element)
    attributes = {f"@{_local(name)}": value for name, value in element.attrib.items()}
    text = (element.text or "").strip()
    if not children and not attributes:
        return text
    node: dict[str, Any] = dict(attributes)
    grouped: dict[str, list[Any]] = {}
    for child in children:
        grouped.setdefault(_local(child.tag), []).append(_xml_tree(child))
    for key, values in grouped.items():
        node[key] = values if len(values) > 1 else values[0]
    if text:
        node["#text"] = text
    return node


def _feed_item(entry: ElementTree.Element) -> dict[str, Any]:
    """Champs d'un ``item`` ou d'une ``entry``; un champ répété devient une liste."""
    item: dict[str, Any] = {}
    for child in entry:
        key = _local(child.tag)
        if key == "link" and child.attrib.get("href"):
            value = child.attrib["href"]
        else:
            value = "".join(child.itertext()).strip()
        if key in ("encoded",):
            continue  # content:encoded : corps de l'article, jamais lu
        if key in item:
            if not isinstance(item[key], list):
                item[key] = [item[key]]
            item[key].append(value)
        else:
            item[key] = value
    return item


def _feed_tree(root: ElementTree.Element) -> dict[str, Any]:
    """RSS 2.0, RSS 1.0 (RDF) et Atom ramenés à ``{"title", "items": [{title, link, guid, published, ...}]}``."""
    entries = [element for element in root.iter() if _local(element.tag) in ("item", "entry")]
    items = [_feed_item(entry) for entry in entries]
    channel_title = ""
    for element in root.iter():
        if _local(element.tag) == "title":
            channel_title = "".join(element.itertext()).strip()
            break
    return {"title": channel_title, "items": items}


def _csv_tree(text: str) -> dict[str, Any]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return {"columns": [], "rows": []}
    columns = [name.strip() or f"col{i}" for i, name in enumerate(rows[0])]
    records = []
    for row in rows[1:]:
        records.append({columns[i] if i < len(columns) else f"col{i}": cell.strip() for i, cell in enumerate(row)})
    return {"columns": columns, "rows": records}


def parse_tree(body: bytes, fmt: str) -> Any:
    text = body.decode("utf-8-sig", errors="replace")
    if fmt == "json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise DocumentError(f"JSON illisible : {exc}") from exc
    if fmt == "csv":
        return _csv_tree(text)
    if fmt == "feed":
        return _feed_tree(_safe_xml(text))
    if fmt == "xml":
        root = _safe_xml(text)
        return {_local(root.tag): _xml_tree(root)}
    return {"text": text[:20000]}


# ----------------------------------------------------------------------------- localisateurs
_TOKEN = re.compile(r'\["((?:[^"\\]|\\.)*)"\]|\[(\d+)\]|\.?([^.\[\]]+)')


def parse_locator(locator: str) -> list[str | int]:
    if not isinstance(locator, str) or not locator.strip():
        raise DocumentError("localisateur vide")
    parts: list[str | int] = []
    position = 0
    text = locator.strip()
    while position < len(text):
        match = _TOKEN.match(text, position)
        if not match or match.end() == position:
            raise DocumentError(f"localisateur illisible : {locator!r}")
        quoted, index, key = match.groups()
        if quoted is not None:
            parts.append(quoted.replace('\\"', '"'))
        elif index is not None:
            parts.append(int(index))
        else:
            parts.append(key)
        position = match.end()
    return parts


def resolve(tree: Any, locator: str) -> Any:
    node = tree
    for part in parse_locator(locator):
        if isinstance(part, int):
            if not isinstance(node, list) or part >= len(node):
                raise DocumentError(f"index hors limites dans {locator!r}")
            node = node[part]
        else:
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and len(node) == 1 and isinstance(node[0], dict) and part in node[0]:
                node = node[0][part]
            else:
                raise DocumentError(f"clé absente dans {locator!r} : {part!r}")
    return node


def scalar(value: Any) -> str:
    """Valeur feuille lue au localisateur, en texte; refuse un objet ou une liste."""
    if isinstance(value, dict) and set(value) <= {"#text"} | {k for k in value if k.startswith("@")}:
        value = value.get("#text", "")
    if isinstance(value, dict | list):
        raise DocumentError("le localisateur désigne un objet ou une liste, pas une valeur")
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def extract_rows(tree: Any, rows_locator: str, date_field: str, value_field: str) -> list[dict[str, str]]:
    rows = resolve(tree, rows_locator)
    if not isinstance(rows, list):
        raise DocumentError(f"{rows_locator!r} ne désigne pas une liste")
    readable = []
    for index, row in enumerate(rows):
        try:
            date = scalar(resolve(row, date_field))
            value = scalar(resolve(row, value_field))
        except DocumentError:
            continue
        if date and value not in ("", "-", ".", "NaN", "null", "None"):
            readable.append({"date": date, "value": value, "row": index})
    if not readable:
        raise DocumentError("aucune ligne lisible avec ces champs de date et de valeur")
    return readable


# ----------------------------------------------------------------------------- aperçus
def _flatten(node: Any, path: str, lines: list[str]) -> None:
    if isinstance(node, dict):
        if not node:
            lines.append(f"{path} = {{}}")
        for key, value in node.items():
            safe = key if re.fullmatch(r"[A-Za-z_@#][\w@#:-]*", str(key)) else json.dumps(str(key))
            child = (f"{path}.{safe}" if path else safe) if not safe.startswith('"') else f"{path}[{safe}]"
            _flatten(value, child, lines)
    elif isinstance(node, list):
        lines.append(f"{path} : liste de {len(node)} éléments")
        for index, value in enumerate(node):
            _flatten(value, f"{path}[{index}]", lines)
    else:
        text = scalar(node)
        if len(text) > MAX_VALUE_CHARS:
            text = text[: MAX_VALUE_CHARS - 1] + "…"
        lines.append(f"{path} = {text}")


def preview(tree: Any, offset: int = 0, lines: int = PREVIEW_LINES) -> dict[str, Any]:
    flat: list[str] = []
    _flatten(tree, "", flat)
    offset = max(0, int(offset))
    window = flat[offset : offset + lines]
    return {
        "lines": window,
        "offset": offset,
        "total_lines": len(flat),
        "next_offset": offset + lines if offset + lines < len(flat) else None,
    }


# ----------------------------------------------------------------------------- nombres
_NUMBER = re.compile(r"(?<![\w.])[-−]?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|(?<![\w.])[-−]?\d+(?:[.,]\d+)?")


_UNIT = re.compile(r"^\s?(?:%|\$|€|pb\b|bps?\b|pts?\b|points?\b|[MGk]\$?\b|millions?\b|milliards?\b|x\b|×)", re.I)


def numbers_in(text: str) -> list[tuple[float, int, bool]]:
    """Nombres d'un texte, avec leurs décimales et un drapeau « suivi d'une unité » (%, $, pb, M…)."""
    found = []
    source = text or ""
    for match in _NUMBER.finditer(source):
        raw = match.group(0).replace("−", "-")
        raw = re.sub(r"[   ]", "", raw)
        decimals = 0
        if "," in raw or "." in raw:
            separator = "," if "," in raw else "."
            whole, fraction = raw.split(separator, 1)
            decimals = len(fraction)
            raw = f"{whole}.{fraction}"
        try:
            number = float(raw)
        except ValueError:
            continue
        found.append((number, decimals, bool(_UNIT.match(source[match.end() : match.end() + 12]))))
    return found


def _pool(values: list[str] | tuple[str, ...]) -> list[float]:
    return [number for value in values for number, _, _ in numbers_in(str(value))]


def grounded(text: str, allowed_values: list[str], allowed_dates: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Nombres de ``text`` absents des valeurs lues (arrondi permis à la précision écrite).

    Un nombre suivi d'une unité (« 12 % », « 25 pb », « 1 820 $ ») doit venir d'une valeur lue; les autres
    peuvent aussi venir d'une date (année, mois, jour). Une fraction peut s'écrire en pourcentage (0,51 → 51 %).
    """
    values = _pool(allowed_values)
    dates = [abs(n) for n in _pool(allowed_dates)]
    missing = []
    for number, decimals, with_unit in numbers_in(text):
        tolerance = 0.5 * 10 ** (-decimals) + 1e-9
        if any(abs(number - value) <= tolerance or abs(number - value * 100) <= tolerance for value in values):
            continue
        if not with_unit and decimals == 0 and any(abs(abs(number) - date_part) <= tolerance for date_part in dates):
            continue
        missing.append(f"{number:g}")
    return missing
