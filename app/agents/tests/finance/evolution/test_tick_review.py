"""Non-régression des corrections de la revue indépendante (2026-11-15), sur les stubs de ``test_tick_synthetic``.

- une limite resserrée par F1 à niveau égal impose un REOPTIMIZE (et un mouvement immédiat) ;
- la suite d'un glissement à la hausse reste plafonnée par le budget de rotation, mois après mois ;
- un Judge indisponible ne laisse passer aucun déplacement d'overlay (α = 0) ;
- unités des faits des déclencheurs (mois, CAD) et identifiants uniques ;
- flux effectif : un retrait plus grand que le portefeuille est plafonné et la performance reste cohérente ;
- GOAL_NEED_12M se déclenche au premier tick quand l'objectif est déjà à moins de 12 mois.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from alphaforge.finance.contracts import Limit, PolicySpec, Selector
from alphaforge.finance.contracts.evolution import OverlayState, TriggerFired
from alphaforge.finance.contracts.profile import Goal
from alphaforge.finance.evolution import tick as T
from alphaforge.finance.evolution.triggers import TriggerState, evaluate

from .test_tick_synthetic import (
    APPROVED,
    ASSETS,
    CFG,
    M1,
    M2,
    ORIGIN,
    POLICY,
    TARGET,
    TARGET_N4,
    Engine,
    _frame,
    _profile,
    _start,
)


@pytest.fixture
def engine(monkeypatch) -> Engine:
    import alphaforge.finance.policy as policy_pkg

    eng = Engine()
    monkeypatch.setattr(T, "_judge", lambda *a, **k: APPROVED)
    monkeypatch.setattr(policy_pkg, "compile_profile", eng.compile)
    return eng


def _policy_with(max_a: float) -> PolicySpec:
    lim = Limit(rule_id="conc.a", kind="asset_weight", selector=Selector(assets=["A"]), max=max_a, derived_from="test")
    return PolicySpec(
        policy_id=f"test-{max_a}",
        profile_id="test",
        profile_version=1,
        created_utc=datetime(2026, 11, 15, tzinfo=UTC),
        universe=ASSETS,
        limits=[lim],
    )


def test_tightened_limit_same_level_reoptimizes_at_once(engine, monkeypatch):
    import alphaforge.finance.policy as policy_pkg

    loose, tight = _policy_with(0.60), _policy_with(0.40)
    monkeypatch.setattr(
        policy_pkg,
        "compile_profile",
        lambda p, d: SimpleNamespace(level="N3", policy=loose if d <= ORIGIN else tight, horizon_years=None, trace=[]),
    )
    engine.targets["N3"] = dict(TARGET)
    traj = _start(engine, _frame())
    traj.policy = loose
    new_target = {"A": 0.40, "B": 0.35, "C": 0.25}
    engine.build = lambda p, d: T.BuildOutcome(target=dict(new_target), policy=tight, level="N3", decision=None)
    traj.build_fn = engine.build
    out = T.tick(traj, M1)
    assert out.version.event.action == "REOPTIMIZE"
    assert out.version.weights == pytest.approx(new_target, abs=1e-9)  # resserrement : d'un coup
    assert any(f.fact_id.endswith("limites_resserrees") for f in out.facts)
    assert traj.policy is tight


def test_glide_continues_under_turnover_cap(engine):
    traj = _start(engine, _frame())
    engine.level = "N4"
    first = T.tick(traj, M1)
    assert first.version.event.action == "REOPTIMIZE" and traj.glide_pending
    second = T.tick(traj, M2)
    assert second.version.event.action == "REOPTIMIZE"
    assert second.version.event.turnover_twoway <= CFG.trading.max_turnover_tick + 1e-9
    assert second.version.target == pytest.approx(TARGET_N4)


def test_unavailable_judge_blocks_overlay_shift(engine, monkeypatch):
    traj = _start(engine, _frame())
    moved = {"A": 0.60, "B": 0.25, "C": 0.15}
    st = OverlayState(
        name="trend_tilt",
        active=True,
        gate="passe",
        gate_reason_fr="test",
        signal=1.0,
        delta={"A": 0.10, "B": -0.05, "C": -0.05},
    )
    traj.overlay_fn = lambda *a: (dict(moved), [st], [])
    traj.overlay_active = {"trend_tilt"}
    monkeypatch.setattr(T, "_judge", lambda *a, **k: None)
    target, states, _facts, alpha = T._overlays_judged(
        traj, traj.pit.with_horizon(M1), pd.Timestamp(M1), dict(TARGET), 1.0, date(2020, 2, 29)
    )
    assert alpha == 0.0 and target == pytest.approx(TARGET)
    assert all(not s.delta for s in states)


def test_trigger_units_and_unique_ids(engine, monkeypatch):
    trig = [
        TriggerFired(
            code="KYC_AGE",
            blocking=False,
            value=36,
            threshold=36,
            threshold_source="x#review.kyc",
            message_fr="KYC de 36 mois.",
        ),
        TriggerFired(
            code="DRAWDOWN_LIMIT",
            blocking=False,
            value=0.2,
            threshold=0.15,
            threshold_source="profile.max_acceptable_loss_pct",
            message_fr="baisse en %",
        ),
        TriggerFired(
            code="DRAWDOWN_LIMIT",
            blocking=False,
            value=5000.0,
            threshold=3000.0,
            threshold_source="profile.max_acceptable_loss_cad",
            message_fr="baisse en CAD",
        ),
    ]
    monkeypatch.setattr(T, "evaluate", lambda *a, **k: trig)
    traj = _start(engine, _frame())
    out = T.tick(traj, M1)
    units = {f.fact_id.split("declencheur.")[1]: f.unit for f in out.facts if "declencheur." in f.fact_id}
    assert units == {"KYC_AGE": "mois", "DRAWDOWN_LIMIT": "%", "DRAWDOWN_LIMIT.2": "CAD"}


def test_withdrawal_larger_than_value_is_capped(engine):
    traj = _start(engine, _frame())
    v0 = traj.value_cad
    out = T.tick(traj, M1, flow_cad=-10 * v0)
    assert out.version.value_cad == pytest.approx(0.0, abs=1e-6)
    snap = traj.perf.snapshot()
    assert snap.invested_cad == pytest.approx(0.0, abs=1e-6)  # flux effectif = −valeur
    assert traj.perf.returns[-1] == pytest.approx(0.0, abs=1e-9)  # rendements nuls (_frame) : r_net = 0


def test_goal_need_fires_on_first_tick_when_already_close():
    from alphaforge.finance.policy import compile_profile

    p = _profile().model_copy(
        update={
            "goals": [
                Goal(
                    goal_id="maison",
                    label="mise de fonds",
                    priority="besoin",
                    amount=20_000,
                    target_date=date(2020, 9, 30),
                )
            ]
        }
    )
    comp = compile_profile(p, date(2020, 2, 29))
    st = TriggerState(
        as_of=date(2020, 2, 29), origin=ORIGIN, profile=p, level_prev=comp.level, level_now=comp.level, compile_now=comp
    )
    assert any(t.code == "GOAL_NEED_12M" for t in evaluate(st, CFG))
    later = TriggerState(
        as_of=date(2020, 3, 31), origin=ORIGIN, profile=p, level_prev=comp.level, level_now=comp.level, compile_now=comp
    )
    assert not any(t.code == "GOAL_NEED_12M" for t in evaluate(later, CFG))
    assert POLICY is not None
