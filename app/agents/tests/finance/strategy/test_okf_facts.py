"""Lot E, partie pure : lecture des fondamentaux et des actualités de la base générale OKF (sans numpy, en CI).

Les documents réels ``app/knowledge/general/societes/{atd,csu}.md`` servent de jeu d'essai : point dans le temps,
registre des unités, statut des mesures non IFRS, héritage de ``prior_year``, refus des documents mal formés.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from alphaforge import okf
from alphaforge.finance.strategy import okf_facts as of

from ._okf_docs import SOCIETES, news_text

AS_OF = date(2026, 9, 30)


def _text(name: str) -> str:
    return (SOCIETES / name).read_text(encoding="utf-8")


def _cf(name: str, **kw) -> of.CompanyFundamentals:
    return of.parse_company_fundamentals(_text(name), f"general/societes/{name}", "etag-" + name, **kw)


def _facts(name: str, as_of=AS_OF) -> dict[str, object]:
    return {f.fact_id: f for f in of.fundamentals_facts(_cf(name), as_of)}


def _mutate(name: str, change) -> str:
    doc = okf.parse(_text(name))
    change(doc.frontmatter)
    return okf.render(doc)


# ------------------------------------------------------------------------------------------- lecture des seeds
def test_seed_documents_parse_with_their_declared_units():
    atd, csu = _cf("atd.md", bucket="bkt"), _cf("csu.md")
    assert (atd.ticker, atd.reporting_currency, atd.unit, atd.accounting_standard) == (
        "ATD.TO",
        "USD",
        "millions",
        "IFRS",
    )
    assert (csu.ticker, csu.reporting_currency) == ("CSU.TO", "USD")
    assert [p.period for p in atd.periods] == ["T1 2027", "Exercice 2026"]
    assert [p.period for p in csu.periods] == ["T3 2026", "Neuf mois 2026", "Exercice 2025"]
    assert atd.url == "s3://bkt/general/societes/atd.md" and csu.url is None
    assert atd.dividends[0].currency == "CAD" and csu.dividends[0].currency == "USD"


def test_point_in_time_2026_09_30_atd_admissible_csu_only_fiscal_2025():
    atd, csu = _cf("atd.md").admissible(AS_OF), _cf("csu.md").admissible(AS_OF)
    assert [p.period for p in atd.periods] == ["T1 2027", "Exercice 2026"]
    assert len(atd.balance_sheets) == 2 and len(atd.dividends) == 1
    assert [p.period for p in csu.periods] == ["Exercice 2025"]
    assert csu.balance_sheets == [] and csu.dividends == []  # tout le reste est publié le 2026-11-06

    facts = _facts("csu.md")
    assert set(facts) == {
        "okf.fund.CSU.TO.revenue",
        "okf.fund.CSU.TO.revenue_growth_yoy",
        "okf.fund.CSU.TO.net_income_attributable",
        "okf.fund.CSU.TO.diluted_eps",
    }
    assert all("Exercice 2025" in f.sources[0].processing for f in facts.values())
    assert facts["okf.fund.CSU.TO.revenue"].value == 11623


@pytest.mark.parametrize("name", ["atd.md", "csu.md"])
def test_no_fact_is_published_after_as_of(name):
    cf = _cf(name)
    for days in range(0, 400, 7):
        as_of = date(2025, 12, 1) + timedelta(days=days)
        for f in of.fundamentals_facts(cf, as_of):
            assert f.published <= as_of, (f.fact_id, f.published, as_of)
            assert f.as_of <= f.published


def test_csu_comparative_balance_sheet_keeps_the_later_statements_date():
    """Bilan au 2025-12-31 repris comme comparatif des états du T3 2026 : admissible à partir du 2026-11-06."""
    cf = _cf("csu.md")
    sheet = next(b for b in cf.balance_sheets if b.observed_at == date(2025, 12, 31))
    assert sheet.published_at_basis == "comparative_in_later_statements"
    assert cf.admissible(date(2026, 11, 5)).balance_sheets == []
    assert len(cf.admissible(date(2026, 11, 6)).balance_sheets) == 2


def test_latest_quarter_wins_at_equal_observation_date():
    facts = _facts("csu.md", date(2026, 11, 10))
    assert facts["okf.fund.CSU.TO.revenue"].value == 3512  # T3 2026, pas les neuf mois (10 027)
    assert "T3 2026" in facts["okf.fund.CSU.TO.revenue"].label_fr
    assert facts["okf.fund.CSU.TO.dividend"].value == 1.0


# ------------------------------------------------------------------------------------------- unités et statuts
def test_unit_registry_atd():
    f = _facts("atd.md")
    rev = f["okf.fund.ATD.TO.revenue"]
    assert (rev.value, rev.unit, rev.currency, rev.status) == (21704.8, "millions", "USD", "FAIT")
    eps = f["okf.fund.ATD.TO.diluted_eps"]
    assert (eps.value, eps.unit, eps.currency, eps.status) == (0.90, "par action", "USD", "FAIT")  # pas en millions
    roe = f["okf.fund.ATD.TO.return_on_equity"]
    assert (roe.value, roe.unit, roe.currency) == (0.197, "%", None)  # 19,7 points de % → fraction
    assert roe.status == "HYPOTHESE" and "points de pourcentage" in roe.sources[0].processing
    lev = f["okf.fund.ATD.TO.leverage_ratio"]
    assert (lev.value, lev.unit, lev.currency) == (1.77, "ratio", None)
    div = f["okf.fund.ATD.TO.dividend"]
    assert (div.value, div.unit, div.currency, div.status) == (0.215, "par action", "CAD", "FAIT")  # CAD, pas USD
    assert (div.as_of, div.published) == (date(2026, 9, 1), date(2026, 9, 1))
    assert (rev.as_of, rev.published) == (date(2026, 7, 19), date(2026, 9, 1))


def test_registry_flags_non_ifrs_measures_and_their_facts_are_hypotheses():
    for name in ("adjusted_ebitda", "fcfa2s", "organic_growth_pct"):
        assert of.PERIOD_METRICS[name].gaap is False
    for name in ("leverage_ratio", "net_interest_bearing_debt", "return_on_equity_pct"):
        assert of.BALANCE_METRICS[name].gaap is False
    assert of.PERIOD_METRICS["revenue"].gaap and of.PERIOD_METRICS["diluted_eps"].gaap
    lev = _facts("atd.md")["okf.fund.ATD.TO.leverage_ratio"]
    assert lev.status == "HYPOTHESE" and "non IFRS" in lev.label_fr and "non IFRS" in lev.sources[0].processing
    assert of.fact_unit(of.PERIOD_METRICS["organic_growth_pct"], "USD") == ("%", None, 0.01)


def test_prior_year_inherits_published_at_and_feeds_yoy_growth():
    cf = _cf("atd.md")
    t1 = cf.periods[0]
    assert t1.prior_year is not None and t1.prior_year.published_at == t1.published_at == date(2026, 9, 1)
    g = _facts("atd.md")["okf.fund.ATD.TO.revenue_growth_yoy"]
    assert g.status == "HYPOTHESE" and g.unit == "%"
    assert g.value == pytest.approx(21704.8 / 17346.9 - 1)
    assert g.published == date(2026, 9, 1)
    assert "prior_year.revenue" in g.sources[0].processing


def test_prior_year_alone_is_never_admissible_before_its_parent():
    """Le T1 2026 (prior_year) a été publié en 2025, mais ce document ne le date pas : il suit le T1 2027."""
    cf = _cf("atd.md").admissible(date(2026, 8, 31))
    assert [p.period for p in cf.periods] == ["Exercice 2026"]
    assert _facts("atd.md", date(2026, 6, 21)) == {}


def test_fact_ids_and_provenance():
    f = _facts("atd.md")
    assert all(k.startswith("okf.fund.ATD.TO.") for k in f)
    rev = f["okf.fund.ATD.TO.revenue"]
    okf_src, issuer = rev.sources
    assert okf_src.dataset == "okf:general/societes/atd.md" and okf_src.sha256 == "etag-atd.md"
    assert okf_src.processing == "data.periods[period='T1 2027'].revenue"
    assert issuer.dataset == "emetteur:atd-t1-2027-communique" and issuer.url.startswith("https://")
    assert issuer.retrieved_utc is not None
    order = list(f)
    assert order[0] == "okf.fund.ATD.TO.revenue" and order[-1] == "okf.fund.ATD.TO.dividend"


def test_markdown_body_is_never_read():
    doc = okf.parse(_text("atd.md"))
    doc.body = "| Produits | 99 999 999 |\n\nBénéfice : 1 000 000 000 $.\n"
    other = of.fundamentals_facts(of.parse_company_fundamentals(okf.render(doc), "k", "e"), AS_OF)
    assert [(f.fact_id, f.value) for f in other] == [(f.fact_id, f.value) for f in _facts("atd.md").values()]


def test_deterministic():
    a = [f.model_dump() for f in of.fundamentals_facts(_cf("atd.md"), AS_OF)]
    b = [f.model_dump() for f in of.fundamentals_facts(_cf("atd.md"), AS_OF)]
    assert a == b


# ------------------------------------------------------------------------------------------- refus
def _set(path, value):
    def change(meta):
        node = meta
        for p in path[:-1]:
            node = node[p]
        node[path[-1]] = value

    return change


def _drop(path):
    def change(meta):
        node = meta
        for p in path[:-1]:
            node = node[p]
        del node[path[-1]]

    return change


MALFORMED = {
    "champ inconnu": _set(("data", "periods", 0, "ebit_margin"), 5.1),
    "unité": _set(("data", "unit"), "thousands"),
    "nombre en texte": _set(("data", "periods", 0, "revenue"), "21 704,8"),
    "booléen": _set(("data", "balance_sheets", 0, "cash"), True),
    "horodatage au lieu d'une date": _set(("data", "periods", 0, "published_at"), "2026-09-01T00:00:00Z"),
    "publié avant observé": _set(("data", "periods", 0, "published_at"), "2026-07-01"),
    "source inconnue": _set(("data", "periods", 0, "source"), "nulle-part"),
    "prior_year daté": _set(("data", "periods", 0, "prior_year", "published_at"), "2025-09-01"),
    "prior_year plus récent": _set(("data", "periods", 0, "prior_year", "observed_at"), "2026-07-20"),
    "dividende sans devise": _drop(("data", "dividends", 0, "currency")),
    "devise inconnue": _set(("data", "reporting_currency"), "GBP"),
    "ticker invalide": _set(("data", "ticker"), "Couche Tard"),
    "type de période": _set(("data", "periods", 0, "kind"), "semester"),
    "frontmatter incomplet": _drop(("owners",)),
    "période en double": _set(("data", "periods", 1, "period"), "T1 2027"),
    "champ réservé": _set(("data", "sources"), []),
}


@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_malformed_documents_are_rejected_with_a_clear_error(case):
    text = _mutate("atd.md", MALFORMED[case])
    with pytest.raises(of.OkfFactsError) as exc:
        of.parse_company_fundamentals(text, "general/societes/atd.md", "e")
    assert "general/societes/atd.md" in str(exc.value)
    assert not isinstance(exc.value, of.WrongDocType)


def test_unknown_field_message_names_the_field():
    text = _mutate("atd.md", MALFORMED["champ inconnu"])
    with pytest.raises(of.OkfFactsError, match="ebit_margin"):
        of.parse_company_fundamentals(text, "k", "e")


def test_other_document_types_and_text_without_frontmatter():
    with pytest.raises(of.WrongDocType):
        of.parse_company_fundamentals(_mutate("atd.md", _set(("type",), "Index")), "k", "e")
    with pytest.raises(of.OkfFactsError):
        of.parse_company_fundamentals("# Couche-Tard\n\nProduits : 21 704,8\n", "k", "e")


# ------------------------------------------------------------------------------------------- actualités
def test_news_admissible_only_after_publication_and_always_a_hypothesis():
    key = "general/actualites/2026/09/shopify-abc.md"
    assert of.news_facts(news_text(), key, "e1", date(2026, 9, 14)) == []
    facts = of.news_facts(news_text(), key, "e1", date(2026, 9, 15))
    assert [f.fact_id for f in facts] == ["okf.news.SHOP.TO.1", "okf.news.ATD.TO.1"]  # shop.to canonisé
    f = facts[0]
    assert f.status == "HYPOTHESE" and f.unit == "texte" and f.value == "Shopify annonce un partenariat"
    assert f.sources[0].dataset == f"okf-news:{key}" and f.sources[0].sha256 == "e1"
    assert f.published == date(2026, 9, 15)
    only = of.news_facts(news_text(), key, "e1", date(2026, 9, 30), ticker="atd.to", n=3)
    assert [x.fact_id for x in only] == ["okf.news.ATD.TO.3"]


def test_malformed_news_is_rejected():
    with pytest.raises(of.OkfFactsError):
        of.news_facts(news_text(published="hier"), "k", "e", AS_OF)
    with pytest.raises(of.OkfFactsError):
        of.news_facts(news_text(tickers=("pas un ticker !",)), "k", "e", AS_OF)
    with pytest.raises(of.WrongDocType):
        of.news_facts(_text("atd.md"), "k", "e", AS_OF)


def test_canonical_ticker():
    assert of.canonical_ticker(" shop.to ") == "SHOP.TO"
    assert of.canonical_ticker("brk-b") == "BRK-B"
    for bad in ("", "a b", None, 3, "x" * 30):
        with pytest.raises(of.OkfFactsError):
            of.canonical_ticker(bad)
