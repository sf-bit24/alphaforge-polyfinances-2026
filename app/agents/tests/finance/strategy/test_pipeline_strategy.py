"""Étape 0 dans le pipeline complet (mode rules) : décision valide, vérifiée, déterministe (sauté sans données)."""

from __future__ import annotations

import pytest

from alphaforge.finance.contracts import Limit, Selector
from alphaforge.finance.debate.merge import apply_amendments
from alphaforge.finance.debate.pipeline import Request, build_portfolio
from alphaforge.finance.debate.schemas import Amendment, LensReport
from alphaforge.finance.observability.verify import verify_decision
from alphaforge.finance.policy import compile_profile
from alphaforge.finance.portfolio.judge import _supersession, check
from alphaforge.finance.portfolio.optimizer import optimize
from alphaforge.finance.strategy import Plan, StyleInputs, apply_to_policy

from ..policy import _personas as P


@pytest.fixture(scope="module")
def amira():
    return build_portfolio(P.amira(), P.AS_OF, strategy=True, style_inputs=StyleInputs(amount_cad=100_000))


def test_strategy_false_keeps_master_behaviour():
    off = build_portfolio(P.mateo(), P.AS_OF, strategy=False)
    assert off.strategy is None
    assert not any(f.fact_id.startswith("strat.") for f in off.decision.facts)


def test_amira_decision_is_valid_and_every_number_verified(amira):
    d = amira.decision
    assert d.kind == "proposition" and amira.strategy.applied
    chk = verify_decision(d)
    bad = [s for s in chk.statements if not s["ok"]]
    assert not bad, bad
    sats = {p.asset_id for p in d.positions if p.role == "satellite"}
    assert set(amira.strategy.shortlist) <= sats
    eq = sum(p.weight for p in d.positions if p.asset_id in ("SPY", "XIU.TO", "QQQ", "ESGV") or p.asset_id in sats)
    assert eq >= amira.strategy.plan.growth_floor - 1e-6


def test_style_counterfactuals_cite_existing_facts(amira):
    d = amira.decision
    ids = {f.fact_id for f in d.facts}
    cfs = [c for c in d.counterfactuals if c.change_fr.startswith("Si le style était")]
    assert cfs and all(set(c.result_fact_ids) <= ids for c in cfs)


def test_positions_cite_rank_and_floor(amira):
    pos = {p.asset_id: p for p in amira.decision.positions}
    for t in amira.strategy.shortlist:
        assert {f"strat.rank.{t}", f"strat.floor.{t}"} <= set(pos[t].rationale_fact_ids)


def test_strategy_is_on_by_default_on_this_branch():
    assert build_portfolio(P.mateo(), P.AS_OF).strategy is not None


def test_deterministic_three_runs():
    runs = [build_portfolio(P.mateo(), P.AS_OF, strategy=True).decision for _ in range(3)]
    sig = [[(p.asset_id, round(p.weight, 8)) for p in r.positions] for r in runs]
    assert sig[0] == sig[1] == sig[2]


def test_request_keeps_its_ticker_and_robert_gets_no_single_stock():
    r = build_portfolio(P.robert(), P.AS_OF, strategy=True, request=Request("TSLA", amount_cad=50_000))
    assert r.decision.kind == "refus_encadre"
    assert "TSLA" not in r.strategy.policy.excluded
    assert r.strategy.shortlist == []


def test_judge_ignores_non_blocking_strat_limit_in_supersession():
    """Condition du volet traçabilité : une limite strat.* non bloquante plus basse qu'exp.tech ne la remplace
    ni ne la masque ; le verdict reste celui des limites bloquantes ; le fait strat.* reste dans les Facts."""
    comp = compile_profile(P.amira(), P.AS_OF)
    pol = apply_to_policy(comp.policy, Plan(None, {}, {"tech": (0.01, "test")}, {}))
    sup = _supersession(pol)
    assert "exp.tech" not in sup and "strat.sector_cap.tech" not in sup
    w = optimize(comp.policy, P.AS_OF).weights  # poids SANS le plafond strat : il est violé
    rep = check(w, pol, P.AS_OF)
    strat_checks = [c for c in rep.checks if c.rule_id.startswith("strat.sector_cap.tech")]
    assert strat_checks and strat_checks[0].violated
    assert not any(v.startswith("strat.") for v in rep.blocking_violations)
    assert rep.verdict == check(w, comp.policy, P.AS_OF).verdict
    assert any("strat.sector_cap.tech" in f.fact_id for f in rep.facts)


def test_lens_cap_below_style_floor_lowers_the_floor():
    comp = compile_profile(P.amira(), P.AS_OF)
    pol = apply_to_policy(comp.policy, Plan(0.75, {}, {}, {}))
    lvl = next(f for f in ("level",) if f)
    rep = LensReport(
        lens="timeline",
        amendments=[
            Amendment(kind="cap_group", target="alloc.growth", value=0.70, reason_fr="test", evidence_fact_ids=[lvl])
        ],
    )
    new, log = apply_amendments(
        pol, [rep], {"timeline": 1.0}, {lvl}, feasible=lambda p: optimize(p, P.AS_OF).status == "optimal"
    )
    assert log[0].status == "applique"
    floor = next(x for x in new.limits if x.rule_id == "strat.growth_floor")
    assert floor.min == pytest.approx(0.70 - 0.02)


def test_lens_cannot_raise_a_style_floor():
    comp = compile_profile(P.amira(), P.AS_OF)
    pol = apply_to_policy(comp.policy, Plan(0.70, {}, {}, {}))
    rep = LensReport(
        lens="risk",
        amendments=[
            Amendment(
                kind="require_min_group",
                target="strat.growth_floor",
                value=0.78,
                reason_fr="x",
                evidence_fact_ids=["level"],
            )
        ],
    )
    _, log = apply_amendments(pol, [rep], {"risk": 1.0}, {"level"})
    assert log[0].status == "rejete" and "strat" in log[0].why_fr


def test_limit_and_selector_import_sanity():
    assert Limit(rule_id="x", kind="exposure", selector=Selector(exposure_tag="tech"), max=0.1, derived_from="t")


def test_gold_profile_keeps_gld_in_a_verified_decision():
    res = build_portfolio(
        P.amira(), P.AS_OF, strategy=True, style_inputs=StyleInputs(interests=("gold",), amount_cad=100_000)
    )
    strat = res.strategy
    assert strat.plan.interest_floors.get("GLD") == "gold" or any("GLD" in f for f in strat.fallback)
    if strat.applied and "GLD" in strat.plan.floors:
        w = {p.asset_id: p.weight for p in res.decision.positions}
        assert w.get("GLD", 0.0) >= strat.plan.floors["GLD"] - 1e-6
        assert "GLD" not in strat.shortlist  # un FNB n'est pas un titre retenu par le classement
    bad = [s for s in verify_decision(res.decision).statements if not s["ok"]]
    assert not bad, bad
