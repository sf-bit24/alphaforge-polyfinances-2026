"""Analyseurs des sources publiques, sur des réponses d'exemple (aucun appel réseau)."""

import json
from datetime import UTC, datetime

import pytest

from alphaforge.collect import fetchers
from alphaforge.collect.http import FetchError, http_get


def test_boc_valet_parsing():
    payload = {
        "seriesDetail": {"V39079": {"label": "Target for the overnight rate", "description": "x"}},
        "observations": [
            {"d": "2026-11-10", "V39079": {"v": "2.25"}},
            {"d": "2026-11-12", "V39079": {"v": "2.25"}},
            {"d": "2026-11-11", "V39079": {"v": ""}},
        ],
    }
    url = fetchers.build_boc_url(["V39079"], "2026-11-01")
    assert url == "https://www.bankofcanada.ca/valet/observations/V39079/json?start_date=2026-11-01"
    data = fetchers.parse_boc(payload, ["V39079"], url)["V39079"]
    assert data.label == "Target for the overnight rate" and data.frequency == "daily"
    assert data.observations == [{"date": "2026-11-10", "value": 2.25}, {"date": "2026-11-12", "value": 2.25}]
    assert data.latest == {"date": "2026-11-12", "value": 2.25}


def test_fred_csv_parsing():
    text = "observation_date,DGS10\n2026-11-10,4.98\n2026-11-11,\n2026-11-12,5.10\n2026-11-13,.\n"
    data = fetchers.parse_fred(text, "DGS10", fetchers.build_fred_url("DGS10", "2026-11-01"))
    assert data.observations == [{"date": "2026-11-10", "value": 4.98}, {"date": "2026-11-12", "value": 5.1}]
    monthly = fetchers.parse_fred("DATE,CPIAUCSL\n2026-09-01,330.1\n", "CPIAUCSL", "u")
    assert monthly.frequency == "monthly" and monthly.unit == "index"


def test_yahoo_chart_parsing():
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": "RY.TO",
                        "currency": "CAD",
                        "exchangeName": "TOR",
                        "fullExchangeName": "Toronto",
                        "instrumentType": "EQUITY",
                        "gmtoffset": -18000,
                        "regularMarketTime": 1763067600,
                        "longName": "Royal Bank of Canada",
                    },
                    "timestamp": [1762957800, 1763044200],
                    "indicators": {"quote": [{"close": [190.1, None]}]},
                }
            ],
            "error": None,
        }
    }
    quote = fetchers.parse_yahoo_chart(payload, "RY.TO", "https://query1.finance.yahoo.com/v8/finance/chart/RY.TO")
    assert quote.last_close == 190.1 and quote.last_date == "2025-11-12"
    assert quote.exchange == "Toronto" and quote.instrument_type == "EQUITY"
    assert quote.market_time.endswith("Z")
    with pytest.raises(FetchError):
        fetchers.parse_yahoo_chart({"chart": {"result": None, "error": {"code": "Not Found"}}}, "X", "u")


NEWSWIRE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
<item><title>Sagicor Financial Corrects Dividend Payment Date</title>
<link>https://www.newswire.ca/news-releases/sagicor-1.html</link>
<pubDate>Fri, 14 Nov 2026 21:05:00 +0000</pubDate>
<description><![CDATA[<p>TORONTO /CNW/ - Sagicor Financial Company Ltd. (TSX: SFC) &amp; more...</p>]]>
</description>
<dc:contributor><![CDATA[Sagicor Financial Company Ltd.]]></dc:contributor><dc:language>en</dc:language></item>
<item><title>Perpetua Resources Announces Third Quarter 2026 Financial Results</title>
<link>https://www.newswire.ca/news-releases/perpetua-2.html</link>
<pubDate>Fri, 14 Nov 2026 22:00:00 +0000</pubDate>
<description>Perpetua Resources Corp. (Nasdaq: PPTA) (TSX: PPTA) and Slate (TSX: SLT.U, TSXV: AGET)</description>
<dc:contributor>Perpetua Resources Corp.</dc:contributor><dc:language>en-US</dc:language></item>
<item><title></title><link>https://x</link></item>
</channel></rss>"""


def test_press_release_parsing():
    items = fetchers.parse_press_releases(NEWSWIRE, "newswire_ca_financial")
    assert len(items) == 2
    first, second = items
    assert first.source == "Newswire.ca (Cision)" and first.provider == "newswire_ca_financial"
    assert first.issuer == "Sagicor Financial Company Ltd." and first.tickers == ["SFC.TO"]
    assert first.published_at == "2026-11-14T21:05:00Z" and first.language == "en"
    assert first.snippet.endswith("& more...") and "<p>" not in first.snippet
    assert second.tickers == ["PPTA", "PPTA.TO", "SLT-U.TO", "AGET.V"] and second.language == "en"


def test_listing_tickers_and_feed_allowlist():
    assert fetchers.listing_tickers("Acme (NYSE: BRK.B; CSE: XYZ)") == ["BRK-B", "XYZ.CN"]
    assert fetchers.listing_tickers("no listing here") == []
    with pytest.raises(FetchError):
        fetchers.fetch_press_releases("google_news")


def test_gdelt_parsing():
    text = json.dumps(
        {
            "articles": [
                {
                    "url": "https://example.com/a",
                    "title": "Tariffs hit TSX",
                    "seendate": "20261113T180000Z",
                    "domain": "example.com",
                    "language": "English",
                }
            ]
        }
    )
    items = fetchers.parse_gdelt(text)
    assert items[0].published_at == "2026-11-13T18:00:00Z" and items[0].language == "en"
    assert items[0].published_at_basis == "gdelt_seendate"
    with pytest.raises(FetchError):
        fetchers.parse_gdelt("Please limit requests to one every 5 seconds")
    url = fetchers.build_gdelt_url("TSX", datetime(2026, 11, 7, tzinfo=UTC), datetime(2026, 11, 14, tzinfo=UTC))
    assert "startdatetime=20261107000000" in url and "mode=artlist" in url and "sourcelang" not in url
    url = fetchers.build_gdelt_url(
        "Banque du Canada", datetime(2026, 11, 7, tzinfo=UTC), datetime(2026, 11, 14, tzinfo=UTC), language="fr"
    )
    assert "query=Banque+du+Canada+sourcelang%3Afrench" in url


def test_http_get_only_allows_listed_https_hosts():
    with pytest.raises(FetchError):
        http_get("https://example.com/x")
    with pytest.raises(FetchError):
        http_get("http://www.bankofcanada.ca/valet/")
    for blocked in ("https://news.google.com/rss/search?q=x", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=RY"):
        with pytest.raises(FetchError, match="host not allowed"):
            http_get(blocked)


def test_fetchers_refuse_unlisted_series_and_symbols():
    with pytest.raises(FetchError):
        fetchers.fetch_boc(["SECRET"], "2026-11-01")
    with pytest.raises(FetchError):
        fetchers.fetch_fred("NOPE", "2026-11-01")
    with pytest.raises(FetchError):
        fetchers.fetch_yahoo_chart("rm -rf")


def test_rss_with_entity_declarations_is_refused():
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]>'
        "<rss><channel><item><title>&a;</title></item></channel></rss>"
    )
    with pytest.raises(FetchError):
        fetchers.parse_press_releases(bomb, "newswire_ca")


def test_gzip_bodies_are_bounded_after_decompression():
    import gzip

    from alphaforge.collect import http

    small = gzip.compress(b"x" * 100)
    assert http._gunzip(small, 1000, "u") == b"x" * 100
    with pytest.raises(FetchError):
        http._gunzip(gzip.compress(b"x" * 10_000), 1000, "u")


def test_redirects_must_stay_on_listed_hosts():
    from alphaforge.collect import http

    handler = http._AllowlistRedirects()
    with pytest.raises(FetchError):
        handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example.com/")


class _FakeResponse:
    status = 200
    headers = {"Content-Type": "text/csv"}

    def __init__(self, body=b"ok"):
        self._body = body

    def read(self, _n):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_declared_user_agent_and_fred_fallback(monkeypatch):
    import urllib.error

    from alphaforge.collect import http

    seen = []

    def fake_open(request, timeout):
        agent = request.get_header("User-agent")
        seen.append((request.full_url, agent))
        if "fred" in request.full_url and agent == http.USER_AGENT:
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
        if request.full_url.endswith("/y"):
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, None)
        return _FakeResponse()

    monkeypatch.setattr(http._OPENER, "open", fake_open)
    assert http.USER_AGENT.startswith("AlphaForgeResearchBot/") and "github.com" in http.USER_AGENT
    assert http_get("https://www.bankofcanada.ca/valet/x").status == 200
    assert seen[-1][1] == http.USER_AGENT
    assert http_get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF").status == 200
    assert [agent for _, agent in seen[1:]] == [http.USER_AGENT, "curl/8.0"]
    with pytest.raises(FetchError) as refused:
        http_get("https://www.bankofcanada.ca/valet/y")
    assert refused.value.status == 429 and len(seen) == 4
