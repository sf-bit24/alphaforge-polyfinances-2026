"""Catalogue des concepts, faits calculés et signaux déterministes."""

from __future__ import annotations

import pytest

from alphaforge.tldoole import signals
from alphaforge.tldoole.concepts import (
    CatalogError,
    load_catalog,
    normalize,
    parse_catalog,
)
from alphaforge.tldoole.facts import (
    FactBook,
    FactError,
    fmt_money,
    fmt_pct,
    number_tokens,
)


def test_catalog_is_consistent():
    catalog = load_catalog()
    assert len(catalog.concepts) >= 15
    for concept in catalog.concepts.values():
        for rule in concept.signals:
            assert rule in signals.RULES, (concept.id, rule)
        assert catalog.source_entries(concept)
    with pytest.raises(CatalogError):
        parse_catalog({"concepts": [{"id": "x", "label": {"fr": "x"}}]})


def test_fact_hints_are_computable():
    catalog = load_catalog()
    portfolio = {
        "positions": [{"id": "p1", "ticker": "RY.TO"}, {"id": "p2", "ticker": "SHOP.TO"}],
        "exposures": {
            "total_value_cad": 1000,
            "top_positions": [{"id": "p1", "weight": 0.7}, {"id": "p2", "weight": 0.3}],
            "by_currency": {"CAD": 1.0},
            "by_market": {"TSX": 1.0},
            "flags": [],
        },
    }
    for concept in catalog.concepts.values():
        facts = FactBook("fr", client_portfolio=portfolio)
        for hint in concept.fact_hints:
            args = {k: v for k, v in hint.items() if k != "tool"}
            fact = getattr(facts, hint["tool"])(**args)
            assert fact["fact_id"].startswith("f") and fact["source"]["title"]


def test_alias_matching_ignores_case_and_accents():
    catalog = load_catalog()
    assert catalog.get("fnb").mentioned_in("C'est quoi un FNB ?")
    assert catalog.get("volatilite").mentioned_in("la VOLATILITÉ me fait peur")
    assert catalog.get("celi_reer").mentioned_in("mon tfsa")
    assert not catalog.get("fnb").mentioned_in("un fnbx")
    assert normalize("Qu’est-ce   qu'un REER") == "qu'est-ce qu'un reer"


def test_formats_by_locale():
    assert fmt_pct(-0.164, "fr") == "\u221216,4\u00a0%"
    assert fmt_pct(0.897, "en", signed=True) == "+89.7%"
    assert fmt_money(61960, "fr") == "61\u00a0960\u00a0$"
    assert fmt_money(190, "en", "USD") == "US$190"
    assert number_tokens("\u221216,4\u00a0% en 2022, 61\u00a0960\u00a0$ ou $1,234.5") == {
        "16.4",
        "2022",
        "61960",
        "1234.5",
    }


def test_asset_stats_from_the_starter_dataset():
    facts = FactBook("fr")
    fact = facts.asset_stats("xiu.to")
    metrics = fact["metrics"]
    assert fact["entity"] == "XIU.TO" and fact["source"]["resource"] == "starter:prices_daily.csv"
    assert -0.5 < metrics["max_drawdown"]["value"] < 0
    assert 0 < metrics["annualized_volatility"]["value"] < 1
    assert facts.series("f1")["values"][0] == 100
    compare = facts.compare_assets(["SHOP.TO", "XIU.TO"], "annualized_volatility")
    assert compare["metrics"]["ratio_first_last"]["value"] > 1
    assert facts.asset_stats("XIU.TO")["fact_id"] == "f1"  # même fait, même identifiant
    assert "13.1" in facts.allowed_numbers(["f1"]) or "13" in facts.allowed_numbers(["f1"])
    with pytest.raises(FactError):
        facts.asset_stats("NOPE")
    with pytest.raises(FactError):
        facts.compound_growth(1000, 100, 50, 10)
    with pytest.raises(FactError):
        facts.client_portfolio()


def test_message_and_rule_signals():
    catalog = load_catalog()
    entries = [
        {
            "at": "t1",
            "kind": "answer",
            "field": "risk_tolerance.risk_attitude",
            "value": "large",
            "provenance": "base:q",
        },
        {
            "at": "t2",
            "kind": "answer",
            "field": "risk_tolerance.drop_reaction",
            "value": "sell_all",
            "provenance": "base:q",
        },
        {
            "at": "t3",
            "kind": "answer",
            "field": "constraints.account_types",
            "value": ["unknown"],
            "provenance": "base:q",
        },
        {
            "at": "t4",
            "kind": "message",
            "provenance": "a1:1",
            "text": "Je ne comprends pas c'est quoi un FNB.",
            "locale": "fr",
        },
        {"at": "t5", "kind": "message", "provenance": "a1:2", "text": "J'ai un CELI.", "locale": "fr"},
    ]
    messages = signals.investor_messages(entries)
    assert [m.ref for m in messages] == ["m1", "m2"]
    found = {c.concept_id: c for c in signals.message_candidates(catalog, messages)}
    assert found["fnb"].score == 0.85 and found["fnb"].evidence[0].quote.startswith("Je ne comprends pas")
    assert found["celi_reer"].score == 0.3
    answers = signals.latest_answers(entries)
    rules = {c.concept_id: c for c in signals.rule_candidates(catalog, answers, None, "beginner")}
    assert rules["volatilite"].rule == "attitude_vs_reaction"
    assert rules["celi_reer"].score == 0.7
    merged = signals.merge([*found.values(), *rules.values()])
    assert merged["celi_reer"].score == 0.7 and len(merged["celi_reer"].evidence) == 2


def test_portfolio_flags_point_to_concepts():
    catalog = load_catalog()
    portfolio = {"exposures": {"flags": ["concentration_single_position", "home_bias_canada"]}}
    found = {c.concept_id for c in signals.rule_candidates(catalog, {}, portfolio, None)}
    assert {"concentration", "biais_domestique"} <= found
