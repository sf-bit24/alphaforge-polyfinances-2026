"""Bout en bout (mode règles) : le portefeuille existant est cité par la décision, sans rien changer sans lui."""

from __future__ import annotations

from datetime import UTC, date, datetime

from alphaforge.finance.contracts.profile import Goal, Holding, InvestorProfile, Score
from alphaforge.finance.debate import build_portfolio
from alphaforge.finance.debate.explain import verify

AS_OF = date(2026, 9, 30)


def _profile(holdings=()):
    return InvestorProfile(
        profile_id="p-holdings",
        created_utc=datetime(2026, 11, 14, tzinfo=UTC),
        status="COMPLETE",
        goals=[Goal(goal_id="g1", label="retraite", priority="besoin", horizon_years=12)],
        tolerance_declared=Score(value=52),
        investable_wealth=100_000,
        max_acceptable_loss_cad=25_000,
        knowledge_level="avance",
        holdings=list(holdings),
    )


def _weights(d):
    return tuple(sorted((p.asset_id, round(p.weight, 6)) for p in d.positions))


def test_without_holdings_the_decision_has_no_holding_fact():
    d = build_portfolio(_profile(), AS_OF).decision
    assert not any(f.fact_id.startswith("holdings.") for f in d.facts)
    assert not any("Portefeuille existant" in s.text_fr for s in d.explanation.data_used)


def test_existing_position_is_cited_and_grounded():
    d = build_portfolio(_profile([Holding(ticker="RY.TO", market_value=40_000)]), AS_OF).decision
    ids = {f.fact_id for f in d.facts}
    assert {"holdings.n", "holdings.total", "holdings.top", "holdings.top_share"} <= ids
    st = next(s for s in d.explanation.data_used if s.text_fr.startswith("Portefeuille existant"))
    assert "RY.TO" in st.text_fr and "40,0 %" in st.text_fr
    book = type("B", (), {"facts": {f.fact_id: f for f in d.facts}})()
    assert not verify(book, st), st.text_fr


def test_a_small_holding_leaves_the_weights_unchanged():
    base = build_portfolio(_profile(), AS_OF).decision
    small = build_portfolio(_profile([Holding(ticker="RY.TO", market_value=5_000)]), AS_OF).decision
    assert _weights(small) == _weights(base) and small.kind == base.kind
