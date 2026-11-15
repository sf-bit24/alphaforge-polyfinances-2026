"""Session Web d'un chercheur et consignation des constats (valeurs lues par le code, nombres vérifiés)."""

import hashlib
import json
import time

import pytest

from alphaforge.research import researcher as researcher_mod
from alphaforge.research.packs import pack_hosts
from alphaforge.research.web import ResearchWeb, WebError
from alphaforge.trace import Trace

from ..conftest import ScriptedFactory
from .conftest import KALSHI_MARKET, RSS_FEED, VALET_FX

VALET_URL = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=3"


def make_web(store, packs=("rates-fx-commodities",), resolver=lambda host: True):
    return ResearchWeb(store=store, allowed_hosts=pack_hosts(list(packs)), resolver=resolver)


# ----------------------------------------------------------------------------- web
def test_fetch_archives_and_previews(store, fake_http):
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    web = make_web(store)
    archived = web.fetch(VALET_URL)
    assert archived.host_status == "allowed" and archived.robots_ok is True and archived.fmt == "json"
    document = store.get_json(archived.archive_key)
    assert archived.archive_key.startswith("archive/www.bankofcanada.ca/")
    assert document["url"] == VALET_URL and document["sha256"] == archived.sha256 and "1.4257" in document["body"]
    assert document["headers"] == {"ETag": '"x"'}


def test_hosts_outside_packs_and_html_are_refused(store, fake_http):
    fake_http.add("https://ici.radio-canada.ca/", "<html><body>page</body></html>", content_type="text/html")
    web = make_web(store, packs=("context-press",))
    with pytest.raises(WebError, match="non permis"):
        web.fetch("https://www.wsj.com/x")
    with pytest.raises(WebError, match="HTML"):
        web.fetch("https://ici.radio-canada.ca/page")
    with pytest.raises(WebError, match="https"):
        web.fetch("http://ici.radio-canada.ca/rss")


def test_robots_disallow_is_respected_except_for_the_assumed_exception(store, fake_http):
    fake_http.robots["www.bankofcanada.ca"] = "User-agent: *\nDisallow: /valet/\n"
    fake_http.robots["query1.finance.yahoo.com"] = "User-agent: *\nDisallow: /\n"
    fake_http.add("https://query1.finance.yahoo.com/v8/finance/chart/RY.TO", {"chart": {"result": []}})
    web = make_web(store, packs=("rates-fx-commodities", "markets-companies"))
    with pytest.raises(WebError, match="robots.txt"):
        web.fetch(VALET_URL)
    archived = web.fetch("https://query1.finance.yahoo.com/v8/finance/chart/RY.TO?range=1mo")
    assert archived.host_status == "exception" and archived.robots_ok is False


def test_refusal_blocks_the_host_for_the_session(store, fake_http):
    fake_http.add("https://www.sec.gov/", {"x": 1}, status=403)
    web = make_web(store, packs=("markets-companies",))
    with pytest.raises(WebError, match="403"):
        web.fetch("https://www.sec.gov/files/company_tickers.json")
    with pytest.raises(WebError, match="bloqué"):
        web.fetch("https://www.sec.gov/files/other.json")
    assert (
        web.blocked["www.sec.gov"] == "HTTP 403" and len([c for c in fake_http.calls if "sec.gov/files" in c[1]]) == 1
    )


def test_per_host_request_cap(store, fake_http):
    fake_http.add("https://sdmx.oecd.org/", "a,b\n1,2\n", content_type="text/csv")
    web = make_web(store, packs=("us-intl-macro",))
    for _ in range(3):
        web.fetch("https://sdmx.oecd.org/public/rest/data/x")
    with pytest.raises(WebError, match="plafond"):
        web.fetch("https://sdmx.oecd.org/public/rest/data/x")


def test_quarantine_needs_a_public_host_and_robots(store, fake_http):
    fake_http.robots["data.example.org"] = "User-agent: *\nAllow: /\n"
    fake_http.add("https://data.example.org/api", {"value": 3})
    web = make_web(store, resolver=lambda host: host == "data.example.org")
    with pytest.raises(WebError, match="adresse publique"):
        web.propose_host("https://intranet.local/api", "test")
    entry = web.propose_host("https://data.example.org/api", "found a better series")
    assert entry.robots_allows and entry.robots_status == "parsed"
    archived = web.fetch("https://data.example.org/api")
    assert archived.host_status == "quarantined"
    for _ in range(2):
        web.fetch("https://data.example.org/api")
    with pytest.raises(WebError, match="plafond"):
        web.fetch("https://data.example.org/api")


# ----------------------------------------------------------------------------- constats
def make_run(store, web, **brief_overrides):
    payload = {
        "run_id": "run1",
        "subject": "E2",
        "researcher": "r1",
        "objective": "USD/CAD",
        "packs": ["rates-fx-commodities"],
        **brief_overrides,
    }
    brief = researcher_mod.parse_brief(payload)
    return researcher_mod.ResearcherRun(brief=brief, store=store, web=web, deadline=time.monotonic() + 60)


def test_record_finding_reads_values_and_dates_from_the_response(store, fake_http):
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    web = make_web(store)
    run = make_run(store, web)
    archived = web.fetch(VALET_URL)
    out = run.record_finding(
        {
            "kind": "fact",
            "label": "USD/CAD",
            "claim": "Le dollar américain valait 1,4257 $ CA le 13 novembre 2026.",
            "response_id": archived.response_id,
            "fields": {"value": "observations[2].FXUSDCAD.v"},
            "observation_locator": "observations[2].d",
        }
    )
    finding = run.findings[0]
    assert out["values"] == {"value": "1.4257"} and finding["observation_date"] == "2026-11-13"
    assert finding["publication_basis"] == "retrieved_at_upper_bound"
    assert finding["licence"].startswith("Conditions de la Banque du Canada")
    assert finding["attribution_text"] == "Source : Banque du Canada"
    assert finding["locators"] == {"value": "observations[2].FXUSDCAD.v"}


def test_record_finding_refuses_invented_numbers_bad_locators_and_late_evidence(store, fake_http):
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    web = make_web(store)
    run = make_run(store, web)
    archived = web.fetch(VALET_URL)
    base = {
        "kind": "fact",
        "label": "USD/CAD",
        "response_id": archived.response_id,
        "fields": {"value": "observations[2].FXUSDCAD.v"},
        "observation_locator": "observations[2].d",
    }
    with pytest.raises(researcher_mod.ResearchError, match="nombres absents"):
        run.record_finding({**base, "claim": "Le dollar a gagné 3 % et vaut 1,4257."})
    with pytest.raises(Exception, match="index hors limites"):
        run.record_finding({**base, "claim": "ok", "fields": {"value": "observations[7].FXUSDCAD.v"}})
    with pytest.raises(researcher_mod.ResearchError, match="date d'observation"):
        run.record_finding({**base, "claim": "Valeur lue.", "observation_locator": None})
    past = make_run(store, web, as_of="2020-01-01")
    with pytest.raises(researcher_mod.ResearchError, match="as_of"):
        past.record_finding({**base, "claim": "Valeur lue."})


def test_market_signal_requires_resolution_rules(store, fake_http):
    fake_http.add("https://external-api.kalshi.com/trade-api/v2/markets/", KALSHI_MARKET)
    web = make_web(store, packs=("market-implied",))
    run = make_run(store, web, subject="E6", packs=["market-implied"])
    archived = web.fetch("https://external-api.kalshi.com/trade-api/v2/markets/KXCBDECISIONCANADA-26DEC-H25")
    base = {
        "kind": "signal",
        "label": "Hausse de 25 pb de la BdC le 9 décembre",
        "claim": "Kalshi cote une hausse de 25 pb à 51 cents contre 52.",
        "response_id": archived.response_id,
        "observation_date": "2026-11-14",
    }
    with pytest.raises(researcher_mod.ResearchError, match="resolution_rules"):
        run.record_finding({**base, "fields": {"value": "market.yes_bid", "bid": "market.yes_bid"}})
    out = run.record_finding(
        {
            **base,
            "fields": {
                "value": "market.yes_bid",
                "bid": "market.yes_bid",
                "ask": "market.yes_ask",
                "volume": "market.volume",
                "resolution_rules": "market.rules_primary",
            },
        }
    )
    assert out["values"]["bid"] == "51" and "25 bps" in out["values"]["resolution_rules"]


def test_record_series_and_news(store, fake_http):
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    fake_http.add("https://ici.radio-canada.ca/", RSS_FEED, content_type="application/rss+xml")
    web = make_web(store, packs=("rates-fx-commodities", "context-press"))
    run = make_run(store, web)
    series = web.fetch(VALET_URL)
    out = run.record_series(
        {
            "label": "USD/CAD quotidien",
            "claim": "Le taux est passé de 1,4012 à 1,4257 entre le 11 et le 13 novembre.",
            "response_id": series.response_id,
            "rows": "observations",
            "date_field": "d",
            "value_field": "FXUSDCAD.v",
            "series_id": "FXUSDCAD",
        }
    )
    assert out["points"] == 3 and out["last"] == {"date": "2026-11-13", "value": "1.4257"}
    feed = web.fetch("https://ici.radio-canada.ca/info/rss/info/economie/en-continu")
    news = run.record_finding(
        {
            "kind": "news",
            "label": "Dividende d'Enbridge",
            "claim": "Radio-Canada rapporte une annonce de dividende d'Enbridge.",
            "response_id": feed.response_id,
            "fields": {"title": "items[0].title", "link": "items[0].link"},
            "publication_locator": "items[0].pubDate",
        }
    )
    finding = run.findings[-1]
    assert news["publication_date"] == "2026-11-13T14:00:00Z" and finding["publication_basis"] == "source"
    assert finding["item_url"] == "https://ici.radio-canada.ca/nouvelle/123"
    assert "description" not in finding["values"]


def response_id_for(url, body):
    raw = json.dumps(body).encode()
    return hashlib.sha256(url.encode() + b"\n" + b"" + b"\n" + raw).hexdigest()[:16]


def test_full_research_run_with_a_scripted_model(store, fake_http):
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    brief = researcher_mod.parse_brief(
        {
            "run_id": "run1",
            "subject": "E2",
            "researcher": "r1",
            "objective": "USD/CAD",
            "packs": ["rates-fx-commodities"],
        }
    )
    factory = ScriptedFactory(
        [
            [("tool", "fetch", {"url": VALET_URL})],
            [
                (
                    "tool",
                    "record_series",
                    {
                        "label": "USD/CAD",
                        "claim": "Le dollar américain vaut 1,4257 $ CA au 13 novembre 2026.",
                        "response_id": response_id_for(VALET_URL, VALET_FX),
                        "rows": "observations",
                        "date_field": "d",
                        "value_field": "FXUSDCAD.v",
                    },
                )
            ],
            [("tool", "finish", {"summary": "Taux de change lu.", "gaps": ["aucune donnée intrajournalière"]})],
        ]
    )
    result = researcher_mod.research(
        brief=brief, store=store, trace=Trace("fr"), model_factory=factory, model_id="scripted"
    )
    assert result["findings"] == 1 and result["gaps"] == ["aucune donnée intrajournalière"]
    saved = store.get_json(result["findings_key"])
    assert saved["brief"]["objective"] == "USD/CAD" and saved["findings"][0]["kind"] == "series"
    assert result["warnings"] == [] and result["requests"] == {"www.bankofcanada.ca": 1}
    tools = factory.models[0].calls[0]["tools"]
    assert "record_finding" in tools and "propose_host" in tools and "shell" not in tools


def test_market_odds_are_always_signals(store, fake_http):
    fake_http.add("https://external-api.kalshi.com/trade-api/v2/markets/", KALSHI_MARKET)
    web = make_web(store, packs=("market-implied",))
    run = make_run(store, web, subject="E6", packs=["market-implied"])
    archived = web.fetch("https://external-api.kalshi.com/trade-api/v2/markets/KXCBDECISIONCANADA-26DEC-H25")
    base = {
        "kind": "quote",
        "label": "Hausse de 25 pb",
        "claim": "Offre à 51 cents.",
        "response_id": archived.response_id,
        "observation_date": "2026-11-14",
    }
    with pytest.raises(researcher_mod.ResearchError, match="resolution_rules"):
        run.record_finding({**base, "fields": {"value": "market.yes_bid"}})
    run.record_finding({**base, "fields": {"value": "market.yes_bid", "resolution_rules": "market.rules_primary"}})
    assert run.findings[-1]["kind"] == "signal"
