"""Déclencheurs du tick mensuel. Profils fictifs construits ici (valeurs de test, aucune tirée des fiches persona)."""
from __future__ import annotations

import calendar
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from alphaforge.finance.contracts.evolution import PerfSnapshot
from alphaforge.finance.contracts.profile import Goal, Income, InvestorProfile, Score
from alphaforge.finance.evolution.config import load_config
from alphaforge.finance.evolution.triggers import (
    LEVELS,
    TriggerState,
    evaluate,
    level_source,
    months_between,
    profile_at,
)
from alphaforge.finance.policy.compiler import compile_profile

ORIGIN = date(2026, 1, 31)
CFG = load_config()


def _profile(goals: list[Goal], **kw) -> InvestorProfile:
    base = dict(
        profile_id="test", created_utc=datetime(2026, 1, 1, tzinfo=UTC), status="COMPLETE", age=45,
        knowledge_level="intermediaire", goals=goals,
        tolerance_declared=Score(value=60, confidence=0.7), tolerance_tested=Score(value=60, confidence=0.7),
        composure=Score(value=60), investable_wealth=300_000, monthly_expenses=5_000, emergency_fund_months=6,
        income=Income(annual_amount=120_000, variability="stable"),
    )
    base.update(kw)
    return InvestorProfile(**base)


def _month(i: int) -> date:
    """Fin du i-ème mois après ORIGIN."""
    y, m = divmod(ORIGIN.month - 1 + i, 12)
    return date(ORIGIN.year + y, m + 1, calendar.monthrange(ORIGIN.year + y, m + 1)[1])


def _perf(value=100_000.0, invested=100_000.0, cur_dd=0.0) -> PerfSnapshot:
    return PerfSnapshot(months=1, value_cad=value, invested_cad=invested, twr_cum=0.0, twr_ann=None, mwr_ann=None,
                        cagr=None, max_drawdown=cur_dd, current_drawdown=cur_dd, high_water_mark_cad=value,
                        months_underwater=0)


def _state(profile, as_of=ORIGIN, **kw) -> TriggerState:
    cr = kw.pop("compile_now", None) or compile_profile(profile, as_of)
    base = dict(as_of=as_of, origin=ORIGIN, profile=profile, level_prev=kw.pop("level_prev", cr.level),
                level_now=cr.level, compile_now=cr, value_cad=100_000.0)
    base.update(kw)
    return TriggerState(**base)


def _codes(fired):
    return [t.code for t in fired]


# --------------------------------------------------------------------------- outils


def test_months_between():
    assert months_between(date(2026, 1, 31), date(2026, 2, 28)) == 1
    assert months_between(date(2026, 1, 15), date(2026, 2, 14)) == 0
    assert months_between(date(2026, 1, 15), date(2027, 1, 15)) == 12
    assert months_between(date(2027, 1, 15), date(2026, 1, 15)) == -12


def test_profile_at_does_not_mutate_and_shortens_horizon():
    p = _profile([Goal(goal_id="maison", label="maison", priority="envie", horizon_years=6)])
    before = p.model_dump()
    q = profile_at(p, ORIGIN)
    assert p.model_dump() == before
    assert p.goals[0].target_date is None and p.goals[0].horizon_years == 6
    assert q.goals[0].horizon_years is None and q.goals[0].target_date is not None
    h0 = compile_profile(q, ORIGIN).horizon_years
    h1 = compile_profile(q, _month(24)).horizon_years
    assert h0 == pytest.approx(6, abs=0.01)
    assert h1 == pytest.approx(4, abs=0.02)
    # sans profile_at, l'horizon resterait figé
    assert compile_profile(p, _month(24)).horizon_years == pytest.approx(6)


# --------------------------------------------------------------------------- glidepath


def _glide_profile():
    return profile_at(_profile([Goal(goal_id="projet", label="projet", priority="envie", horizon_years=8)]), ORIGIN)


def test_glidepath_equity_never_increases():
    p = _glide_profile()
    caps, levels = [], []
    for i in range(0, 8 * 12, 3):
        cr = compile_profile(p, _month(i))
        caps.append(cr.e_cap)
        levels.append(LEVELS.index(cr.level))
    assert all(b <= a + 1e-12 for a, b in zip(caps, caps[1:], strict=False))
    assert all(b <= a for a, b in zip(levels, levels[1:], strict=False))
    assert levels[0] > levels[-1]


def test_horizon_level_change_fires_exactly_when_level_changes():
    p = _glide_profile()
    prev = compile_profile(p, _month(0)).level
    changes = 0
    for i in range(1, 8 * 12):
        cr = compile_profile(p, _month(i))
        fired = evaluate(_state(p, _month(i), compile_now=cr, level_prev=prev), CFG)
        hl = [t for t in fired if t.code == "HORIZON_LEVEL_CHANGE"]
        if cr.level != prev:
            changes += 1
            assert len(hl) == 1 and not hl[0].blocking
            assert hl[0].value == cr.level and hl[0].threshold == prev
            assert hl[0].threshold_source.startswith("risk_levels.yaml@")
        else:
            assert not hl
        prev = cr.level
    assert changes >= 1


def test_level_source_points_to_horizon_cap_when_horizon_binds():
    p = _glide_profile()
    assert level_source(compile_profile(p, _month(84))).endswith("#horizon_cap[0]")      # < 1 an : plafond N0
    assert level_source(compile_profile(p, _month(30))).endswith("#dollar_rule.level_after")  # règle des dollars


# --------------------------------------------------------------------------- objectifs, pertes


def test_goal_need_12m_once_inside_window():
    p = profile_at(_profile([
        Goal(goal_id="mise_de_fonds", label="mise de fonds", priority="besoin", horizon_years=2, amount=50_000),
        Goal(goal_id="long", label="long terme", priority="souhait", horizon_years=20),
    ]), ORIGIN)
    fired_months = []
    for i in range(0, 24):
        fired = evaluate(_state(p, _month(i)), CFG)
        g = [t for t in fired if t.code == "GOAL_NEED_12M"]
        if g:
            assert g[0].value == "mise_de_fonds" and not g[0].blocking
            fired_months.append(months_between(_month(i), p.goals[0].target_date))
    assert fired_months == [12]


def test_drawdown_limit_blocking():
    p = _profile([Goal(goal_id="g", label="g", priority="envie", horizon_years=10)], max_acceptable_loss_pct=0.2,
                 max_acceptable_loss_cad=15_000)
    ok = evaluate(_state(p, perf=_perf(cur_dd=0.19, value=90_000)), CFG)
    assert "DRAWDOWN_LIMIT" not in _codes(ok)
    hit = [t for t in evaluate(_state(p, perf=_perf(cur_dd=0.21, value=80_000)), CFG) if t.code == "DRAWDOWN_LIMIT"]
    assert {t.threshold_source for t in hit} == {"profile.max_acceptable_loss_pct", "profile.max_acceptable_loss_cad"}
    assert all(t.blocking for t in hit)


# --------------------------------------------------------------------------- KYC, revue, événements, flux


def test_kyc_36_vs_12_months():
    p = _profile([Goal(goal_id="g", label="g", priority="envie", horizon_years=20)])
    cr = compile_profile(p, ORIGIN)
    at12, at36 = _month(12), _month(36)
    assert "KYC_AGE" not in _codes(evaluate(_state(p, at12, compile_now=cr), CFG))
    k = [t for t in evaluate(_state(p, at12, compile_now=cr, managed_account=True), CFG) if t.code == "KYC_AGE"]
    assert k and k[0].blocking and k[0].threshold == 12 and "31-103" in k[0].message_fr
    assert "KYC_AGE" not in _codes(evaluate(_state(p, _month(35), compile_now=cr), CFG))
    k = [t for t in evaluate(_state(p, at36, compile_now=cr), CFG) if t.code == "KYC_AGE"]
    assert k and k[0].threshold == 36
    assert "KYC_AGE" not in _codes(evaluate(_state(p, at36, compile_now=cr, kyc_confirmed=_month(30)), CFG))


def test_review_due():
    p = _profile([Goal(goal_id="g", label="g", priority="envie", horizon_years=20)])
    cr = compile_profile(p, ORIGIN)
    assert "REVIEW_DUE" not in _codes(evaluate(_state(p, _month(11), compile_now=cr), CFG))
    assert "REVIEW_DUE" in _codes(evaluate(_state(p, _month(12), compile_now=cr), CFG))


def test_life_event_only_after_its_date():
    p = _profile([Goal(goal_id="g", label="g", priority="envie", horizon_years=20)])
    cr = compile_profile(p, ORIGIN)
    ev = {"code": "naissance", "date": _month(3)}
    assert "LIFE_EVENT" not in _codes(evaluate(_state(p, _month(2), compile_now=cr, life_event=ev), CFG))
    f = [t for t in evaluate(_state(p, _month(3), compile_now=cr, life_event=ev), CFG) if t.code == "LIFE_EVENT"]
    assert f and f[0].blocking and f[0].value == "naissance"


def test_large_flow_threshold():
    p = _profile([Goal(goal_id="g", label="g", priority="envie", horizon_years=20)])
    cr = compile_profile(p, ORIGIN)
    share = CFG.flows.large_flow_share
    below = evaluate(_state(p, compile_now=cr, flow_cad=share * 100_000 - 1), CFG)
    assert "LARGE_FLOW" not in _codes(below)
    for flow in (share * 100_000, -share * 100_000):
        f = [t for t in evaluate(_state(p, compile_now=cr, flow_cad=flow), CFG) if t.code == "LARGE_FLOW"]
        assert f and not f[0].blocking


def test_judge_drift_and_overlay():
    p = _profile([Goal(goal_id="g", label="g", priority="envie", horizon_years=20)])
    cr = compile_profile(p, ORIGIN)
    judge = SimpleNamespace(blocking_violations=("cap.crypto", "band.equity"))
    f = evaluate(_state(p, compile_now=cr, judge_drift=judge, overlay_signal_changes=["trend_tilt"]), CFG)
    j = [t for t in f if t.code == "JUDGE_VIOLATION_DRIFT"]
    assert j and not j[0].blocking and j[0].value == "cap.crypto,band.equity"
    o = [t for t in f if t.code == "OVERLAY_SIGNAL"]
    assert o and o[0].threshold_source == CFG.src("overlays.trend_tilt")


# --------------------------------------------------------------------------- lexique


FORBIDDEN = ("achetez", "vendez", "recommandons", "recommand", "conseill", "garanti")


def test_messages_lexicon():
    p = profile_at(_profile([Goal(goal_id="b", label="b", priority="besoin", horizon_years=1, amount=10_000)],
                            max_acceptable_loss_pct=0.1, max_acceptable_loss_cad=1_000), ORIGIN)
    cr = compile_profile(p, _month(40))
    s = _state(p, _month(40), compile_now=cr, level_prev="N5", perf=_perf(value=50_000, cur_dd=0.5),
               judge_drift=SimpleNamespace(blocking_violations=("x",)), flow_cad=50_000.0, managed_account=True,
               life_event={"code": "divorce", "date": _month(1)}, overlay_signal_changes=["tsmom"])
    fired = evaluate(s, CFG)
    assert len(set(_codes(fired))) >= 7
    for t in fired:
        msg = t.message_fr.lower()
        assert msg and not any(w in msg for w in FORBIDDEN), msg
