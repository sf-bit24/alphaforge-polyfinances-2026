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


RSS = """<?xml version="1.0"?><rss><channel>
<item><title>RBC beats estimates</title><link>https://finance.yahoo.com/news/rbc-1.html</link>
<description>&lt;p&gt;Royal Bank reported &amp;amp; more&lt;/p&gt;</description>
<pubDate>Thu, 13 Nov 2026 14:00:00 +0000</pubDate></item>
<item><title></title><link>https://x</link></item>
</channel></rss>"""


def test_yahoo_rss_parsing():
    items = fetchers.parse_yahoo_rss(RSS, "RY.TO")
    assert len(items) == 1
    item = items[0]
    assert item.published_at == "2026-11-13T14:00:00Z" and item.tickers == ["RY.TO"]
    assert item.snippet == "Royal Bank reported & more" and item.provider == "yahoo_rss"


GOOGLE = """<?xml version="1.0"?><rss><channel>
<item><title>La Banque du Canada maintient son taux - Radio-Canada</title>
<link>https://news.google.com/rss/articles/abc?oc=5</link><pubDate>Wed, 12 Nov 2026 15:30:00 GMT</pubDate>
<source url="https://ici.radio-canada.ca">Radio-Canada</source></item>
</channel></rss>"""


def test_google_news_parsing():
    items = fetchers.parse_google_news(GOOGLE, "fr")
    assert items[0].title == "La Banque du Canada maintient son taux"
    assert items[0].source == "Radio-Canada" and items[0].published_at == "2026-11-12T15:30:00Z"
    url = fetchers.build_google_news_url("Banque du Canada", 7, "fr")
    assert url.startswith("https://news.google.com/rss/search?q=Banque%20du%20Canada%20when%3A7d&hl=fr-CA")


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
    assert "startdatetime=20261107000000" in url and "mode=artlist" in url


def test_http_get_only_allows_listed_https_hosts():
    with pytest.raises(FetchError):
        http_get("https://example.com/x")
    with pytest.raises(FetchError):
        http_get("http://www.bankofcanada.ca/valet/")


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
        fetchers.parse_yahoo_rss(bomb, "RY.TO")


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
