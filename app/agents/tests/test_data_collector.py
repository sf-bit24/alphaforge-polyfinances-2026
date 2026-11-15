"""Outils de A5 (``collect.data``) : séries, cotations et dépôt des éléments, sans réseau ni modèle."""

import json
import time

import pytest

from alphaforge.collect import data as data_collector
from alphaforge.collect import fetchers


def series(series_id, provider, observations, frequency="daily"):
    return fetchers.SeriesData(
        series_id=series_id,
        provider=provider,
        label=f"Série {series_id}",
        unit="percent",
        frequency=frequency,
        url=f"https://example.org/{series_id}",
        observations=observations,
    )


def quote(symbol, last_close=101.5, market_time="2026-11-13T21:00:00+00:00"):
    return fetchers.Quote(
        symbol=symbol,
        currency="CAD",
        exchange="TOR",
        instrument_type="EQUITY",
        name=f"Société {symbol}",
        last_close=last_close,
        last_date="2026-11-13" if last_close is not None else None,
        market_time=market_time,
        url=f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        closes=[{"date": f"2026-10-{day:02d}", "value": 100.0 + day} for day in range(1, 31)],
    )


@pytest.fixture
def run(store):
    return data_collector.DataRun(
        run_id="exec-9",
        since="2026-11-08",
        tickers=["RY.TO", "TD.TO", "SHOP.TO"],
        store=store,
        deadline=time.monotonic() + 60,
    )


def call(run, name, **arguments):
    tools = {tool.tool_name: tool for tool in run.tools()}
    return json.loads(tools[name](**arguments))


def test_tools_are_offered_in_a_fixed_order(run):
    assert [tool.tool_name for tool in run.tools()] == [
        "fetch_boc_series",
        "fetch_fred_series",
        "fetch_quotes",
        "stage_data",
        "finish",
    ]


def test_fetch_boc_series_keeps_allowed_ids_once_and_widens_the_window(run, monkeypatch):
    seen = {}

    def fetch_boc(ids, start):
        seen.update(ids=ids, start=start)
        return {"V39079": series("V39079", "boc", [{"date": "2026-11-12", "value": 2.25}])}

    monkeypatch.setattr(fetchers, "fetch_boc", fetch_boc)
    result = call(run, "fetch_boc_series", series_ids=["V39079", "NOPE", "V39079"])
    assert seen == {"ids": ["V39079"], "start": "2026-07-11"}
    assert result == {
        "status": "ok",
        "series": [
            {
                "fetch_id": "s:boc:V39079",
                "series_id": "V39079",
                "label": "Série V39079",
                "unit": "percent",
                "frequency": "daily",
                "observations": 1,
                "in_window": 1,
                "latest": {"date": "2026-11-12", "value": 2.25},
            }
        ],
    }


def test_fetch_boc_series_errors(run, monkeypatch):
    assert call(run, "fetch_boc_series", series_ids=["NOPE"]) == {"status": "error", "reason": "no allowed series"}

    def broken(ids, start):
        raise fetchers.FetchError("valet down")

    monkeypatch.setattr(fetchers, "fetch_boc", broken)
    assert call(run, "fetch_boc_series", series_ids=["V39079"]) == {"status": "error", "reason": "valet down"}
    assert run.warnings == ["boc: valet down"]


def test_fetch_fred_series_reports_each_failure_and_keeps_the_rest(run, monkeypatch):
    def fetch_fred(series_id, start):
        if series_id == "DGS2":
            raise fetchers.FetchError("fred 503")
        return series(series_id, "fred", [{"date": "2026-10-01", "value": 4.1}, {"date": "2026-11-10", "value": 4.0}])

    monkeypatch.setattr(fetchers, "fetch_fred", fetch_fred)
    result = call(run, "fetch_fred_series", series_ids=["DFF", "DGS2", "NOPE", "DFF"])
    assert result["status"] == "ok"
    assert [entry["fetch_id"] for entry in result["series"]] == ["s:fred:DFF"]
    assert result["series"][0]["observations"] == 2 and result["series"][0]["in_window"] == 1
    assert result["errors"] == [{"series_id": "DGS2", "error": "fred 503"}]
    assert run.warnings == ["fred DGS2: fred 503"]


def test_fetch_quotes_keeps_run_tickers_and_lists_failures(run, monkeypatch):
    def fetch_yahoo_chart(symbol):
        if symbol == "TD.TO":
            raise fetchers.FetchError("yahoo 429")
        return quote(symbol)

    monkeypatch.setattr(fetchers, "fetch_yahoo_chart", fetch_yahoo_chart)
    result = call(run, "fetch_quotes", tickers=["RY.TO", "TD.TO", "AAPL", "RY.TO"])
    assert result == {
        "status": "ok",
        "quotes": [
            {
                "fetch_id": "q:RY.TO",
                "symbol": "RY.TO",
                "currency": "CAD",
                "last_close": 101.5,
                "last_date": "2026-11-13",
            }
        ],
        "failed": ["TD.TO"],
    }


def test_every_fetch_tool_stops_when_the_time_budget_is_spent(run):
    run.deadline = time.monotonic() - 1
    expired = {"status": "error", "reason": "time budget exhausted; call finish"}
    assert call(run, "fetch_boc_series", series_ids=["V39079"]) == expired
    assert call(run, "fetch_fred_series", series_ids=["DFF"]) == expired
    assert call(run, "fetch_quotes", tickers=["RY.TO"]) == expired


def test_stage_data_writes_series_and_quotes_and_refuses_the_rest(run, store, monkeypatch):
    monkeypatch.setattr(data_collector.clock, "iso", lambda *_: "2026-11-14T12:00:00+00:00")
    monthly = [{"date": f"2026-{month:02d}-01", "value": 2.0 + month / 10} for month in range(1, 11)]
    run.fetched = {
        "s:boc:CPI": series("STATIC_TOTALCPICHANGE", "boc", monthly, frequency="monthly"),
        "s:fred:EMPTY": series("UNRATE", "fred", []),
        "q:RY.TO": quote("RY.TO"),
        "q:TD.TO": quote("TD.TO", last_close=None),
        "q:SHOP.TO": quote("SHOP.TO", market_time=None),
    }
    result = call(
        run,
        "stage_data",
        items=[
            {"fetch_id": "s:boc:CPI", "note": "  Inflation   annuelle. "},
            {"fetch_id": "s:fred:EMPTY", "note": "Chômage."},
            {"fetch_id": "q:RY.TO", "note": ""},
            {"fetch_id": "q:TD.TO", "note": "x"},
            {"fetch_id": "q:SHOP.TO", "note": "Commerce en ligne."},
            {"fetch_id": "unknown", "note": "x"},
            "not-a-dict",
        ],
    )
    assert result == {
        "results": [
            {"fetch_id": "s:boc:CPI", "status": "ok", "id": "series-static-totalcpichange-2026-10-01"},
            {"fetch_id": "s:fred:EMPTY", "status": "error", "reason": "no observation"},
            {"fetch_id": "q:RY.TO", "status": "ok", "id": "quote-ry-to-2026-11-13"},
            {"fetch_id": "q:TD.TO", "status": "error", "reason": "no observation"},
            {"fetch_id": "q:SHOP.TO", "status": "ok", "id": "quote-shop-to-2026-11-13"},
            {"fetch_id": "unknown", "status": "error", "reason": "unknown fetch_id"},
            {"fetch_id": None, "status": "error", "reason": "unknown fetch_id"},
        ],
        "staged": 3,
    }
    cpi = store.get_json("staging/exec-9/data/series-static-totalcpichange-2026-10-01.json")
    assert cpi == {
        "id": "series-static-totalcpichange-2026-10-01",
        "kind": "series",
        "title": "Série STATIC_TOTALCPICHANGE : 3 % au 2026-10-01",
        "url": "https://example.org/STATIC_TOTALCPICHANGE",
        "source": "Banque du Canada (API Valet)",
        "published_at": "2026-11-14T12:00:00+00:00",
        "observed_at": "2026-10-01",
        "retrieved_at": "2026-11-14T12:00:00+00:00",
        "language": "fr",
        "tickers": [],
        "summary": (
            "Dernière valeur : 3 % (mois de référence 2026-10-01), source Banque du Canada (API Valet). "
            "10 observations retenues. Date de publication exacte non fournie par la source : "
            "la date de récupération en est la borne supérieure. Pertinence (A5) : Inflation annuelle."
        ),
        "data": {
            "series_id": "STATIC_TOTALCPICHANGE",
            "provider": "boc",
            "label": "Série STATIC_TOTALCPICHANGE",
            "unit": "percent",
            "frequency": "monthly",
            "observations": monthly,
            "latest": {"date": "2026-10-01", "value": 3.0},
            "published_at_basis": "retrieved_at_upper_bound",
            "note": "Inflation annuelle.",
            "collected_by": "A5",
            "run_id": "exec-9",
        },
    }
    royal = store.get_json("staging/exec-9/data/quote-ry-to-2026-11-13.json")
    assert royal["title"] == "Clôture de RY.TO : 101,5 CAD au 2026-11-13"
    assert royal["summary"] == (
        "Dernière clôture : 101,5 CAD le 2026-11-13 (TOR), source Yahoo Finance; 22 clôtures quotidiennes."
    )
    assert royal["published_at"] == "2026-11-13T21:00:00+00:00"
    assert royal["data"]["published_at_basis"] == "regular_market_time"
    assert royal["data"]["closes"] == quote("RY.TO").closes[-22:] and royal["tickers"] == ["RY.TO"]
    shopify = store.get_json("staging/exec-9/data/quote-shop-to-2026-11-13.json")
    assert shopify["published_at"] == shopify["retrieved_at"] == "2026-11-14T12:00:00+00:00"
    assert shopify["data"]["published_at_basis"] == "retrieved_at_upper_bound"
    assert shopify["summary"].endswith("22 clôtures quotidiennes. Pertinence (A5) : Commerce en ligne.")
