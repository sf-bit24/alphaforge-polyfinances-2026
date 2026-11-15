"""Étape 0 sur les données du moteur : sélection, invariants, faisabilité, repli (sauté sans données longues)."""

from __future__ import annotations

import json

import pytest

from alphaforge.finance.debate.facts import FactBook
from alphaforge.finance.policy import compile_profile
from alphaforge.finance.portfolio.optimizer import optimize
from alphaforge.finance.strategy import StyleInputs
from alphaforge.finance.strategy import select as sel
from alphaforge.finance.strategy.scoring import compute_candidates

from ..policy import _personas as P


def _run(name, inputs=None, **kw):
    prof = getattr(P, name)()
    comp = compile_profile(prof, P.AS_OF)
    book = FactBook(f"dec-test-{name}")
    return comp, book, sel.apply_strategy(comp, prof, P.AS_OF, book, inputs=inputs or StyleInputs(), **kw)


@pytest.fixture(scope="module")
def amira():
    return _run("amira")


@pytest.fixture(scope="module")
def mateo():
    return _run("mateo")


@pytest.fixture(scope="module")
def robert():
    return _run("robert")


def test_candidates_are_deterministic():
    comp = compile_profile(P.amira(), P.AS_OF)
    a = compute_candidates(comp.policy, P.AS_OF)
    b = compute_candidates(comp.policy, P.AS_OF)
    dump = lambda cs: json.dumps([(c.ticker, c.features) for c in cs], sort_keys=True, default=str)  # noqa: E731
    assert dump(a) == dump(b) and len(a) == 20


def test_amira_dynamique_band_floor_and_two_sectors(amira):
    _, _, res = amira
    assert res.decision.style == "dynamique" and res.applied and not res.fallback
    assert res.plan.growth_floor == pytest.approx(0.75)
    assert len(res.shortlist) == 2
    sectors = {r.sector for r in res.ranking if r.ticker in res.shortlist}
    assert len(sectors) == 2


def test_mateo_defensive_sector_caps(mateo):
    _, _, res = mateo
    assert res.decision.style == "defensive"
    assert res.plan.sector_caps["tech"][0] == pytest.approx(0.145)
    assert res.plan.growth_floor is None  # la tolérance place Mateo en bas de bande


def test_robert_no_single_stock(robert):
    _, _, res = robert
    assert res.decision.k == 0 and res.shortlist == []
    singles = [c.ticker for c in res.candidates]
    assert all(t in res.policy.excluded for t in singles)


@pytest.mark.parametrize("fixture_name", ["amira", "mateo", "robert"])
def test_invariants_base_limits_untouched(request, fixture_name):
    comp, _, res = request.getfixturevalue(fixture_name)
    base = {x.rule_id: x.model_dump() for x in comp.policy.limits}
    new = {x.rule_id: x.model_dump() for x in res.policy.limits}
    assert all(new[k] == v for k, v in base.items())
    assert all(k.startswith("strat.") and not new[k]["blocking"] for k in set(new) - set(base))
    assert set(res.policy.excluded) >= set(comp.policy.excluded)


def test_optimizer_window_unchanged(amira):
    comp, _, res = amira
    assert optimize(comp.policy, P.AS_OF).window == optimize(res.policy, P.AS_OF).window


def test_facts_cite_strategy_yaml(amira):
    _, book, res = amira
    strat = [f for f in book.facts.values() if f.fact_id.startswith("strat.")]
    assert len(strat) > 100
    assert all(f.sources[0].dataset.startswith(f"strategy.yaml@{res.version}#") for f in strat)
    assert "strat.rank.FTS.TO" in book.facts and "strat.sens.mom.rank.NVDA" in book.facts


def test_requested_ticker_is_never_excluded():
    _, _, res = _run("mateo", protect=["TSLA"])
    assert "TSLA" not in res.policy.excluded


def test_growth_preference_never_moves_the_band(amira):
    _, _, base = amira
    _, _, growth = _run("amira", StyleInputs(goal="growth"))
    assert growth.decision.style == "offensive" and growth.plan.growth_floor == base.plan.growth_floor


def test_human_capital_tech_worker():
    _, _, res = _run("amira", StyleInputs(employment_sector="technology"))
    tech = {"SHOP.TO", "CSU.TO", "AAPL", "MSFT", "NVDA", "GOOGL"}
    assert not (set(res.shortlist) & tech)
    assert res.plan.sector_caps["tech"][0] == pytest.approx(0.35)


def test_forced_fallback_is_traced(monkeypatch):
    real = sel.check

    def strict(weights, policy, as_of, **kw):
        rep = real(weights, policy, as_of, **kw)
        if any(lim.rule_id.startswith("strat.floor.") for lim in policy.limits):
            return type(rep)(**{**rep.__dict__, "blocking_violations": (*rep.blocking_violations, "simulée")})
        return rep

    monkeypatch.setattr(sel, "check", strict)
    _, book, res = _run("amira")
    assert res.fallback and res.fallback[0].startswith("planchers des titres divisés par 2")
    assert res.applied and res.plan.floors == {} and res.plan.growth_floor == pytest.approx(0.75)
    assert any(fid.startswith("strat.fallback.") for fid in book.facts)


def test_sector_deltas_match_the_long_history_fixture():
    import csv
    import math
    from pathlib import Path

    from alphaforge.finance.strategy import load_strategy

    fx = Path(__file__).parents[1] / "fixtures" / "calibration" / "tails_sectors.csv"
    mdd = {r["asset"]: float(r["mdd"]) for r in csv.DictReader(fx.open()) if r["cur"] == "CAD"}
    tags = load_strategy().sectors.tags
    for tag, ind in {
        "utilities": "US_IND_UTILS",
        "healthcare": "US_IND_HLTH",
        "energy": "US_IND_ENRGY",
        "financials": "US_IND_MONEY",
    }.items():
        assert tags[tag].delta == pytest.approx(math.ceil(mdd[ind] / 0.05 - 1e-9) * 0.05)
