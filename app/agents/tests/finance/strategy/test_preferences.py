"""Préférences du profil dans l'étape 0 : intérêt « or » (GLD) et titres préférés (preferences.favored_tickers)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from alphaforge import starter
from alphaforge.finance.policy.from_profile_view import style_inputs_from_view
from alphaforge.finance.strategy import Plan, StyleInputs, apply_to_policy, derive_style, load_strategy
from alphaforge.finance.strategy.rules import (
    clamp_strategy_floors,
    interest_asset_floors,
    rank_scores,
    sector_caps,
    shortlist,
    stock_floors,
)
from alphaforge.profile.questionnaire import InvalidValueError, default_questionnaire

from ._helpers import amira, lim, robert
from .test_rules import CANDS

CFG = load_strategy()


def with_gold(comp, gold_max=0.10):
    """Mandat de test avec GLD dans l'univers et la limite alloc.gold du niveau."""
    pol = comp.policy
    data = pol.model_dump()
    data["universe"] = [*pol.universe, "GLD"]
    gold = lim("alloc.gold", "group_weight", {"classes": ["commodity"]}, None, gold_max)
    data["limits"] = [*data["limits"], gold.model_dump()]
    new = type(pol).model_validate(data)
    return replace(comp, policy=new, limits=[*comp.limits, gold])


# --------------------------------------------------------------------------- or → GLD


def test_gold_interest_gives_a_bounded_floor_on_gld():
    comp = with_gold(amira())
    d = derive_style(comp)
    floors, owner, notes = interest_asset_floors(comp.policy, comp, d, StyleInputs(interests=("gold",)))
    assert owner == {"GLD": "gold"} and not notes
    f = floors["GLD"]
    assert CFG.floors.min_floor <= f <= min(CFG.floors.f_abs, 0.10)


def test_gold_interest_needs_the_interest_the_asset_and_room():
    comp = with_gold(amira())
    d = derive_style(comp)
    assert interest_asset_floors(comp.policy, comp, d, StyleInputs())[0] == {}
    no_gld = amira()
    floors, _, notes = interest_asset_floors(no_gld.policy, no_gld, d, StyleInputs(interests=("gold",)))
    assert floors == {} and "hors de l'univers" in notes[0]
    closed = with_gold(amira(), gold_max=0.0)  # niveau qui n'admet pas l'or : rien, jamais au-delà du plafond
    floors, _, notes = interest_asset_floors(closed.policy, closed, d, StyleInputs(interests=("gold",)))
    assert floors == {} and notes
    small = interest_asset_floors(comp.policy, comp, d, StyleInputs(interests=("gold",), amount_cad=5_000))
    assert small[0] == {}  # ligne sous le minimum en dollars


def test_gold_floor_limit_is_non_blocking_and_clamped_by_alloc_gold():
    comp = with_gold(amira())
    plan = Plan(None, {"GLD": 0.03}, {}, {}, interest_floors={"GLD": "gold"})
    pol = apply_to_policy(comp.policy, plan)
    gld = next(x for x in pol.limits if x.rule_id == "strat.floor.GLD")
    assert not gld.blocking and gld.min == pytest.approx(0.03) and "gold" in (gld.source or "")
    data = pol.model_dump()
    for x in data["limits"]:
        if x["rule_id"] == "alloc.gold":
            x["max"] = 0.02  # une lentille resserre l'or
        if x["rule_id"] == "conc.single_total":
            x["max"] = 0.01  # n'a rien à voir avec un FNB
    out, notes = clamp_strategy_floors(type(pol).model_validate(data))
    got = {x.rule_id: x.min for x in out.limits if x.rule_id.startswith("strat.floor.")}
    assert got["strat.floor.GLD"] == pytest.approx(0.02) and notes


# --------------------------------------------------------------------------- titres préférés


def test_favored_ticker_gets_one_bonus_and_nothing_else():
    base = {x.ticker: x for x in rank_scores(CANDS, "dynamique", StyleInputs(), {})}
    fav = {x.ticker: x for x in rank_scores(CANDS, "dynamique", StyleInputs(favored_tickers=("TSLA", "ZZZ")), {})}
    assert "favored:TSLA" in fav["TSLA"].bonuses
    assert fav["TSLA"].score == pytest.approx(base["TSLA"].score + CFG.bonus.size)
    assert all(fav[t].score == base[t].score for t in base if t != "TSLA")
    assert fav["TSLA"].eligible == base["TSLA"].eligible and fav["TSLA"].reasons == base["TSLA"].reasons


def test_favored_ticker_never_bypasses_eligibility():
    inp = StyleInputs(favored_tickers=("NVDA",))  # baisse longue de 87 % > δ des titres individuels
    r = {x.ticker: x for x in rank_scores(CANDS, "offensive", inp, {"CNQ.TO": "exclu"})}
    assert not r["NVDA"].eligible
    inp_cnq = StyleInputs(favored_tickers=("CNQ.TO",))
    excl = {x.ticker: x for x in rank_scores(CANDS, "dynamique", inp_cnq, {"CNQ.TO": "x"})}
    assert not excl["CNQ.TO"].eligible
    assert "NVDA" not in [x.ticker for x in shortlist(list(r.values()), 3)]


def test_favored_tickers_never_change_a_risk_limit_nor_impose_a_weight():
    comp = amira()
    d = derive_style(comp)
    plain = shortlist(rank_scores(CANDS, "dynamique", StyleInputs(), {}), 2)
    fav_in = StyleInputs(favored_tickers=("TSLA",))
    fav = shortlist(rank_scores(CANDS, "dynamique", fav_in, {}), 2)
    f_plain, _ = stock_floors(plain, comp, d, StyleInputs())
    f_fav, _ = stock_floors(fav, comp, d, fav_in)
    assert set(f_fav.values()) == set(f_plain.values())  # même plancher de satellite, aucun poids propre
    caps = sector_caps(comp, "dynamique", fav_in, set())
    assert caps == sector_caps(comp, "dynamique", StyleInputs(), set())
    pol = apply_to_policy(comp.policy, Plan(None, f_fav, caps, {}))
    base = {x.rule_id: x.model_dump() for x in comp.policy.limits}
    assert all({x.rule_id: x.model_dump() for x in pol.limits}[k] == v for k, v in base.items())


def test_robert_index_funds_only_ignores_favored_tickers():
    comp = robert()
    d = derive_style(comp, StyleInputs(approach="passive_funds", favored_tickers=("AAPL",)))
    assert d.k == 0


# --------------------------------------------------------------------------- questionnaire et profil


def test_questionnaire_favored_tickers_is_a_closed_list_of_universe_stocks():
    q = default_questionnaire()
    spec = q.fields["preferences.favored_tickers"]
    stocks = {t for t, a in starter.universe().items() if a.asset_class == "equity"}
    values = set(spec.value_ids)
    assert values == stocks | {"none"} and spec.weight == 0
    question = next(x for x in q.questions if x.field.id == "preferences.favored_tickers")
    assert set(q.validate_answer(question, ["AAPL", "RY.TO"])) == {"AAPL", "RY.TO"}
    with pytest.raises(InvalidValueError):
        q.validate_answer(question, ["ZZZ"])  # hors univers
    with pytest.raises(InvalidValueError):
        q.validate_answer(question, ["AAPL", "none"])


def test_profile_view_passes_favored_tickers_to_step_0():
    view = {"facts": [{"field": "preferences.favored_tickers", "value": ["AAPL", "none"]}]}
    assert style_inputs_from_view(view).favored_tickers == ("AAPL",)
