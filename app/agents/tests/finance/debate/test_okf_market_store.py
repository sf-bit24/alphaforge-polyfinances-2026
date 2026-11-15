"""``OkfMarketStore.evidence`` sur le magasin local (pur, en CI) : fondamentaux et actualités de la base générale,
point dans le temps, cache par lot, et version des données qui couvre les fondamentaux mais jamais les actualités."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from alphaforge import okf
from alphaforge.finance.debate.okf_bridge import OkfMarketStore
from alphaforge.store.local import LocalStore

from ..strategy._okf_docs import SOCIETES, news_text

AS_OF = date(2026, 9, 30)
ATD = "general/societes/atd.md"
NEWS_SEPT = "general/actualites/2026/09/couche-tard-zabka-aaaa1111.md"
NEWS_OCT = "general/actualites/2026/10/couche-tard-rumeur-bbbb2222.md"


def _seed(root: Path, news: bool = True) -> LocalStore:
    store = LocalStore(root)
    store.put_text(ATD, (SOCIETES / "atd.md").read_text(encoding="utf-8"))
    index = okf.new_doc(
        type="Index",
        title="Sociétés",
        description="Index.",
        tags=["index"],
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A6",
        at="2026-11-15T00:00:00Z",
    )
    store.put_text("general/societes/index.md", okf.render(index))
    if news:
        store.put_text(NEWS_SEPT, news_text("Couche-Tard vise Żabka", ("atd.to",), "2026-09-15T13:00:00Z"))
        store.put_text(NEWS_OCT, news_text("Rumeur sur Couche-Tard", ("ATD.TO", "SHOP.TO"), "2026-10-02T08:00:00Z"))
    return store


@pytest.fixture
def market(tmp_path):
    return OkfMarketStore(_seed(tmp_path))


def test_fundamentals_match_data_ticker_case_insensitively(market):
    facts = market.evidence("atd.to", "fundamentals", AS_OF)
    assert facts and all(f.fact_id.startswith("okf.fund.ATD.TO.") for f in facts)
    assert [f.model_dump() for f in facts] == [f.model_dump() for f in market.evidence("ATD.TO", "fundamentals", AS_OF)]
    assert facts[0].sources[0].dataset == f"okf:{ATD}" and facts[0].sources[0].url is None
    assert market.evidence("CSU.TO", "fundamentals", AS_OF) == []  # pas de document : rien, jamais d'invention
    assert market.evidence("Couche Tard", "fundamentals", AS_OF) == []
    assert market.evidence("ATD.TO", "fundamentals", date(2026, 6, 1)) == []  # rien de publié avant


def test_bucket_gives_the_s3_url(tmp_path):
    m = OkfMarketStore(_seed(tmp_path), bucket="alphaforge-kb")
    assert m.evidence("ATD.TO", "fundamentals", AS_OF)[0].sources[0].url == f"s3://alphaforge-kb/{ATD}"


def test_news_point_in_time_most_recent_first(market):
    sept = market.evidence("ATD.TO", "news", AS_OF)
    assert [(f.fact_id, f.value) for f in sept] == [("okf.news.ATD.TO.1", "Couche-Tard vise Żabka")]
    assert sept[0].status == "HYPOTHESE" and sept[0].sources[0].dataset == f"okf-news:{NEWS_SEPT}"
    assert NEWS_OCT not in market.news_inputs  # rangée sous octobre : pas lue pour une simulation au 30 septembre
    octo = market.evidence("atd.to", "news", date(2026, 10, 31))
    assert [f.value for f in octo] == ["Rumeur sur Couche-Tard", "Couche-Tard vise Żabka"]
    assert [f.fact_id for f in octo] == ["okf.news.ATD.TO.1", "okf.news.ATD.TO.2"]
    assert [f.fact_id for f in market.evidence("shop.to", "news", date(2026, 10, 31))] == ["okf.news.SHOP.TO.1"]
    assert market.evidence("SHOP.TO", "news", AS_OF) == []


def test_esg_hook_returns_nothing_and_unknown_topic_fails(market):
    assert market.evidence("ATD.TO", "esg", AS_OF) == []
    with pytest.raises(ValueError):
        market.evidence("ATD.TO", "sentiment", AS_OF)


def test_inputs_hold_fundamentals_only(market):
    market.evidence("ATD.TO", "news", date(2026, 10, 31))
    market.evidence("ATD.TO", "fundamentals", AS_OF)
    assert set(market.inputs) == {ATD}  # l'index n'est pas un intrant ; les actualités non plus
    assert set(market.news_inputs) == {NEWS_SEPT, NEWS_OCT}
    assert market.inputs[ATD] and not market.inputs[ATD].startswith('"')


def test_data_version_covers_fundamentals_never_news(tmp_path):
    with_news = OkfMarketStore(_seed(tmp_path / "a", news=True))
    without = OkfMarketStore(_seed(tmp_path / "b", news=False))
    v = with_news.data_version("d1")
    assert v.startswith("d1+okf:") and v == without.data_version("d1")
    assert with_news.data_version(None) == v.removeprefix("d1+")

    store = _seed(tmp_path / "c")
    store.put_text(NEWS_SEPT, news_text("Autre titre", ("ATD.TO",)))
    assert OkfMarketStore(store).data_version("d1") == v  # une actualité changée : même version
    doc = okf.parse(store.get(ATD).text)
    doc.frontmatter["data"]["periods"][0]["revenue"] = 21704.9
    store.put_text(ATD, okf.render(doc))
    changed = OkfMarketStore(store)
    assert changed.data_version("d1") != v  # un fondamental changé : autre version
    assert changed.evidence("ATD.TO", "fundamentals", AS_OF)[0].value == 21704.9


def test_listing_and_documents_are_cached_per_batch(tmp_path):
    store = _seed(tmp_path)
    m = OkfMarketStore(store)
    first = m.evidence("ATD.TO", "fundamentals", AS_OF)
    store.put_text(ATD, store.get(ATD).text.replace("revenue: 21704.8", "revenue: 1.0"))
    assert m.evidence("ATD.TO", "fundamentals", AS_OF) == first  # même lot : mêmes lectures
    m.reset()
    assert m.evidence("ATD.TO", "fundamentals", AS_OF)[0].value == 1.0


def test_malformed_or_duplicate_documents_are_rejected_not_guessed(tmp_path):
    store = _seed(tmp_path)
    text = store.get(ATD).text
    store.put_text("general/societes/atd-copie.md", text)
    store.put_text(
        "general/societes/csu.md",
        (SOCIETES / "csu.md").read_text(encoding="utf-8").replace("unit: millions", "unit: thousands"),
    )
    m = OkfMarketStore(store)
    assert m.evidence("ATD.TO", "fundamentals", AS_OF) == []  # deux documents pour ATD : on ne choisit pas
    assert m.evidence("CSU.TO", "fundamentals", AS_OF) == []
    assert {ATD, "general/societes/atd-copie.md", "general/societes/csu.md"} <= set(m.rejected)
    assert "thousands" in m.rejected["general/societes/csu.md"] or "unit" in m.rejected["general/societes/csu.md"]
    assert {ATD, "general/societes/atd-copie.md", "general/societes/csu.md"} == set(m.inputs)


class _Broken(LocalStore):
    def list(self, prefix, *, limit=1000):
        raise PermissionError("AccessDenied")


def test_unreadable_store_yields_nothing_but_shows_in_the_data_version(tmp_path):
    ok = OkfMarketStore(_seed(tmp_path / "ok"))
    broken = OkfMarketStore(_Broken(tmp_path / "ko"))
    assert broken.evidence("ATD.TO", "fundamentals", AS_OF) == []
    assert broken.evidence("ATD.TO", "news", AS_OF) == []
    assert broken.inputs == {"general/societes/": "erreur:PermissionError"}
    assert broken.data_version("d1") != ok.data_version("d1")
