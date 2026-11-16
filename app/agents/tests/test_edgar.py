"""Fondamentaux EDGAR (``collect.edgar``) : réponses ``companyfacts`` simulées, aucun appel réseau.

A5 les construit par le code, A6 les relit avec le lecteur du volet finance et écrit ``general/societes/``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alphaforge import clock, okf
from alphaforge.collect import data as data_collector
from alphaforge.collect import edgar, fundamentals, http, staging, supervisor
from alphaforge.finance.strategy.okf_facts import fundamentals_facts, parse_company_fundamentals
from alphaforge.trace import Trace

from .conftest import ScriptedFactory

SEEDS = Path(__file__).resolve().parents[2] / "knowledge" / "general" / "societes"
NOW = "2026-11-15T12:00:00Z"


def row(val, end, accn, filed, form="10-Q", start=None):
    out = {"end": end, "val": val, "accn": accn, "fy": 2026, "fp": "Q3", "form": form, "filed": filed}
    if start:
        out["start"] = start
    return out


def companyfacts(name="Apple Inc."):
    """10-Q du T3 2026 (déposé le 2026-10-30), 10-Q du T3 2025 (2025-10-31) et ses comparatifs."""
    q26, q25 = ("2026-06-28", "2026-09-27"), ("2025-06-29", "2025-09-28")
    return {
        "entityName": name,
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            row(100e6, q26[1], "A-26", "2026-10-30", start=q26[0]),
                            row(80e6, q25[1], "A-26", "2026-10-30", start=q25[0]),  # comparatif, déposé plus tard
                            row(79e6, q25[1], "A-25", "2025-10-31", start=q25[0]),  # valeur d'origine
                            row(270e6, q26[1], "A-26", "2026-10-30", start="2025-12-28"),  # 9 mois : non retenu
                            row(999e6, q26[1], "A-26X", "2026-12-01", form="10-Q/A", start=q26[0]),  # amendement
                        ]
                    }
                },
                "EarningsPerShareDiluted": {
                    "units": {
                        "USD/shares": [
                            row(1.5, q26[1], "A-26", "2026-10-30", start=q26[0]),
                            row(1.2, q25[1], "A-25", "2025-10-31", start=q25[0]),
                        ]
                    }
                },
                "NetIncomeLoss": {"units": {"JPY": [row(5e9, q26[1], "A-26", "2026-10-30", start=q26[0])]}},
                "Assets": {
                    "units": {
                        "USD": [
                            row(350e9, q26[1], "A-26", "2026-10-30"),
                            row(340e9, q25[1], "A-25", "2025-10-31"),
                        ]
                    }
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {"units": {"shares": [row(1, q26[1], "A-26", "2026-10-30")]}}
            },
        },
    }


def build(ticker="AAPL", cik=320193, payloads=None):
    return edgar.build_fundamentals(edgar.Issuer(ticker, cik, "Apple Inc."), payloads or [companyfacts()], NOW)


def candidate(built, key="staging/run1/data/x.json"):
    item = edgar.fundamentals_item(built, run_id="run1", retrieved_at=NOW)
    return supervisor.Candidate(key=key, item=item, target=edgar.target_key(built.ticker))


def test_document_is_read_by_the_finance_reader_point_in_time():
    doc = fundamentals.fundamentals_doc(candidate(build()), NOW)
    cf = parse_company_fundamentals(okf.render(doc), "general/societes/aapl.md", "e1")
    assert cf.reporting_currency == "USD" and cf.accounting_standard == "US GAAP"
    assert [p.kind for p in cf.periods] == ["quarter", "quarter"]  # 9 mois et amendement écartés
    latest, older = cf.periods
    assert latest.values == {"revenue": 100.0, "diluted_eps": 1.5} and str(latest.published_at) == "2026-10-30"
    assert latest.prior_year.values == {"revenue": 80.0}  # comparatif du même dépôt, publié avec lui
    assert older.values["revenue"] == 79.0  # valeur d'origine, pas le comparatif publié un an plus tard
    # 10-Q accepté après as_of : ignoré par le lecteur du volet finance.
    facts = {f.fact_id: f for f in fundamentals_facts(cf, "2026-10-15")}
    assert facts["okf.fund.AAPL.revenue"].value == 79.0
    assert str(facts["okf.fund.AAPL.revenue"].published) == "2025-10-31"
    assert fundamentals_facts(cf, "2026-10-30")[0].value == 100.0
    # Le compagnon de la Knowledge Base date le document par sa publication la plus récente.
    meta = okf.kb_metadata("general/societes/aapl.md", doc.frontmatter)
    assert meta["metadataAttributes"]["published_epoch"]["value"]["numberValue"] > 0


def test_unknown_unit_is_skipped_never_converted():
    built = build()
    assert all("net_income_attributable" not in p for p in built.fundamentals["periods"])
    assert any("NetIncomeLoss en JPY" in s for s in built.skipped)
    no_currency = {"facts": {"us-gaap": {"Revenues": {"units": {"JPY": [row(1, "2026-09-27", "a", "2026-10-30")]}}}}}
    with pytest.raises(edgar.EdgarError):
        edgar.build_fundamentals(edgar.Issuer("X", 1, "X"), [no_currency], NOW)


def test_ifrs_taxonomy_is_preferred_when_present():
    payload = {
        "facts": {
            "ifrs-full": {
                "Revenue": {"units": {"CAD": [row(5e9, "2026-07-31", "R-1", "2026-08-27", "6-K", "2026-05-01")]}}
            },
            "us-gaap": {
                "Revenues": {"units": {"USD": [row(1, "2026-07-31", "R-1", "2026-08-27", start="2026-05-01")]}}
            },
        }
    }
    built = edgar.build_fundamentals(edgar.Issuer("RY.TO", 1000275, "Royal Bank"), [payload], NOW)
    assert built.taxonomy == "ifrs-full" and built.fundamentals["accounting_standard"] == "IFRS"
    assert built.fundamentals["reporting_currency"] == "CAD" and built.fundamentals["periods"][0]["revenue"] == 5000.0


def fake_sec(calls, mapping, facts_by_cik, sic_by_cik=None):
    def get(url):
        calls.append(url)
        if url == edgar.TICKERS_URL:
            return json.dumps(mapping).encode()
        for cik, payload in facts_by_cik.items():
            if url == edgar.COMPANYFACTS_URL.format(cik=cik):
                return json.dumps(payload).encode()
            if url == edgar.SUBMISSIONS_URL.format(cik=cik):
                if sic_by_cik and cik in sic_by_cik:
                    code, label = sic_by_cik[cik]
                    return json.dumps({"cik": str(cik), "sic": str(code), "sicDescription": label}).encode()
                raise http.FetchError("not found", status=404, url=url)
        raise AssertionError(f"URL inattendue : {url}")

    return get


def test_cn_is_read_under_cni_and_xom_history_under_its_old_cik():
    mapping = {
        "0": {"cik_str": 16868, "ticker": "CNI", "title": "Canadian National Railway"},
        "1": {"cik_str": 999999, "ticker": "XOM", "title": "Exxon Mobil"},
    }
    calls, staged = [], []
    get = fake_sec(calls, mapping, {16868: companyfacts(), 999999: {"facts": {}}, 34088: companyfacts()})
    report = edgar.stage_fundamentals(
        run_id="run1",
        tickers={"CNR.TO": "TSX", "XOM": None, "ATD.TO": "TSX"},
        stage=staged.append,
        deadline=float("inf"),
        get=get,
    )
    assert report["staged"] == ["CNR.TO", "XOM"] and report["absent"] == ["ATD.TO"]
    assert edgar.COMPANYFACTS_URL.format(cik=34088) in calls  # ancien CIK d'ExxonMobil lu aussi
    cn = staged[0]
    assert cn["tickers"] == ["CNR.TO"] and cn["data"]["fundamentals"]["ticker"] == "CNR.TO"
    assert cn["data"]["fundamentals"]["exchange"] == "TSX" and edgar.target_key("CNR.TO") == "general/societes/cnr.md"
    assert all("frames" not in url for url in calls)


def stage_item(store, built):
    item = edgar.fundamentals_item(built, run_id="run1", retrieved_at=NOW)
    store.put_json(staging.item_key("run1", "data", item["id"]), item)


def curate(store):
    return supervisor.curate(
        run_id="run1", store=store, trace=Trace("fr"), model_factory=ScriptedFactory(), model_id="scripted"
    )


def test_a6_writes_then_skips_unchanged_fundamentals(store):
    stage_item(store, build())
    result = curate(store)
    assert result["written"] == ["general/societes/aapl.md"], result
    text = store.get_text("general/societes/aapl.md").text
    assert "type: Company Fundamentals" in text and "agent:A6" in text
    assert store.get_json("general/societes/aapl.md.metadata.json")["metadataAttributes"]["ticker"]
    again = curate(store)
    assert again["written"] == [] and again["unchanged"] == ["general/societes/aapl.md"]


def test_a6_never_overwrites_the_atd_seed(store):
    seed = (SEEDS / "atd.md").read_text(encoding="utf-8")
    store.put_text("general/societes/atd.md", seed)
    stage_item(store, build(ticker="ATD.TO", cik=1))
    result = curate(store)
    assert result["written"] == []
    assert any("seed protégé" in r["reason"] for r in result["rejected"])
    assert store.get_text("general/societes/atd.md").text == seed


def test_a5_skips_edgar_without_a_contact_email(store, monkeypatch):
    monkeypatch.delenv("ALPHAFORGE_CONTACT_EMAIL", raising=False)
    monkeypatch.setattr(edgar, "_default_get", lambda url: pytest.fail(f"appel réseau : {url}"))
    run = data_collector.DataRun(run_id="run1", since="2026-11-01", tickers=["AAPL"], store=store, deadline=1e18)
    assert data_collector.stage_edgar_fundamentals(run, Trace("fr"), budget_seconds=10) is None
    assert any("ALPHAFORGE_CONTACT_EMAIL" in w for w in run.warnings) and run.staged == {}


def test_a5_stages_equities_only_with_a_contact_email(store, monkeypatch):
    monkeypatch.setenv("ALPHAFORGE_CONTACT_EMAIL", "contact@example.org")
    calls = []
    mapping = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
    monkeypatch.setattr(edgar, "_default_get", fake_sec(calls, mapping, {320193: companyfacts()}))
    run = data_collector.DataRun(
        run_id="run1", since="2026-11-01", tickers=["AAPL", "SPY", "BTC-USD"], store=store, deadline=1e18
    )
    report = data_collector.stage_edgar_fundamentals(run, Trace("fr"), budget_seconds=10)
    assert report["staged"] == ["AAPL"] and list(run.staged) == ["fundamentals-aapl"]
    assert len(calls) == 3  # correspondance des symboles, companyfacts et submissions d'Apple ; ni SPY ni BTC-USD


def stage_with_sic(store, code, label, ticker="ENB.TO", cik=895728, name="Enbridge Inc."):
    mapping = {"0": {"cik_str": cik, "ticker": edgar.sec_symbol(ticker), "title": name}}
    staged = []
    get = fake_sec([], mapping, {cik: companyfacts(name)}, {cik: (code, label)})
    report = edgar.stage_fundamentals(
        run_id="run1", tickers={ticker: "TSX"}, stage=staged.append, deadline=float("inf"), get=get
    )
    assert report["staged"] == [ticker]
    for item in staged:
        store.put_json(staging.item_key("run1", "data", item["id"]), item)
    return staged[0]


def test_a6_writes_a_sector_activity_fact_from_a_fossil_sic_code(store, monkeypatch):
    from alphaforge.finance.debate.okf_bridge import OkfMarketStore

    # A5 date l'élément à l'heure réelle et A6 en tire la période du fait : l'horloge est figée sur NOW.
    monkeypatch.setattr(clock, "utcnow", lambda: clock.parse_datetime(NOW))
    item = stage_with_sic(store, 4610, "PIPE LINES (NO NATURAL GAS)")
    assert item["data"]["sic"]["code"] == 4610
    result = curate(store)
    facts = [k for k in result["written"] if k.startswith(fundamentals.SECTOR_PREFIX)]
    assert len(facts) == 1, result
    doc = okf.parse(store.get_text(facts[0]).text)
    assert doc.frontmatter["type"] == "Fact"
    assert doc.data["esg"] == {"kind": "sector_activity", "metric": "fossil_fuels", "period": NOW[:10]}
    assert doc.data["tickers"] == ["ENB.TO"] and doc.data["value"] == "4610"
    items = OkfMarketStore(store).esg_items("ENB.TO", "2026-11-30")
    assert [(i.kind, i.metric) for i in items] == [("sector_activity", "fossil_fuels")]
    assert OkfMarketStore(store).esg_items("ENB.TO", "2026-11-01") == []  # pas avant sa publication
    again = curate(store)
    assert not [k for k in again["written"] if k.startswith(fundamentals.SECTOR_PREFIX)]


def test_a_sic_code_outside_the_table_gives_no_esg_fact(store):
    stage_with_sic(store, 4911, "ELECTRIC SERVICES", ticker="FTS.TO", cik=1666175, name="Fortis Inc.")
    result = curate(store)
    assert not [k for k in result["written"] if k.startswith(fundamentals.SECTOR_PREFIX)]


def test_a_missing_sic_code_does_not_block_fundamentals():
    mapping = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
    staged = []
    report = edgar.stage_fundamentals(
        run_id="run1",
        tickers={"AAPL": None},
        stage=staged.append,
        deadline=float("inf"),
        get=fake_sec([], mapping, {320193: companyfacts()}),
    )
    assert report["staged"] == ["AAPL"] and "sic" not in staged[0]["data"]
