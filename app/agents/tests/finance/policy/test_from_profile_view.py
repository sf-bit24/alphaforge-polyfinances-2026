"""ProfileView (app/CONTRACTS.md §3.3) → InvestorProfile → compile_profile."""
from datetime import date, datetime, timezone

from alphaforge.finance.policy import compile_profile
from alphaforge.finance.policy.from_profile_view import investor_profile_from_view

AS_OF = date(2026, 9, 30)
LEVELS = ["N0", "N1", "N2", "N3", "N4", "N5"]


def _view(tol="high", cap="high", amount=60_000, max_loss=24_000, band="gt10", years=None, excl=(), interests=()):
    facts = [{"field": "horizon.horizon_band", "value": band}, {"field": "objective.goal", "value": "growth"},
             {"field": "context.amount_cad", "value": amount}, {"field": "risk_capacity.max_loss_cad", "value": max_loss},
             {"field": "risk_capacity.emergency_fund", "value": 6}, {"field": "risk_capacity.income_stability", "value": "stable"},
             {"field": "preferences.exclusions", "value": list(excl)}, {"field": "preferences.interests", "value": list(interests)},
             {"field": "preferences.esg_importance", "value": 4 if excl else 1}]
    if years is not None:
        facts.append({"field": "horizon.horizon_years", "value": years})
    return {"knowledge_level": "intermediate", "risk": {"tolerance": tol, "capacity": cap, "effective": min(tol, cap)},
            "facts": facts}


def _p(**kw):
    return investor_profile_from_view(_view(**kw), "8f0c1c2e-0000-4000-8000-000000000001",
                                      created_utc=datetime(2026, 11, 14, tzinfo=timezone.utc))


def test_valid_profile_and_compiles():
    res = compile_profile(_p(), AS_OF)
    assert res.policy is not None and res.level in LEVELS


def test_app_capacity_caps_the_level():
    hi = compile_profile(_p(tol="high", cap="high"), AS_OF).level
    lo = compile_profile(_p(tol="high", cap="low"), AS_OF).level
    assert LEVELS.index(lo) <= LEVELS.index(hi)
    assert LEVELS.index(lo) <= 1


def test_fossil_exclusion_maps_to_tickers():
    p = _p(excl=["fossil_fuels"])
    assert p.preferences.value_filters[0].per_ticker == {"XOM": "exclu", "CNQ.TO": "exclu", "ENB.TO": "exclu"}


def test_missing_amount_is_incomplete_not_invented():
    v = _view(); v["facts"] = [x for x in v["facts"] if x["field"] != "context.amount_cad"]
    p = investor_profile_from_view(v, "8f0c1c2e-0000-4000-8000-000000000002")
    assert p.status.value == "INCOMPLETE" and p.investable_wealth is None
