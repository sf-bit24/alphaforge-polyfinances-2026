"""Chaque profil reçoit un portefeuille construit pour lui, même en protection ou incomplet (décision 2026-11-15).

Le statut resserre le mandat et reste visible (type de décision, raison chiffrée dans l'explication) ; il
n'empêche plus la construction. Mode règles, hors ligne, sur les données longues du moteur.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from alphaforge.finance.contracts.profile import Goal, InvestorProfile, ProfileStatus, Score
from alphaforge.finance.debate import Request, build_portfolio
from alphaforge.finance.observability.verify import verify_decision

AS_OF = date(2026, 9, 30)
SINGLE_OR_CRYPTO = {"TSLA", "NVDA", "AAPL", "MSFT", "SHOP.TO", "BTC-USD", "ETH-USD"}


def _profile(**update) -> InvestorProfile:
    """Profil complet de référence ; ``model_copy`` ne valide pas : passer les énumérations elles-mêmes."""
    base = InvestorProfile(
        profile_id="p-statut",
        created_utc=datetime(2026, 11, 15, tzinfo=UTC),
        status="COMPLETE",
        goals=[Goal(goal_id="g1", label="projet", priority="besoin", horizon_years=5.0)],
        tolerance_declared=Score(value=40),
        investable_wealth=10_000,
        max_acceptable_loss_cad=1_500,
        knowledge_level="intermediaire",
    )
    return base.model_copy(update=update)


def _assert_portfolio(res, kind):
    d = res.decision
    assert d.kind == kind
    assert d.positions, "chaque profil doit recevoir un portefeuille"
    assert abs(sum(p.weight for p in d.positions) - 1) < 1e-9
    facts = {f.fact_id: f.value for f in d.facts}
    assert facts.get("r2.n_blocking") == 0  # le Judge n'accepte aucune limite bloquante dépassée
    assert verify_decision(d).ok  # chaque nombre de l'explication vient d'un fait qu'elle cite
    return d, facts


def test_protection_by_the_dollar_rule_builds_the_most_prudent_portfolio():
    """250 $ sur 10 000 $ : même sans actions, la perte de planification dépasse l* (cas vu en production)."""
    d, facts = _assert_portfolio(build_portfolio(_profile(max_acceptable_loss_cad=250), AS_OF), "protection")
    assert facts["status.l_star"] < facts["status.min_l_plan"]
    assert not {p.asset_id for p in d.positions} & SINGLE_OR_CRYPTO
    why = d.explanation.why[0]
    assert why.text_fr.startswith("Statut protection") and {"status.l_star", "status.min_l_plan"} <= set(why.fact_ids)
    assert any("serait levé" in s.text_fr for s in d.explanation.what_would_change)
    assert any(s.fact_ids == ["status.human_referral"] for s in d.explanation.limits)


def test_protection_requested_by_the_profile_still_frames_the_request():
    res = build_portfolio(_profile(status=ProfileStatus.PROTECTION), AS_OF, request=Request("TSLA", amount_cad=500))
    d, _ = _assert_portfolio(res, "protection")  # le statut prime sur l'issue de la demande
    assert "TSLA" not in {p.asset_id for p in d.positions}
    assert any(s.fact_ids == ["status.profile"] for s in d.explanation.why)


@pytest.mark.parametrize(
    ("update", "kind"),
    [
        ({"investable_wealth": None, "missing_info": ["investable_wealth"]}, "incomplet"),
        ({"status": ProfileStatus.INCOMPLETE, "missing_info": ["tolerance_tested"]}, "position_attente"),
    ],
)
def test_incomplete_profiles_get_a_capped_portfolio(update, kind):
    d, facts = _assert_portfolio(build_portfolio(_profile(**update), AS_OF), kind)
    assert facts["status.level_cap"] == "N2" and int(facts["level"][1]) <= 2
    assert not {p.asset_id for p in d.positions} & SINGLE_OR_CRYPTO
    todo = [s for s in d.explanation.what_would_change if s.fact_ids == ["status.todo"]]
    assert todo and todo[0].text_fr == f"Compléter : {facts['status.todo']}."


def test_complete_profile_is_unchanged():
    _, facts = _assert_portfolio(build_portfolio(_profile(max_acceptable_loss_cad=4_000), AS_OF), "proposition")
    assert not any(k.startswith("status.") for k in facts)  # aucun énoncé de statut sans statut
