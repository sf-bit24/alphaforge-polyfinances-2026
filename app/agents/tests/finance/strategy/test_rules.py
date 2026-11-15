"""Étape 0, partie pure : classement, sélection, plafonds sectoriels, planchers, limites strat.* (sûr en CI)."""

from __future__ import annotations

import re

import pytest

from alphaforge.finance.strategy import Plan, StyleInputs, apply_to_policy, derive_style, load_strategy
from alphaforge.finance.strategy.config import DEFAULT_PATH
from alphaforge.finance.strategy.rules import (
    Candidate,
    clamp_strategy_floors,
    degrade_steps,
    rank_scores,
    sector_caps,
    shortlist,
    stock_floors,
)

from ._helpers import amira, lim, make_comp, mateo, robert

CFG = load_strategy()


def cand(t, sector, tags, ccy="CAD", **f):
    base = {"vol": 0.2, "beta": 1.0, "corr_core": 0.5, "dividend_yield": 0.02, "mdd_long": 0.5, "liquidity_cad": 1e9}
    base.update(f)
    return Candidate(t, sector, tuple(tags), ccy, base)


CANDS = [
    cand(
        "FTS.TO",
        "Utilities",
        ["utilities", "defensive_sector", "canada"],
        vol=0.15,
        beta=0.1,
        dividend_yield=0.035,
        mdd_long=0.45,
        corr_core=0.2,
    ),
    cand(
        "JNJ",
        "Health Care",
        ["healthcare", "defensive_sector"],
        "USD",
        vol=0.17,
        beta=0.0,
        dividend_yield=0.02,
        mdd_long=0.55,
        corr_core=0.05,
    ),
    cand(
        "RY.TO",
        "Financials",
        ["financials", "canada"],
        vol=0.2,
        beta=0.9,
        dividend_yield=0.04,
        mdd_long=0.6,
        corr_core=0.6,
    ),
    cand(
        "TD.TO",
        "Financials",
        ["financials", "canada"],
        vol=0.19,
        beta=0.8,
        dividend_yield=0.045,
        mdd_long=0.62,
        corr_core=0.55,
    ),
    cand(
        "NVDA",
        "Information Technology",
        ["tech"],
        "USD",
        vol=0.5,
        beta=1.9,
        dividend_yield=0.002,
        mdd_long=0.87,
        corr_core=0.6,
    ),
    cand(
        "AAPL",
        "Information Technology",
        ["tech"],
        "USD",
        vol=0.27,
        beta=1.1,
        dividend_yield=0.003,
        mdd_long=0.75,
        corr_core=0.57,
    ),
    cand(
        "CNQ.TO",
        "Energy",
        ["energy", "fossil_fuel", "canada"],
        vol=0.32,
        beta=0.6,
        dividend_yield=0.037,
        mdd_long=0.7,
        corr_core=0.36,
    ),
    cand(
        "TSLA",
        "Consumer Discretionary",
        ["consumer_discretionary"],
        "USD",
        vol=0.6,
        beta=2.0,
        dividend_yield=0.0,
        mdd_long=0.74,
        corr_core=0.5,
    ),
]


def test_rank_is_deterministic_with_ticker_tiebreak():
    a = rank_scores(CANDS, "defensive", StyleInputs(), {})
    b = rank_scores(list(reversed(CANDS)), "defensive", StyleInputs(), {})
    assert [r.ticker for r in a] == [r.ticker for r in b]
    tie = [cand("BBB", "X", []), cand("AAA", "Y", [])]
    assert [r.ticker for r in rank_scores(tie, "dynamique", StyleInputs(), {})] == ["AAA", "BBB"]


def test_zero_dividend_and_missing_get_minimum_utility():
    r = {x.ticker: x for x in rank_scores(CANDS, "defensive", StyleInputs(), {})}
    assert r["TSLA"].utility["dividend_yield"] == 0.0
    miss = rank_scores([cand("A", "S1", [], vol=None), cand("B", "S2", [])], "defensive", StyleInputs(), {})
    assert {x.ticker: x.utility["vol"] for x in miss}["A"] == 0.0


def test_defensive_prefers_defensive_sectors_and_one_per_sector():
    ranked = rank_scores(CANDS, "defensive", StyleInputs(), {})
    top = shortlist(ranked, 3)
    assert [r.ticker for r in top][:2] == ["FTS.TO", "JNJ"]
    assert len({r.sector for r in top}) == len(top)


def test_offensive_does_not_pick_past_tail_winners():
    ranked = {r.ticker: r for r in rank_scores(CANDS, "offensive", StyleInputs(), {})}
    assert not ranked["NVDA"].eligible  # baisse maximale longue 87 % > δ 80 %
    assert any("baisse maximale longue" in w for w in ranked["NVDA"].reasons)


def test_eligibility_rules():
    ex = {"RY.TO": "profile.legal_constraints[test]"}
    inputs = StyleInputs(
        employment_sector="technology",
        currency_preference="cad_only",
        exclusions=("fossil_fuels",),
        exclusion_strictness="absolute",
    )
    r = {x.ticker: x for x in rank_scores(CANDS, "dynamique", inputs, ex, employer_tickers={"TD.TO"})}
    assert not r["RY.TO"].eligible and not r["TD.TO"].eligible
    assert not r["AAPL"].eligible and any("secteur d'emploi" in w for w in r["AAPL"].reasons)
    assert not r["JNJ"].eligible and any("CAD seulement" in w for w in r["JNJ"].reasons)
    assert not r["CNQ.TO"].eligible and any("exclusion de valeurs" in w for w in r["CNQ.TO"].reasons)
    assert r["FTS.TO"].eligible


def test_preference_exclusion_penalises_without_excluding():
    inputs = StyleInputs(exclusions=("fossil_fuels",), exclusion_strictness="preference")
    base = {x.ticker: x.score for x in rank_scores(CANDS, "dynamique", StyleInputs(), {})}
    pen = {x.ticker: x for x in rank_scores(CANDS, "dynamique", inputs, {})}
    assert pen["CNQ.TO"].eligible and pen["CNQ.TO"].score == pytest.approx(
        base["CNQ.TO"] + CFG.bonus.preference_penalty
    )


def test_interest_bonus_and_employment_tag_never_rewarded():
    inp = StyleInputs(interests=("technology",), employment_sector="technology")
    r = {x.ticker: x for x in rank_scores(CANDS, "offensive", inp, {})}
    assert "interest:technology" not in r["AAPL"].bonuses and "style:tech" not in r["AAPL"].bonuses


def test_sector_caps_defensive_mateo_and_robert():
    caps = sector_caps(mateo(), "defensive", StyleInputs(), set())
    assert caps["tech"][0] == pytest.approx(0.145) and caps["energy"][0] == pytest.approx(0.0475)
    rob = sector_caps(robert(), "defensive", StyleInputs(), set())
    assert rob["tech"][0] == pytest.approx(0.0475)


def test_sector_cap_with_zero_tau_reproduces_exp_tech_and_is_not_emitted():
    caps = sector_caps(amira(), "dynamique", StyleInputs(), {"tech"})
    assert "tech" not in caps  # e_cap·s_ref + φ·l*/δ = 0,4075 = exp.tech : rien de plus strict


def test_human_capital_caps_tech_at_market_weight():
    caps = sector_caps(amira(), "dynamique", StyleInputs(employment_sector="technology"), set())
    assert caps["tech"][0] == pytest.approx(0.35) and "capital humain" in caps["tech"][1]


def test_stock_floors_respect_budgets_and_min_line():
    ranked = shortlist(rank_scores(CANDS, "dynamique", StyleInputs(), {}), 2)
    d = derive_style(amira())
    floors, _ = stock_floors(ranked, amira(), d, StyleInputs())
    assert set(floors.values()) == {0.025} and sum(floors.values()) <= 0.14
    fm, _ = stock_floors(ranked, mateo(), derive_style(mateo()), StyleInputs())
    assert set(fm.values()) == {0.015}
    small, notes = stock_floors(ranked, amira(), d, StyleInputs(amount_cad=10_000))
    assert small == {} and all("sous" in n for n in notes)


def _plan(comp):
    return Plan(
        growth_floor=0.75,
        floors={"FTS.TO": 0.025, "JNJ": 0.025},
        sector_caps={"tech": (0.35, "test")},
        exclusions={"NVDA": "strat.shortlist (fact strat.rank.NVDA)"},
    )


def test_apply_to_policy_invariants():
    comp = amira()
    base = comp.policy
    new = apply_to_policy(base, _plan(comp))
    base_ids = {x.rule_id: x.model_dump() for x in base.limits}
    new_ids = {x.rule_id: x.model_dump() for x in new.limits}
    assert all(new_ids[k] == v for k, v in base_ids.items())  # I1 : base intacte
    added = [new_ids[k] for k in set(new_ids) - set(base_ids)]
    assert added and all(a["rule_id"].startswith("strat.") and not a["blocking"] for a in added)  # I2
    assert set(new.excluded) >= set(base.excluded) and "NVDA" in new.excluded  # I3
    assert [x for x in new.limits if x.rule_id.startswith("risk.")] == [
        x for x in base.limits if x.rule_id.startswith("risk.")
    ]


def test_apply_to_policy_is_idempotent():
    comp = amira()
    once = apply_to_policy(comp.policy, _plan(comp))
    twice = apply_to_policy(once, _plan(comp))
    assert [x.rule_id for x in once.limits] == [x.rule_id for x in twice.limits]


def test_clamp_lowers_floors_when_prudence_tightens():
    comp = amira()
    pol = apply_to_policy(comp.policy, _plan(comp))
    data = pol.model_dump()
    for lim_ in data["limits"]:
        if lim_["rule_id"] == "alloc.growth":
            lim_["max"] = 0.70
        if lim_["rule_id"] == "conc.single_each":
            lim_["max"] = 0.02
    tightened = type(pol).model_validate(data)
    out, notes = clamp_strategy_floors(tightened)
    got = {x.rule_id: x.min for x in out.limits if x.rule_id.startswith("strat.")}
    assert got["strat.growth_floor"] == pytest.approx(0.68)  # alloc.growth.max − crypto
    assert got["strat.floor.FTS.TO"] == pytest.approx(0.02) and notes


def test_degrade_steps_order_never_drops_base_exclusions():
    labels = [lbl for lbl, _ in degrade_steps(_plan(amira()), e_min=0.6)]
    assert labels[0] == "planchers des titres divisés par 2"
    assert labels[-1] == "sélection abandonnée : mandat de base"
    assert any("plafonds sectoriels" in x for x in labels)


def test_wording_never_advises():
    text = DEFAULT_PATH.read_text(encoding="utf-8").lower()
    forbidden = r"achet|vendez|recommand|meilleur placement|garanti|surperform|gagnant"
    assert not re.search(forbidden, text), re.findall(forbidden, text)


def test_risk_budgets_identical_whatever_the_preferences():
    comp = amira()
    risk = [x.model_dump() for x in comp.limits if x.rule_id.startswith("risk.")]
    for pref in ("defensive", "dynamique", "offensive"):
        derive_style(comp, StyleInputs(explicit_preference=pref, interests=("dividends",), approach="mixed"))
        assert [x.model_dump() for x in comp.limits if x.rule_id.startswith("risk.")] == risk


def test_lim_helper_sanity():
    assert lim("x", "group_weight", {"classes": ["a"]}, 0.1, 0.2).max == 0.2
    assert make_comp().policy.universe
