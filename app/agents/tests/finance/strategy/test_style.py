"""Étape 0, partie pure : style, préférence, garde-fous, position dans la bande, K (sûr en CI)."""

from __future__ import annotations

import pytest
import yaml

from alphaforge.finance.strategy import StyleInputs, band_target, derive_style, load_strategy
from alphaforge.finance.strategy.config import DEFAULT_PATH, StrategyConfig
from alphaforge.finance.strategy.style import behavior_flags, k_rule

from ._helpers import amira, make_comp, mateo, robert

CFG = load_strategy()


@pytest.mark.parametrize(
    ("level", "style"),
    [
        ("N0", "defensive"),
        ("N1", "defensive"),
        ("N2", "defensive"),
        ("N3", "dynamique"),
        ("N4", "dynamique"),
        ("N5", "offensive"),
    ],
)
def test_level_to_style_team_convention(level, style):
    comp = make_comp(level=level, level_from_R=level)
    assert derive_style(comp).from_level == style


def test_config_rejects_non_monotonic_mapping():
    data = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    data["level_to_style"]["N4"] = "defensive"
    with pytest.raises(ValueError, match="monotone"):
        StrategyConfig.model_validate(data)


def test_config_sha_and_version():
    assert CFG.version == "0.1.0" and len(CFG.sha256) == 64
    assert CFG.src("band").startswith("strategy.yaml@0.1.0#")


def test_descent_always_allowed():
    comp = make_comp(level="N5", level_from_R="N5", R=80, T=80, C=95, e_min=0.8, e_cap=1.0)
    d = derive_style(comp, StyleInputs(explicit_preference="defensive"))
    assert (d.from_level, d.style, d.shift) == ("offensive", "defensive", -2)


def test_ascent_capped_to_one_notch():
    d = derive_style(mateo(), StyleInputs(explicit_preference="offensive"))
    assert d.style == "dynamique" and d.shift == 1
    assert any("plafonnée" in r for r in d.refused)


def test_goal_growth_is_a_composition_preference_only():
    base, growth = derive_style(amira()), derive_style(amira(), StyleInputs(goal="growth"))
    assert growth.style == "offensive" and growth.preference_source == "objective.goal=growth"
    assert growth.pi == base.pi  # le besoin de rendement ne change jamais la position dans la bande


@pytest.mark.parametrize(
    ("comp_kw", "inputs_kw", "reason"),
    [
        ({"status": "INCOMPLETE"}, {}, "statut INCOMPLETE"),
        ({}, {"hype_reaction": "buy_a_lot"}, "FOMO"),
        ({}, {"news_frequency": "daily", "hype_reaction": "buy_some"}, "attention"),
        ({}, {"drop_reaction": "sell_all"}, "sang-froid"),
        ({}, {"past_drop_behavior": "sold"}, "sang-froid"),
        ({"C": 60.0}, {}, "capacité lie"),
        ({"level": "N3", "level_from_R": "N4"}, {}, "capacité lie"),
    ],
)
def test_upward_shift_blocked(comp_kw, inputs_kw, reason):
    d = derive_style(make_comp(**comp_kw), StyleInputs(explicit_preference="offensive", **inputs_kw))
    assert d.shift == 0 and d.style == d.from_level
    assert any(reason in r for r in d.refused), d.refused


def test_contradiction_low_tolerance_growth_goal():
    comp = make_comp(level="N1", level_from_R="N1", R=20, T=20, C=90, e_min=0.10, e_cap=0.25)
    d = derive_style(comp, StyleInputs(goal="growth"))
    assert d.style == "defensive" and d.shift == 0
    assert any("tolérance faible" in c for c in d.contradictions)


def test_contradiction_short_horizon():
    d = derive_style(make_comp(horizon=2.0), StyleInputs(explicit_preference="offensive"))
    assert d.shift == 0 and any("horizon" in c for c in d.contradictions)


def test_beginner_capped_at_dynamique_and_no_single_stock():
    comp = make_comp(level="N5", level_from_R="N5", R=80, T=80, C=95, e_min=0.8, e_cap=1.0)
    d = derive_style(comp, StyleInputs(knowledge_level="beginner"))
    assert d.style == "dynamique" and d.k == 0
    assert d.flags.low_literacy


def test_knowledge_low_and_aggressive_tolerance_caps_pi():
    d = derive_style(make_comp(), StyleInputs(products_known=("etf", "bonds")))
    assert d.flags.low_literacy and d.pi <= CFG.band.low_composure_pi_max
    assert any("tolérance agressive" in c for c in d.contradictions)


def test_band_position_tolerance_places_capacity_caps():
    a = derive_style(amira())
    assert a.pi == pytest.approx((71.5 - 60) / 15) and not a.capacity_binds
    capped = derive_style(make_comp(C=65.0))  # C < T : la capacité lie → π = 1 (e_cap)
    assert capped.pi == 1.0 and capped.capacity_binds


def test_band_position_low_composure_and_incomplete():
    assert derive_style(robert()).pi == CFG.band.low_composure_pi_max
    assert derive_style(make_comp(status="INCOMPLETE")).pi == 0.0


def test_band_target_values():
    assert band_target(make_comp(crypto=0.0), 0.5) == pytest.approx(0.70)
    assert band_target(amira(), derive_style(amira()).pi) == pytest.approx(0.75)
    assert band_target(mateo(), derive_style(mateo()).pi) is None  # bas de bande : aucun plancher
    assert band_target(make_comp(crypto=0.02), 1.0) == pytest.approx(0.78)  # hors crypto


def test_k_rule():
    flags = behavior_flags(StyleInputs())
    assert k_rule(amira(), "dynamique", StyleInputs(), flags)[0] == 2
    assert k_rule(amira(), "dynamique", StyleInputs(approach="individual_securities"), flags)[0] == 2  # ⌊0.14/0.05⌋
    big = make_comp(level="N5", level_from_R="N5", R=80, T=80, e_min=0.8, e_cap=1.0, total=0.1675)
    assert k_rule(big, "offensive", StyleInputs(approach="individual_securities"), flags)[0] == 3
    assert k_rule(amira(), "dynamique", StyleInputs(approach="passive_funds"), flags)[0] == 0
    assert k_rule(robert(), "defensive", StyleInputs(), flags)[0] == 0
    over = behavior_flags(StyleInputs(self_assessment="advanced", quiz={"quiz_bond_rates": "rises"}))
    assert over.overconfidence and k_rule(amira(), "dynamique", StyleInputs(), over)[0] == 1


def test_overconfidence_halves_floor_fraction():
    d = derive_style(amira(), StyleInputs(self_assessment="advanced", quiz={"quiz_diversification": "etf"}))
    assert d.flags.overconfidence and d.floor_fraction == pytest.approx(CFG.floors.phi["dynamique"] / 2)


def test_trace_rows_cite_strategy_yaml():
    d = derive_style(amira(), StyleInputs(goal="growth"))
    assert {r["rule"] for r in d.trace} >= {
        "strategy.style_from_level",
        "strategy.style",
        "strategy.band_position",
        "strategy.k",
    }
    assert all(r["yaml_path"].startswith("strategy.yaml@0.1.0#") for r in d.trace)
