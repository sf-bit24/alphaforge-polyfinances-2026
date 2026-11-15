"""Dépôts réglementaires de la base générale (pur, en CI) : sujet ``filings`` d'``OkfMarketStore``, point dans le
temps, et garde de la fusion (un dépôt se signale, ne change jamais le mandat)."""

from __future__ import annotations

from datetime import date

from alphaforge import okf
from alphaforge.finance.debate.merge import FILING_REJECT_FR, apply_amendments
from alphaforge.finance.debate.okf_bridge import OkfMarketStore
from alphaforge.finance.debate.schemas import Amendment, LensReport
from alphaforge.store.local import LocalStore

from ..strategy._helpers import make_comp

ENB_NEW = "general/depots/enb-to/0001193125-26-100001.md"
ENB_OLD = "general/depots/enb-to/0001193125-26-050001.md"
FILING = "okf.filing.ENB.TO.1"
RISK = "r1.cvar_m"


def filing_text(title, form, accession, published, tickers=None):
    data = {
        "kind": "filing",
        "values": {"form": form, "accession": accession},
        "url": "https://www.sec.gov/Archives/edgar/data/895728/",
        "published_at": published,
        "observed_at": published[:10],
    }
    if tickers is not None:
        data["tickers"] = tickers
    doc = okf.new_doc(
        type="Regulatory Filing",
        title=title,
        description="Dépôt.",
        tags=["depots"],
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A6",
        at="2026-11-15T00:00:00Z",
        sources=[{"id": accession, "title": title, "resource": data["url"]}],
        data=data,
    )
    return okf.render(doc)


def market(tmp_path):
    store = LocalStore(tmp_path)
    store.put_text(
        ENB_NEW, filing_text("Enbridge 6-K", "6-K", "0001193125-26-100001", "2026-11-03T10:00:00Z", ["ENB.TO"])
    )
    store.put_text(ENB_OLD, filing_text("Enbridge 40-F", "40-F", "0001193125-26-050001", "2026-02-13T10:00:00Z"))
    return OkfMarketStore(store)


def test_filings_are_point_in_time_newest_first(tmp_path):
    ms = market(tmp_path)
    facts = ms.evidence("enb.to", "filings", date(2026, 11, 15))
    assert [f.fact_id for f in facts] == ["okf.filing.ENB.TO.1", "okf.filing.ENB.TO.2"]
    assert "6-K" in facts[0].label_fr and facts[0].unit == "texte"
    # Avant le 6-K, seul le 40-F (rangé sous enb-to/, sans data.tickers) est connu.
    old = ms.evidence("ENB.TO", "filings", date(2026, 9, 30))
    assert len(old) == 1 and "40-F" in old[0].label_fr
    assert ms.evidence("CNQ.TO", "filings", date(2026, 11, 15)) == []
    assert "general/depots/" not in "".join(ms.inputs)  # hors version des données, comme les actualités


def _merge(*amendments, lens="constraints"):
    policy = make_comp().policy
    rep = LensReport(lens=lens, amendments=list(amendments))
    return policy, *apply_amendments(policy, [rep], {lens: 1.0}, {FILING, RISK})


def _am(kind, target, evidence, value=None):
    return Amendment(kind=kind, target=target, value=value, reason_fr="test", evidence_fact_ids=evidence)


def test_a_filing_never_justifies_a_mandate_change():
    for a in (_am("exclude_asset", "ENB.TO", [FILING]), _am("tighten_limit", "risk.cvar_m", [RISK, FILING], 0.05)):
        before, after, log = _merge(a)
        assert [x.status for x in log] == ["rejete"] and log[0].why_fr == FILING_REJECT_FR
        assert after.model_dump() == before.model_dump()


def test_flag_only_citing_a_filing_stays_allowed():
    _, _, log = _merge(_am("flag_only", "ENB.TO", [FILING]))
    assert [x.status for x in log] == ["applique"]
