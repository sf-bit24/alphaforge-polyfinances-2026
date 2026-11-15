"""Constats → éléments de collecte (``staging/<run_id>/experts/<sujet>/<id>.json``).

Le format reste celui de la section 4 de CONTRACTS.md (``id``, ``kind``, ``title``, ``url``, ``source``, dates,
``summary``, ``data``); la recherche ajoute les types ``fact``, ``signal``, ``filing`` et ``brief`` et deux blocs
facultatifs : ``data.provenance`` (champs retenus par l'équipe le 2026-11-15) et ``data.market`` (cotes).
"""

from __future__ import annotations

from typing import Any

from ..collect import staging
from .packs import HOSTS

MARKET_FIELDS = (
    "venue_market_id",
    "bid",
    "ask",
    "last",
    "volume",
    "open_interest",
    "resolution_rules",
    "settlement_source",
    "bar_interval",
)
MARKET_HOSTS = frozenset({"external-api.kalshi.com", "gamma-api.polymarket.com", "clob.polymarket.com"})
HIGH_VOLUME = 1_000_000
MAX_SPREAD = 0.02


def _source_name(finding: dict[str, Any]) -> str:
    values = finding.get("values") or {}
    if finding.get("kind") == "news" and values.get("domain"):
        return str(values["domain"])[:80]
    info = HOSTS.get(finding.get("host") or "")
    if info is not None:
        return info.attribution.removeprefix("Source : ").split(",")[0][:80]
    return str(finding.get("host"))


def _price(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number / 100 if number > 1 else number  # Kalshi en cents, Polymarket en fraction


def quality_tier(market: dict[str, Any]) -> str:
    bid, ask = _price(market.get("bid")), _price(market.get("ask"))
    try:
        volume = float(str(market.get("volume") or 0))
    except ValueError:
        volume = 0.0
    if bid is not None and ask is not None and volume >= HIGH_VOLUME and ask - bid <= MAX_SPREAD:
        return "high"
    if volume >= 50_000:
        return "medium"
    return "illustrative"


def item_id(finding: dict[str, Any]) -> str:
    kind = finding["kind"]
    if kind == "news":
        return staging.news_item_id(finding.get("item_url") or finding["url"])
    basis = "|".join(
        str(x)
        for x in (
            finding.get("url"),
            sorted((finding.get("locators") or {}).items()),
            finding.get("series_spec"),
            finding.get("observation_date"),
        )
    )
    return f"{kind}-{staging.short_hash(basis)}"


def provenance(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": finding.get("finding_id"),
        "researcher": f"{finding.get('subject')}-{finding.get('researcher')}",
        "observation_date": finding.get("observation_date"),
        "observation_basis": finding.get("observation_basis"),
        "publication_datetime_utc": finding.get("publication_date"),
        "publication_basis": finding.get("publication_basis"),
        "retrieved_at": finding.get("retrieved_at"),
        "source_url": finding.get("item_url") or finding.get("url"),
        "endpoint": finding.get("url"),
        "host": finding.get("host"),
        "host_status": finding.get("host_status"),
        "robots_ok_at_fetch": finding.get("robots_ok_at_fetch"),
        "response_id": finding.get("response_id"),
        "archive_key": finding.get("archive_key"),
        "locators": finding.get("locators") or {},
        "series_spec": finding.get("series_spec"),
        "licence": finding.get("licence"),
        "licence_url": finding.get("licence_url"),
        "attribution_text": finding.get("attribution_text"),
        "licence_note": finding.get("licence_note"),
        "as_of": finding.get("as_of"),
        "adjustment": "raw" if finding.get("host") == "query1.finance.yahoo.com" else None,
    }


def build_item(finding: dict[str, Any], *, summary: str | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    kind = finding["kind"]
    values = dict(finding.get("values") or {})
    data: dict[str, Any] = {
        "run_id": finding.get("run_id"),
        "subject": finding.get("subject"),
        "collected_by": f"{finding.get('subject')} ({finding.get('researcher')})",
        "label": finding.get("label"),
        "unit": finding.get("unit"),
        "values": values,
        "published_at_basis": finding.get("publication_basis"),
        "provenance": provenance(finding),
    }
    if kind == "series":
        data.update(
            series_id=finding.get("series_id"),
            frequency=finding.get("frequency"),
            observations=finding.get("observations") or [],
        )
    elif kind == "quote":
        data.update(
            symbol=(finding.get("issuers") or [finding.get("label")])[0],
            observations=[{"date": (finding.get("observation_date") or "")[:10], "value": values.get("value")}],
        )
    elif kind in ("fact", "signal"):
        data.update(value=values.get("value"))
    if finding.get("host") in MARKET_HOSTS:
        market = {name: values.get(name) for name in MARKET_FIELDS if values.get(name) not in (None, "")}
        market["venue"] = finding.get("host")
        market["quality_tier"] = quality_tier(market)
        data["market"] = market
    if tags:
        data["tags"] = [staging.slugify(str(t), 30) for t in tags][:3]
    title = finding.get("label") or values.get("title") or kind
    if kind == "news":
        title = values.get("title") or title
    return {
        "id": item_id(finding),
        "kind": kind,
        "title": str(title)[:200],
        "url": finding.get("item_url") or finding["url"],
        "source": _source_name(finding),
        "published_at": finding.get("publication_date"),
        "observed_at": finding.get("observation_date"),
        "retrieved_at": finding.get("retrieved_at"),
        "language": values.get("language") if kind == "news" else None,
        "tickers": finding.get("issuers") or [],
        "summary": " ".join(str(summary or finding.get("claim") or "").split())[:600],
        "data": data,
    }


def allowed_numbers(item: dict[str, Any]) -> list[str]:
    """Valeurs lues auxquelles un texte fondé sur cet élément peut emprunter des nombres."""
    data = item.get("data") or {}
    out = [str(v) for v in (data.get("values") or {}).values()]
    out += [str(o.get("value")) for o in data.get("observations") or [] if isinstance(o, dict)]
    return out


def allowed_dates(item: dict[str, Any]) -> list[str]:
    """Dates de cet élément dont un texte peut citer l'année, le mois ou le jour (bornes d'une série seulement)."""
    data = item.get("data") or {}
    observations = [o for o in data.get("observations") or [] if isinstance(o, dict) and o.get("date")]
    out = [str(o["date"])[:10] for o in observations[:1] + observations[-1:]]
    for key in ("observed_at", "published_at"):
        if item.get(key):
            out.append(str(item[key])[:10])
    return [d.replace("-", "/") for d in out]
