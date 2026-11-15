"""Outils de collecte déterministes sur des sources publiques sans clé.

Chaque source a une fonction ``build_*_url`` (adresse construite par le code), une fonction ``parse_*``
(testable sans réseau) et une fonction de récupération qui enchaîne les deux. Les dates gardent leur sens :
``published_at`` est la date de publication donnée par la source, ``observed_at`` la date de référence d'une
donnée (le mois d'un IPC, le jour d'une clôture).

Sources et conditions :
- Banque du Canada, API Valet : https://www.bankofcanada.ca/terms/
- FRED, Federal Reserve Bank of St. Louis (``fredgraph.csv``) : https://fred.stlouisfed.org/legal/
- Yahoo Finance (graphique JSON ``v8/finance/chart`` et flux RSS des manchettes) :
  https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html
- Google Actualités (flux RSS de recherche) : https://policies.google.com/terms
- GDELT DOC 2.0 : https://www.gdeltproject.org/about.html#termsofuse
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

from .http import FetchError, http_get

BOC_SERIES = {
    "V39079": "Taux cible du financement à un jour (Banque du Canada)",
    "BD.CDN.2YR.DQ.YLD": "Rendement des obligations du gouvernement du Canada, 2 ans",
    "BD.CDN.10YR.DQ.YLD": "Rendement des obligations du gouvernement du Canada, 10 ans",
    "STATIC_TOTALCPICHANGE": "IPC total du Canada, variation annuelle (%)",
    "FXUSDCAD": "Taux de change USD/CAD (CAD pour 1 USD)",
}
FRED_SERIES = {
    "DFF": "Taux effectif des fonds fédéraux (États-Unis)",
    "DGS2": "Rendement des bons du Trésor américain, 2 ans",
    "DGS10": "Rendement des bons du Trésor américain, 10 ans",
    "CPIAUCSL": "IPC des États-Unis, tous les consommateurs urbains (indice)",
    "UNRATE": "Taux de chômage des États-Unis",
}
MONTHLY_SERIES = {"STATIC_TOTALCPICHANGE", "CPIAUCSL", "UNRATE"}
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,14}$")
_TAGS = re.compile(r"<[^>]+>")


def clean_text(value: str | None, limit: int = 400) -> str:
    if not value:
        return ""
    text = html.unescape(_TAGS.sub(" ", value))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------- séries (Banque du Canada, FRED)
@dataclass
class SeriesData:
    series_id: str
    provider: str
    label: str
    unit: str
    frequency: str
    url: str
    observations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def latest(self) -> dict[str, Any] | None:
        return self.observations[-1] if self.observations else None

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["latest"] = self.latest
        return out


def build_boc_url(series_ids: list[str], start_date: str) -> str:
    joined = ",".join(urllib.parse.quote(s, safe=".") for s in series_ids)
    return f"https://www.bankofcanada.ca/valet/observations/{joined}/json?start_date={start_date}"


def parse_boc(payload: dict[str, Any], series_ids: list[str], url: str) -> dict[str, SeriesData]:
    details = payload.get("seriesDetail") or {}
    out: dict[str, SeriesData] = {}
    for series_id in series_ids:
        detail = details.get(series_id) or {}
        out[series_id] = SeriesData(
            series_id=series_id,
            provider="boc",
            label=detail.get("label") or BOC_SERIES.get(series_id, series_id),
            unit="CAD per USD" if series_id == "FXUSDCAD" else "percent",
            frequency="monthly" if series_id in MONTHLY_SERIES else "daily",
            url=url,
        )
    for row in payload.get("observations") or []:
        day = row.get("d")
        for series_id in series_ids:
            cell = row.get(series_id)
            if not day or not isinstance(cell, dict) or cell.get("v") in (None, ""):
                continue
            try:
                out[series_id].observations.append({"date": day, "value": float(cell["v"])})
            except (TypeError, ValueError):
                continue
    for data in out.values():
        data.observations.sort(key=lambda o: o["date"])
    return out


def fetch_boc(series_ids: list[str], start_date: str) -> dict[str, SeriesData]:
    unknown = [s for s in series_ids if s not in BOC_SERIES]
    if unknown:
        raise FetchError(f"series not allowed: {unknown}")
    url = build_boc_url(series_ids, start_date)
    payload = json.loads(http_get(url).text())
    return parse_boc(payload, series_ids, url)


def build_fred_url(series_id: str, start_date: str) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={urllib.parse.quote(series_id)}&cosd={start_date}"


def parse_fred(text: str, series_id: str, url: str) -> SeriesData:
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    data = SeriesData(
        series_id=series_id,
        provider="fred",
        label=FRED_SERIES.get(series_id, series_id),
        unit="index" if series_id == "CPIAUCSL" else "percent",
        frequency="monthly" if series_id in MONTHLY_SERIES else "daily",
        url=url,
    )
    for row in rows[1:]:
        if len(row) < 2 or not row[0] or row[1] in ("", "."):
            continue
        try:
            data.observations.append({"date": row[0][:10], "value": float(row[1])})
        except ValueError:
            continue
    data.observations.sort(key=lambda o: o["date"])
    return data


def fetch_fred(series_id: str, start_date: str) -> SeriesData:
    if series_id not in FRED_SERIES:
        raise FetchError(f"series not allowed: {series_id}")
    url = build_fred_url(series_id, start_date)
    return parse_fred(http_get(url).text(), series_id, url)


# ---------------------------------------------------------------------- cotations (Yahoo Finance)
@dataclass
class Quote:
    symbol: str
    currency: str | None
    exchange: str | None
    instrument_type: str | None
    name: str | None
    last_close: float | None
    last_date: str | None
    market_time: str | None
    url: str
    closes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_yahoo_chart_url(symbol: str, range_: str = "1mo") -> str:
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}"
        f"?range={range_}&interval=1d"
    )


def parse_yahoo_chart(payload: dict[str, Any], symbol: str, url: str) -> Quote:
    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        error = chart.get("error") or {}
        raise FetchError(f"yahoo chart: {error.get('code') or 'no result'}", url=url)
    result = results[0]
    meta = result.get("meta") or {}
    offset = int(meta.get("gmtoffset") or 0)
    stamps = result.get("timestamp") or []
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes_raw = quotes.get("close") or []
    closes = []
    for stamp, close in zip(stamps, closes_raw, strict=False):
        if close is None:
            continue
        day = datetime.fromtimestamp(int(stamp) + offset, UTC).date().isoformat()
        closes.append({"date": day, "value": round(float(close), 6)})
    market_time = meta.get("regularMarketTime")
    return Quote(
        symbol=meta.get("symbol") or symbol,
        currency=meta.get("currency"),
        exchange=meta.get("fullExchangeName") or meta.get("exchangeName"),
        instrument_type=meta.get("instrumentType"),
        name=meta.get("longName") or meta.get("shortName"),
        last_close=closes[-1]["value"] if closes else None,
        last_date=closes[-1]["date"] if closes else None,
        market_time=_iso(datetime.fromtimestamp(int(market_time), UTC)) if market_time else None,
        url=url,
        closes=closes,
    )


def fetch_yahoo_chart(symbol: str, range_: str = "1mo") -> Quote:
    if not SYMBOL.match(symbol):
        raise FetchError(f"invalid symbol {symbol!r}")
    url = build_yahoo_chart_url(symbol, range_)
    return parse_yahoo_chart(json.loads(http_get(url, max_bytes=1_000_000).text()), symbol, url)


# ---------------------------------------------------------------------- actualités
@dataclass
class NewsCandidate:
    title: str
    url: str
    source: str
    published_at: str
    snippet: str
    language: str
    provider: str
    tickers: list[str] = field(default_factory=list)
    published_at_basis: str = "source"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rss_items(text: str) -> list[ET.Element]:
    # Un flux RSS n'a besoin ni de DTD ni d'entités : on refuse tout document qui en déclare
    # (expansion d'entités, entités externes) avant de l'analyser.
    head = text[:4096].upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in text.upper():
        raise FetchError("RSS with DTD or entity declarations refused")
    try:
        root = ET.fromstring(text)  # noqa: S314 - DTD et entités refusées ci-dessus
    except ET.ParseError as exc:
        raise FetchError(f"invalid RSS: {exc}") from exc
    return root.findall("./channel/item")


def _rss_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _iso(parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return None


def build_yahoo_rss_url(symbol: str) -> str:
    return f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={urllib.parse.quote(symbol)}&region=US&lang=en-US"


def parse_yahoo_rss(text: str, symbol: str) -> list[NewsCandidate]:
    out = []
    for item in _rss_items(text):
        title = clean_text(item.findtext("title"), 300)
        link = (item.findtext("link") or "").strip()
        published = _rss_date(item.findtext("pubDate"))
        if not title or not link:
            continue
        out.append(
            NewsCandidate(
                title=title,
                url=link,
                source="Yahoo Finance",
                published_at=published or "",
                snippet=clean_text(item.findtext("description")),
                language="en",
                provider="yahoo_rss",
                tickers=[symbol],
            )
        )
    return out


def fetch_yahoo_headlines(symbol: str) -> list[NewsCandidate]:
    if not SYMBOL.match(symbol):
        raise FetchError(f"invalid symbol {symbol!r}")
    return parse_yahoo_rss(http_get(build_yahoo_rss_url(symbol), max_bytes=1_000_000).text(), symbol)


def build_google_news_url(query: str, days: int, language: str) -> str:
    q = urllib.parse.quote(f"{query} when:{max(1, min(days, 30))}d")
    if language == "en":
        return f"https://news.google.com/rss/search?q={q}&hl=en-CA&gl=CA&ceid=CA:en"
    return f"https://news.google.com/rss/search?q={q}&hl=fr-CA&gl=CA&ceid=CA:fr"


def parse_google_news(text: str, language: str) -> list[NewsCandidate]:
    out = []
    for item in _rss_items(text):
        raw_title = clean_text(item.findtext("title"), 300)
        link = (item.findtext("link") or "").strip()
        source_el = item.find("source")
        source = clean_text(source_el.text if source_el is not None else "", 120) or "Google Actualités"
        title = raw_title
        if source and raw_title.endswith(f" - {source}"):
            title = raw_title[: -len(source) - 3].strip()
        if not title or not link:
            continue
        out.append(
            NewsCandidate(
                title=title,
                url=link,
                source=source,
                published_at=_rss_date(item.findtext("pubDate")) or "",
                snippet=clean_text(item.findtext("description")),
                language=language,
                provider="google_news",
            )
        )
    return out


def fetch_google_news(query: str, days: int = 7, language: str = "fr") -> list[NewsCandidate]:
    return parse_google_news(http_get(build_google_news_url(query, days, language)).text(), language)


def build_gdelt_url(query: str, start: datetime, end: datetime, max_records: int = 25) -> str:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max(1, min(max_records, 75))),
        "sort": "datedesc",
        "startdatetime": start.astimezone(UTC).strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.astimezone(UTC).strftime("%Y%m%d%H%M%S"),
    }
    return "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)


def parse_gdelt(text: str) -> list[NewsCandidate]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError(f"gdelt: {clean_text(text, 120)}") from exc
    out = []
    for article in payload.get("articles") or []:
        seen = article.get("seendate") or ""
        try:
            published = _iso(datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC))
        except ValueError:
            published = ""
        title = clean_text(article.get("title"), 300)
        url = (article.get("url") or "").strip()
        if not title or not url:
            continue
        language = (article.get("language") or "").lower()
        out.append(
            NewsCandidate(
                title=title,
                url=url,
                source=article.get("domain") or "GDELT",
                published_at=published,
                snippet="",
                language="fr" if language.startswith("fr") else ("en" if language.startswith("en") else language[:2]),
                provider="gdelt",
                published_at_basis="gdelt_seendate",
            )
        )
    return out


def fetch_gdelt(
    query: str, since: datetime, until: datetime | None = None, max_records: int = 25
) -> list[NewsCandidate]:
    end = until or datetime.now(UTC)
    start = max(since, end - timedelta(days=30))
    return parse_gdelt(http_get(build_gdelt_url(query, start, end, max_records), timeout=20).text())
