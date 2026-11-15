"""Preuves ESG de la recherche (CONTRACTS.md, section 11.5) : le chercheur et A6 n'admettent qu'une catégorie de la
liste fermée, sur un fait, venu d'un hôte du paquet funds-sustainability ; le volet finance relit le document."""

from __future__ import annotations

import json
import time
from datetime import date

import pytest

from alphaforge import clock, okf
from alphaforge.collect import supervisor
from alphaforge.finance.debate.okf_bridge import OkfMarketStore
from alphaforge.research import items as items_mod
from alphaforge.research import researcher as researcher_mod
from alphaforge.research.packs import pack_hosts
from alphaforge.research.web import ResearchWeb
from alphaforge.trace import Trace

from ..conftest import ScriptedFactory
from .conftest import VALET_FX
from .test_pipeline import VALET_URL, fx_finding, stage

GHGRP_URL = "https://data-donnees.ec.gc.ca/ghgrp/enbridge-2024.json"
GHGRP = {"facilities": [{"company": "Enbridge Inc.", "year": "2024", "co2e_tonnes": "2154321"}]}


def esg_run(store):
    web = ResearchWeb(store=store, allowed_hosts=pack_hosts(["funds-sustainability", "rates-fx-commodities"]))
    brief = researcher_mod.parse_brief(
        {"run_id": "run1", "subject": "E4", "researcher": "r1", "objective": "ESG", "packs": ["funds-sustainability"]}
    )
    return web, researcher_mod.ResearcherRun(brief=brief, store=store, web=web, deadline=time.monotonic() + 30)


def record(run, archived, **extra):
    return run.record_finding(
        {
            "kind": "fact",
            "label": "Émissions déclarées d'Enbridge",
            "claim": "Enbridge a déclaré ses émissions de gaz à effet de serre au programme fédéral.",
            "response_id": archived.response_id,
            "fields": {"value": "facilities[0].co2e_tonnes"},
            "observation_date": "2024-12-31",
            "unit": "t éq. CO2",
            "issuers": ["ENB.TO"],
            **extra,
        }
    )


def test_researcher_accepts_esg_only_from_the_sustainability_pack(store, fake_http):
    fake_http.add(GHGRP_URL, GHGRP)
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    web, run = esg_run(store)
    ghgrp = web.fetch(GHGRP_URL)
    record(run, ghgrp, esg_kind="emissions", esg_metric="co2e_tonnes", esg_period="2024")
    assert run.findings[-1]["esg"] == {"kind": "emissions", "metric": "co2e_tonnes", "period": "2024"}
    with pytest.raises(researcher_mod.ResearchError, match="paquet funds-sustainability"):
        record(
            run,
            web.fetch(VALET_URL),
            fields={"value": "observations[2].FXUSDCAD.v"},
            esg_kind="emissions",
            esg_metric="co2e_tonnes",
        )
    with pytest.raises(researcher_mod.ResearchError, match="hors de la liste"):
        record(run, ghgrp, esg_kind="greenwashing", esg_metric="co2e_tonnes")
    with pytest.raises(researcher_mod.ResearchError, match="activité sectorielle"):
        record(run, ghgrp, esg_kind="sector_activity", esg_metric="pipelines")
    assert len(run.findings) == 1


def test_a6_writes_the_esg_fact_and_the_finance_reader_cites_it(store, fake_http):
    fake_http.add(GHGRP_URL, GHGRP)
    web, run = esg_run(store)
    record(run, web.fetch(GHGRP_URL), esg_kind="sector_activity", esg_metric="fossil_fuels", esg_period="2024")
    item = items_mod.build_item(run.findings[0])
    assert item["data"]["esg"]["kind"] == "sector_activity" and item["data"]["tags"][0] == "esg"
    stage(store, item, "E4")
    result = supervisor.curate(
        run_id="run1", store=store, trace=Trace("fr"), model_factory=ScriptedFactory(), model_id="scripted"
    )
    assert len(result["written"]) == 1, result
    key = result["written"][0]
    assert key.startswith("general/faits/data-donnees-ec-gc-ca/2024-12-31-")  # arborescence fermée inchangée
    doc = okf.parse(store.get_text(key).text)
    assert doc.data["esg"]["metric"] == "fossil_fuels" and doc.data["tickers"] == ["ENB.TO"]
    assert "esg" in doc.frontmatter["tags"] and "## Preuve ESG" in doc.body

    market = OkfMarketStore(store)
    today = clock.utcnow().date()
    facts = market.evidence("enb.to", "esg", today)
    assert [f.fact_id for f in facts] == ["okf.esg.ENB.TO.1"]
    assert facts[0].status == "FAIT" and facts[0].value == 2154321.0
    assert facts[0].sources[0].dataset == f"okf-esg:{key}"
    assert key in market.inputs  # dans la version des données
    assert market.evidence("ENB.TO", "esg", date(2024, 1, 1)) == []  # publié après as_of : ignoré


def test_a6_rejects_an_invalid_esg_block_or_a_host_outside_the_pack(store, fake_http):
    fake_http.add(GHGRP_URL, GHGRP)
    fake_http.add("https://www.bankofcanada.ca/valet/observations/", VALET_FX)
    web, run = esg_run(store)
    record(run, web.fetch(GHGRP_URL), esg_kind="emissions", esg_metric="co2e_tonnes", esg_period="2024")
    bad_kind = items_mod.build_item(run.findings[0])
    bad_kind["id"] = "fact-bad-kind"
    bad_kind["data"]["esg"]["kind"] = "greenwashing"
    stage(store, bad_kind, "E4")
    valet = fx_finding(store)
    outside = items_mod.build_item(
        {**valet, "kind": "fact", "values": {"value": "1.4257"}, "locators": {"value": "observations[2].FXUSDCAD.v"}}
    )
    outside["id"] = "fact-outside"
    outside["data"]["esg"] = {"kind": "emissions", "metric": "co2e_tonnes", "period": "2024"}
    stage(store, json.loads(json.dumps(outside)), "E4")
    result = supervisor.curate(
        run_id="run1", store=store, trace=Trace("fr"), model_factory=ScriptedFactory(), model_id="scripted"
    )
    reasons = {r["key"].rsplit("/", 1)[-1]: r["reason"] for r in result["rejected"]}
    assert "hors de la liste" in reasons["fact-bad-kind.json"]
    assert "hors du paquet funds-sustainability" in reasons["fact-outside.json"]
    assert result["written"] == []
