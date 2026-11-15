"""Adaptateur questionnaire (brain) -> InvestorProfile : un seul chemin par fait, min par defaut."""

from __future__ import annotations

import pytest

from alphaforge.finance.contracts.profile import Goal
from alphaforge.finance.policy import LV, QuestionnaireScores, aggregate_tolerance, compile_profile
from alphaforge.finance.policy.adapter import load_adapter_config

from ._personas import AS_OF, amira, robert


def q(**kw):
    base = dict(
        M_cad=150_000,
        tolerance_subscores={"declared": 0.8, "scenarios": 0.7, "revealed": 0.75, "test": 0.72},
        capacity_score=0.9,
        L_cad=60_000,
        L_confirmed=True,
    )
    base.update(kw)
    return QuestionnaireScores(**base)


def test_min_is_default_aggregation():
    cfg = load_adapter_config()
    assert cfg["tolerance"]["aggregation"] == "min"
    assert aggregate_tolerance({"declared": 0.8, "test": 0.5}, cfg) == 0.5
    brain = {**cfg, "tolerance": {**cfg["tolerance"], "aggregation": "mean_minus_half_range"}}
    # (0.3*0.8 + 0.2*0.5)/0.5 - 0.5*0.3 = 0.68 - 0.15
    assert aggregate_tolerance({"declared": 0.8, "test": 0.5}, brain) == pytest.approx(0.53)


def test_mapping_single_path():
    r = compile_profile(amira(max_acceptable_loss_pct=0.30), AS_OF, questionnaire=q())
    # L remplace le % declare (TR-03 deja dans L) : l_declared = 60 000 / 150 000 = 0.40, pas 0.30
    assert any(t["rule"] == "dollar_rule.l_declared" and t["output"] == pytest.approx(0.40) for t in r.trace)
    # tolerance = min des sous-scores, tolerance_tested retire (pas de double comptage du test)
    assert r.tolerance["person"]["Tb"] == pytest.approx(70.0)
    assert r.capacity["C"] <= 90.0


def test_liquid_pocket_removes_goals_and_wealth():
    gs = [
        amira().goals[0],
        Goal(goal_id="maison", label="mise de fonds", priority="besoin", horizon_years=2, amount=30_000),
    ]
    base = compile_profile(amira(goals=gs), AS_OF)
    assert base.level == "N4"  # le seau court ne plafonne pas le seau long (deja hors du risque)
    r = compile_profile(amira(goals=gs), AS_OF, questionnaire=q(poche_liquide_cad=30_000, covered_goal_ids=["maison"]))
    assert r.policy.missing_defaults == [] and r.buckets[0]["kind"] == "poche_liquide"
    assert [b["goal_id"] for b in r.buckets] == ["poche_liquide"]  # pas de second seau « maison »
    assert any(t["rule"] == "questionnaire.M_risque" and t["output"] == 120_000 for t in r.trace)


def test_sequence_reserve_not_doubled():
    g = Goal(goal_id="retraite", label="retraite", priority="souhait", horizon_years=4, recurring_withdrawal=30_000)
    own = compile_profile(robert(goals=[g]), AS_OF)
    assert any(b.get("kind") == "reserve_retraits" for b in own.buckets) and own.horizon_years == pytest.approx(7)
    r = compile_profile(
        robert(goals=[g]),
        AS_OF,
        questionnaire=QuestionnaireScores(
            M_cad=900_000, poche_liquide_cad=90_000, sequence_reserve_years=3, L_cad=120_000
        ),
    )
    assert not any(b.get("kind") == "reserve_retraits" for b in r.buckets)
    assert r.horizon_years == pytest.approx(7)


@pytest.mark.parametrize(
    "field,vals",
    [
        ("capacity_score", [0.9, 0.6, 0.4, 0.1]),
        ("L_cad", [80_000, 60_000, 40_000, 25_000]),
    ],
)
def test_adapter_monotone(field, vals):
    lv = [LV.index(compile_profile(amira(), AS_OF, questionnaire=q(**{field: v})).level) for v in vals]
    assert lv == sorted(lv, reverse=True)


def test_lower_subscore_never_raises():
    lv = []
    for t in (0.9, 0.7, 0.5, 0.3, 0.1):
        sub = {"declared": 0.8, "scenarios": 0.8, "revealed": 0.8, "test": t}
        lv.append(LV.index(compile_profile(amira(), AS_OF, questionnaire=q(tolerance_subscores=sub)).level))
    assert lv == sorted(lv, reverse=True)
