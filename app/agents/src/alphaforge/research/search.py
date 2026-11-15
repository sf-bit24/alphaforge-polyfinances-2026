"""Découverte par les catalogues et moteurs de recherche des sources (outil ``search_source`` des chercheurs).

Chaque adaptateur lit un catalogue ou une recherche officielle de la source (toujours par ``ResearchWeb`` : liste
d'hôtes, robots.txt, archive), filtre sur les mots de la requête et rend des pistes avec l'adresse à lire ensuite.
Quand la réponse est déjà le résultat (GDELT, Polymarket, comptes de mentions), l'identifiant de réponse permet de
consigner un constat directement par localisateur.

Vie privée : Hacker News et Bluesky ne servent qu'à compter des mentions. Le texte des publications est lu en
transit, jamais archivé ni rendu au modèle : l'archive ne garde que la requête et le compte (Brain, « Signaux
prospectifs », réseaux sociaux).
"""

from __future__ import annotations

import unicodedata
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

from .. import clock
from .packs import PACKS
from .web import ResearchWeb

MAX_MATCHES = 12


def _fold(text: Any) -> str:
    value = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return value.lower()


def _score(query: str, *fields: Any) -> int:
    terms = [t for t in _fold(query).split() if len(t) > 1]
    haystack = " ".join(_fold(f) for f in fields)
    if not terms:
        return 0
    hits = sum(1 for t in terms if t in haystack)
    return hits if hits == len(terms) else (hits if hits >= max(1, len(terms) - 1) else 0)


def _top(rows: list[tuple[int, dict[str, Any]]], limit: int) -> list[dict[str, Any]]:
    rows = [r for r in rows if r[0] > 0]
    rows.sort(key=lambda r: -r[0])
    return [r[1] for r in rows[: max(1, min(limit, MAX_MATCHES))]]


# ----------------------------------------------------------------------------- Banque du Canada
def valet_groups(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    archived = web.fetch("https://www.bankofcanada.ca/valet/lists/groups/json")
    groups = (archived.tree or {}).get("groups") or {}
    rows = [
        (
            _score(query, name, info.get("label"), info.get("description")),
            {
                "group": name,
                "label": info.get("label"),
                "description": info.get("description"),
                "next": f"https://www.bankofcanada.ca/valet/observations/group/{urllib.parse.quote(name)}/json?recent=5",
            },
        )
        for name, info in groups.items()
        if isinstance(info, dict)
    ]
    return {"response_id": archived.response_id, "matches": _top(rows, limit)}


def valet_series(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    archived = web.fetch("https://www.bankofcanada.ca/valet/lists/series/json")
    series = (archived.tree or {}).get("series") or {}
    rows = [
        (
            _score(query, name, info.get("label"), info.get("description")),
            {
                "series": name,
                "label": info.get("label"),
                "description": info.get("description"),
                "next": f"https://www.bankofcanada.ca/valet/observations/{urllib.parse.quote(name)}/json?recent=12",
            },
        )
        for name, info in series.items()
        if isinstance(info, dict)
    ]
    return {"response_id": archived.response_id, "matches": _top(rows, limit)}


# ----------------------------------------------------------------------------- Statistique Canada
def statcan_tables(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    archived = web.fetch("https://www150.statcan.gc.ca/t1/wds/rest/getAllCubesListLite")
    cubes = archived.tree if isinstance(archived.tree, list) else []
    rows = [
        (
            _score(query, cube.get("productId"), cube.get("cubeTitleEn"), cube.get("cubeTitleFr")),
            {
                "product_id": cube.get("productId"),
                "title_en": cube.get("cubeTitleEn"),
                "title_fr": cube.get("cubeTitleFr"),
                "start": cube.get("cubeStartDate"),
                "end": cube.get("cubeEndDate"),
                "last_release": cube.get("releaseTime"),
                "archived": str(cube.get("archived")) == "1",
                "next": f"statcan_table({cube.get('productId')})",
            },
        )
        for cube in cubes
        if isinstance(cube, dict)
    ]
    return {"response_id": archived.response_id, "matches": _top(rows, limit)}


# ----------------------------------------------------------------------------- portail fédéral
def ckan(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    params = urllib.parse.urlencode({"q": query[:200], "rows": max(1, min(limit, 10))})
    archived = web.fetch(f"https://open.canada.ca/data/api/3/action/package_search?{params}")
    results = ((archived.tree or {}).get("result") or {}).get("results") or []
    matches = []
    for package in results:
        resources = []
        for resource in package.get("resources") or []:
            fmt = str(resource.get("format") or "").upper()
            if fmt in ("HTML", ""):
                continue
            entry = {"id": resource.get("id"), "name": resource.get("name"), "format": fmt, "url": resource.get("url")}
            if resource.get("datastore_active"):
                entry["next"] = "https://open.canada.ca/data/api/3/action/datastore_search?" + urllib.parse.urlencode(
                    {"resource_id": resource.get("id"), "limit": 50}
                )
            resources.append(entry)
        matches.append(
            {
                "package": package.get("name"),
                "title": package.get("title"),
                "organization": (package.get("organization") or {}).get("title"),
                "modified": package.get("metadata_modified"),
                "resources": resources[:8],
            }
        )
    return {
        "response_id": archived.response_id,
        "matches": matches,
        "note": "metadata_modified is a catalogue date, not a publication date; resource URLs on other hosts may "
        "not be allowed.",
    }


# ----------------------------------------------------------------------------- SEC
_EDGAR_ALIASES = {"CNR.TO": "CNI", "CNR": "CNI"}


def edgar_company(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    archived = web.fetch("https://www.sec.gov/files/company_tickers.json")
    table = archived.tree if isinstance(archived.tree, dict) else {}
    wanted = query.strip().upper()
    ticker = _EDGAR_ALIASES.get(wanted, wanted.removesuffix(".TO").removesuffix(".V"))
    rows = []
    for row in table.values():
        if not isinstance(row, dict):
            continue
        exact = str(row.get("ticker", "")).upper() == ticker
        score = 100 if exact else _score(query, row.get("title"))
        cik10 = f"{int(row.get('cik_str', 0)):010d}"
        rows.append(
            (
                score,
                {
                    "ticker": row.get("ticker"),
                    "name": row.get("title"),
                    "cik": cik10,
                    "next": [
                        f"https://data.sec.gov/submissions/CIK{cik10}.json",
                        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",
                    ],
                },
            )
        )
    return {
        "response_id": archived.response_id,
        "matches": _top(rows, limit),
        "note": "ATD and CSU are not in EDGAR; CN files as CNI. Never use the frames endpoint.",
    }


# ----------------------------------------------------------------------------- marchés prédictifs
def kalshi_series(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    archived = web.fetch("https://external-api.kalshi.com/trade-api/v2/series?category=Economics")
    series = (archived.tree or {}).get("series") or []
    rows = [
        (
            _score(query, s.get("ticker"), s.get("title"), " ".join(s.get("tags") or [])),
            {
                "series": s.get("ticker"),
                "title": s.get("title"),
                "settlement_sources": [x.get("name") for x in s.get("settlement_sources") or [] if isinstance(x, dict)],
                "contract_terms_url": s.get("contract_terms_url"),
                "next": "https://external-api.kalshi.com/trade-api/v2/markets?"
                + urllib.parse.urlencode({"series_ticker": s.get("ticker"), "status": "open"}),
            },
        )
        for s in series
        if isinstance(s, dict)
    ]
    return {
        "response_id": archived.response_id,
        "matches": _top(rows, limit),
        "note": "Kalshi Developer Agreement not read yet: findings are flagged. Record rules_primary verbatim.",
    }


def polymarket(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    params = urllib.parse.urlencode({"q": query[:200], "limit_per_type": max(1, min(limit, 8))})
    archived = web.fetch(f"https://gamma-api.polymarket.com/public-search?{params}")
    events = (archived.tree or {}).get("events") or []
    matches = []
    for i, event in enumerate(events):
        markets = []
        for j, market in enumerate(event.get("markets") or []):
            markets.append(
                {
                    "locator": f"events[{i}].markets[{j}]",
                    "question": market.get("question"),
                    "slug": market.get("slug"),
                    "closed": market.get("closed"),
                    "next": f"https://gamma-api.polymarket.com/markets?slug={urllib.parse.quote(str(market.get('slug')))}",
                }
            )
        matches.append({"event": event.get("title"), "slug": event.get("slug"), "markets": markets[:6]})
    return {
        "response_id": archived.response_id,
        "matches": matches[:limit],
        "note": "Read the market (next) for outcomePrices, volume and description (= resolution rules).",
    }


# ----------------------------------------------------------------------------- catalogues SDMX
def _text(node: Any) -> str:
    if isinstance(node, list):
        for entry in node:
            if isinstance(entry, dict) and entry.get("@lang") == "en":
                return str(entry.get("#text") or "")
        node = node[0] if node else ""
    if isinstance(node, dict):
        return str(node.get("#text") or "")
    return str(node or "")


def oecd_dataflows(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    archived = web.fetch("https://sdmx.oecd.org/public/rest/dataflow/all/all/latest?detail=allstubs")
    root = archived.tree.get("Structure", {}) if isinstance(archived.tree, dict) else {}
    flows = ((root.get("Structures") or {}).get("Dataflows") or {}).get("Dataflow") or []
    flows = flows if isinstance(flows, list) else [flows]
    rows = []
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        name = _text(flow.get("Name"))
        agency, fid, version = flow.get("@agencyID"), flow.get("@id"), flow.get("@version")
        rows.append(
            (
                _score(query, fid, name),
                {
                    "agency": agency,
                    "id": fid,
                    "version": version,
                    "name": name,
                    "next": f"https://sdmx.oecd.org/public/rest/data/{agency},{fid},{version}/all?"
                    "lastNObservations=1&format=csvfilewithlabels (narrow the key first)",
                },
            )
        )
    return {"response_id": archived.response_id, "matches": _top(rows, limit), "note": "OECD: 3 requests per session."}


def imf_dataflows(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    archived = web.fetch("https://api.imf.org/external/sdmx/3.0/structure/dataflow/*/*/+?detail=allstubs")
    flows = ((archived.tree or {}).get("data") or {}).get("dataflows") or []
    rows = [
        (
            _score(query, f.get("id"), f.get("name")),
            {
                "agency": f.get("agencyID"),
                "id": f.get("id"),
                "version": f.get("version"),
                "name": f.get("name"),
                "vintage": "VINTAGE" in str(f.get("id")),
                "next": f"https://api.imf.org/external/sdmx/2.1/data/{f.get('agencyID')},{f.get('id')}/{{KEY}}?startPeriod=YYYY-MM",
            },
        )
        for f in flows
        if isinstance(f, dict)
    ]
    return {"response_id": archived.response_id, "matches": _top(rows, limit)}


# ----------------------------------------------------------------------------- presse et attention
def gdelt(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    end = clock.utcnow()
    start = end - timedelta(days=30)
    params = urllib.parse.urlencode(
        {
            "query": query[:250],
            "mode": "artlist",
            "format": "json",
            "maxrecords": str(max(5, min(limit * 2, 50))),
            "sort": "datedesc",
            "startdatetime": start.strftime("%Y%m%d%H%M%S"),
            "enddatetime": end.strftime("%Y%m%d%H%M%S"),
        }
    )
    archived = web.fetch(f"https://api.gdeltproject.org/api/v2/doc/doc?{params}")
    articles = (archived.tree or {}).get("articles") or [] if isinstance(archived.tree, dict) else []
    matches = [
        {
            "locator": f"articles[{i}]",
            "title": a.get("title"),
            "domain": a.get("domain"),
            "language": a.get("language"),
            "seendate": a.get("seendate"),
        }
        for i, a in enumerate(articles[: max(1, min(limit * 2, 50))])
        if isinstance(a, dict)
    ]
    return {
        "response_id": archived.response_id,
        "matches": matches,
        "count": len(articles),
        "note": "Add sourcelang:french to the query for French media. seendate is detection time, not publication.",
    }


def wikipedia(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    lang, _, title = query.partition(":") if query[:3] in ("fr:", "en:") else ("fr", ":", query)
    lang = lang if lang in ("fr", "en") else "fr"
    params = urllib.parse.urlencode(
        {"action": "query", "titles": title.strip()[:200], "redirects": 1, "format": "json"}
    )
    archived = web.fetch(f"https://{lang}.wikipedia.org/w/api.php?{params}")
    pages = ((archived.tree or {}).get("query") or {}).get("pages") or {}
    end = clock.today() - timedelta(days=1)
    start = end - timedelta(days=60)
    matches = []
    for page in pages.values():
        if not isinstance(page, dict) or "missing" in page:
            continue
        canonical = str(page.get("title"))
        encoded = urllib.parse.quote(canonical.replace(" ", "_"), safe="")
        matches.append(
            {
                "canonical_title": canonical,
                "next": "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
                f"{lang}.wikipedia/all-access/user/{encoded}/daily/{start:%Y%m%d}/{end:%Y%m%d}",
            }
        )
    return {"response_id": archived.response_id, "matches": matches, "note": "Query as 'fr:Title' or 'en:Title'."}


def hn_mentions(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    since = int((datetime.now(UTC) - timedelta(days=7)).timestamp())
    params = urllib.parse.urlencode(
        {"query": query[:200], "tags": "story", "numericFilters": f"created_at_i>{since}", "hitsPerPage": 0}
    )
    url = f"https://hn.algolia.com/api/v1/search_by_date?{params}"
    archived = web.fetch(url)  # hitsPerPage=0 : la réponse ne contient que le compte, aucun texte
    count = (archived.tree or {}).get("nbHits") if isinstance(archived.tree, dict) else None
    return {
        "response_id": archived.response_id,
        "count_locator": "nbHits",
        "count": count,
        "window": "7 days",
        "note": "Mentions in story titles over 7 days. Aggregate only.",
    }


def bluesky_mentions(web: ResearchWeb, query: str, limit: int) -> dict[str, Any]:
    since = (clock.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = urllib.parse.urlencode({"q": query[:200], "since": since, "limit": 100})
    url = f"https://api.bsky.app/xrpc/app.bsky.feed.searchPosts?{params}"
    tree = web.read_transient(url)
    posts = tree.get("posts") or [] if isinstance(tree, dict) else []
    count = len(posts)
    del posts, tree  # lu en transit seulement : aucun texte ni pseudonyme n'est gardé
    archived = web.derived(
        url,
        {
            "query": query[:200],
            "since": since,
            "count": count,
            "capped": count >= 100,
            "retrieved_at": clock.iso(),
            "method": "searchPosts, posts counted in transit, content discarded",
        },
    )
    return {"response_id": archived.response_id, "count_locator": "count", "count": count, "window": "24 hours"}


def feeds(web: ResearchWeb, query: str, limit: int, packs: tuple[str, ...] = ()) -> dict[str, Any]:
    rows = []
    for name in packs:
        for title, url in PACKS[name].feeds:
            rows.append({"pack": name, "feed": title, "next": url})
    matched = [r for r in rows if not query.strip() or _score(query, r["feed"], r["pack"]) > 0]
    return {"matches": matched or rows}


ADAPTERS = {
    "valet_groups": valet_groups,
    "valet_series": valet_series,
    "statcan_tables": statcan_tables,
    "ckan": ckan,
    "edgar_company": edgar_company,
    "kalshi_series": kalshi_series,
    "polymarket": polymarket,
    "oecd_dataflows": oecd_dataflows,
    "imf_dataflows": imf_dataflows,
    "gdelt": gdelt,
    "wikipedia": wikipedia,
    "hn_mentions": hn_mentions,
    "bluesky_mentions": bluesky_mentions,
    "feeds": feeds,
}
