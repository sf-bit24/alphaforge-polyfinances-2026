"""Portefeuille existant (``portefeuille-existant.md``, A2) → ``InvestorProfile.holdings`` → F1 (pur, sans numpy)."""

from datetime import UTC, date, datetime

from alphaforge.finance.contracts.profile import AccountType, ClaimKind
from alphaforge.finance.policy import compile_profile
from alphaforge.finance.policy.from_profile_view import holdings_from_existing_portfolio, investor_profile_from_view

AS_OF = date(2026, 9, 30)
CLIENT = "8f0c1c2e-0000-4000-8000-0000000000aa"


def _view(amount=100_000):
    return {
        "knowledge_level": "intermediate",
        "risk": {"tolerance": "medium", "capacity": "medium", "effective": "medium"},
        "facts": [
            {"field": "horizon.horizon_band", "value": "gt10"},
            {"field": "objective.goal", "value": "growth"},
            {"field": "context.amount_cad", "value": amount},
            {"field": "risk_capacity.max_loss_cad", "value": 20_000},
            {"field": "risk_capacity.emergency_fund", "value": 6},
            {"field": "risk_capacity.income_stability", "value": "stable"},
        ],
    }


def _position(pid, ticker, value_cad, *, asset_class="equity", account="tfsa", resolved=True, raw=None):
    return {
        "id": pid,
        "raw": raw or ticker or "?",
        "ticker": ticker,
        "asset_class": asset_class,
        "account_type": account,
        "value_cad": value_cad,
        "resolved": resolved,
    }


def _portfolio(*positions, status="confirmed"):
    return {"view": {"status": status, "positions": list(positions), "unresolved": []}, "turn": 3}


def _profile(existing=None, amount=100_000):
    return investor_profile_from_view(
        _view(amount), CLIENT, created_utc=datetime(2026, 11, 14, tzinfo=UTC), existing_portfolio=existing
    )


def test_valued_positions_become_holdings_in_cad():
    holdings, claims = holdings_from_existing_portfolio(
        _portfolio(
            _position("p1", "RY.TO", 40_000.0, account="rrsp"),
            _position("p2", "XBB.TO", 12_500.5, asset_class="etf_bond", account="unknown"),
            _position("p3", None, 3_000.0, asset_class="cash", account="non_registered"),
        )
    )
    assert [(h.ticker, h.market_value, h.currency, h.account) for h in holdings] == [
        ("RY.TO", 40_000.0, "CAD", AccountType.REER),
        ("XBB.TO", 12_500.5, "CAD", AccountType.AUTRE),
    ]
    assert claims == []  # l'encaisse n'est pas une position, sans être signalée


def test_unvalued_position_is_ignored_and_reported():
    holdings, claims = holdings_from_existing_portfolio(
        _portfolio(
            _position("p1", "RY.TO", 40_000.0),
            _position("p2", None, None, resolved=False, raw="Fonds maison XYZ 120 parts"),
        )
    )
    assert [h.ticker for h in holdings] == ["RY.TO"]
    assert len(claims) == 1 and claims[0].classification is ClaimKind.DECLARE_NON_VERIFIE
    assert "Fonds maison XYZ 120 parts" in claims[0].text


def test_unconfirmed_portfolio_is_not_used():
    holdings, claims = holdings_from_existing_portfolio(_portfolio(_position("p1", "RY.TO", 40_000.0), status="draft"))
    assert holdings == [] and "non confirmé" in claims[0].text


def test_no_existing_portfolio_changes_nothing():
    assert holdings_from_existing_portfolio(None) == ([], [])
    assert holdings_from_existing_portfolio({"view": {"status": "confirmed", "positions": []}}) == ([], [])
    before = _profile()
    assert before.holdings == [] and before.claims == []
    assert before.model_dump(exclude={"created_utc"}) == _profile(existing=None).model_dump(exclude={"created_utc"})
    a, b = compile_profile(before, AS_OF), compile_profile(_profile(), AS_OF)
    assert a.emphasis_rules == b.emphasis_rules and a.emphasis == b.emphasis and a.level == b.level


def test_unvalued_positions_keep_the_profile_complete_and_the_level():
    plain = _profile()
    noisy = _profile(_portfolio(_position("p1", None, None, resolved=False, raw="?")))
    assert noisy.status == plain.status and noisy.missing_info == plain.missing_info
    assert noisy.consistency_flags == []  # un drapeau pénaliserait le niveau de risque
    assert compile_profile(noisy, AS_OF).level == compile_profile(plain, AS_OF).level


def test_a_forty_percent_position_fires_the_concentration_emphasis():
    concentrated = _profile(_portfolio(_position("p1", "RY.TO", 40_000.0)))
    assert [h.ticker for h in concentrated.holdings] == ["RY.TO"]
    with_holding = compile_profile(concentrated, AS_OF)
    without = compile_profile(_profile(), AS_OF)
    assert "diversity.concentrated" in with_holding.emphasis_rules
    assert "diversity.concentrated" not in without.emphasis_rules
    assert with_holding.emphasis["diversity"] > without.emphasis["diversity"]
    assert with_holding.level == without.level  # l'emphase oriente l'explication, jamais le mandat


def test_a_small_position_does_not_fire_it():
    small = compile_profile(_profile(_portfolio(_position("p1", "RY.TO", 5_000.0))), AS_OF)
    assert "diversity.concentrated" not in small.emphasis_rules
