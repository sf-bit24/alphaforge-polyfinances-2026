"""ProfileView (app/CONTRACTS.md §3.3) → InvestorProfile → compile_profile."""

from datetime import UTC, date, datetime

from alphaforge.finance.policy import compile_profile
from alphaforge.finance.policy.from_profile_view import investor_profile_from_view

AS_OF = date(2026, 9, 30)
LEVELS = ["N0", "N1", "N2", "N3", "N4", "N5"]


def _view(tol="high", cap="high", amount=60_000, max_loss=24_000, band="gt10", years=None, excl=(), interests=()):
    facts = [
        {"field": "horizon.horizon_band", "value": band},
        {"field": "objective.goal", "value": "growth"},
        {"field": "context.amount_cad", "value": amount},
        {"field": "risk_capacity.max_loss_cad", "value": max_loss},
        {"field": "risk_capacity.emergency_fund", "value": 6},
        {"field": "risk_capacity.income_stability", "value": "stable"},
        {"field": "preferences.exclusions", "value": list(excl)},
        {"field": "preferences.interests", "value": list(interests)},
        {"field": "preferences.esg_importance", "value": 4 if excl else 1},
    ]
    if years is not None:
        facts.append({"field": "horizon.horizon_years", "value": years})
    return {
        "knowledge_level": "intermediate",
        "risk": {"tolerance": tol, "capacity": cap, "effective": min(tol, cap)},
        "facts": facts,
    }


def _p(**kw):
    return investor_profile_from_view(
        _view(**kw), "8f0c1c2e-0000-4000-8000-000000000001", created_utc=datetime(2026, 11, 14, tzinfo=UTC)
    )


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
    v = _view()
    v["facts"] = [x for x in v["facts"] if x["field"] != "context.amount_cad"]
    p = investor_profile_from_view(v, "8f0c1c2e-0000-4000-8000-000000000002")
    assert p.status.value == "INCOMPLETE" and p.investable_wealth is None


def test_style_inputs_read_only_fields_declared_by_the_questionnaire():
    """Un champ renommé côté profil ne doit pas disparaître en silence de l'étape 0 (la variable resterait vide)."""
    import inspect
    import re

    from alphaforge.finance.policy import from_profile_view
    from alphaforge.profile.questionnaire import Questionnaire

    src = inspect.getsource(from_profile_view.style_inputs_from_view)
    read = set(re.findall(r'g\("([^"]+)"\)', src))  # tout argument de g(), même mal orthographié
    read |= {f"knowledge.{k}" for k in re.findall(r'"(quiz_[a-z_]+)"', src)}
    assert len(read) >= 20, sorted(read)  # l'extraction elle-même ne doit pas se vider
    missing = sorted(read - set(Questionnaire.load().fields))
    assert missing == [], missing


def test_zero_declared_loss_is_kept_and_compiles_to_protection():
    """Issue #91 : la tranche la plus prudente écrit max_loss_cad = 0 ; « je ne peux rien perdre » reste une limite."""
    p = _p(amount=10_000, max_loss=0)
    assert p.max_acceptable_loss_cad == 0
    res = compile_profile(p, AS_OF)
    assert any(t["rule"] == "dollar_rule.l_declared" and t["output"] == 0 for t in res.trace)
    # l* = 0 sous la perte de planification des quasi-liquidités : protection, mandat le plus liquide, sans actions
    assert res.l_star == 0 and res.decision_kind == "protection" and res.level == "N0" and res.e_cap == 0
    assert {lim.rule_id: lim for lim in res.limits}["alloc.cash_like"].min == 1.0


def test_absent_declared_loss_stays_absent():
    v = _view()
    v["facts"] = [x for x in v["facts"] if x["field"] != "risk_capacity.max_loss_cad"]
    p = investor_profile_from_view(v, "8f0c1c2e-0000-4000-8000-000000000003")
    assert p.max_acceptable_loss_cad is None
