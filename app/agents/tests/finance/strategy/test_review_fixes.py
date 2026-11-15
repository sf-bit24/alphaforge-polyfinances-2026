"""Régressions de la revue indépendante de l'étape 0 (données longues requises)."""

from __future__ import annotations

import pytest

from alphaforge.finance.debate import pipeline as pl
from alphaforge.finance.debate.facts import FactBook
from alphaforge.finance.debate.merge import apply_amendments
from alphaforge.finance.debate.pipeline import build_portfolio
from alphaforge.finance.debate.schemas import Amendment, LensReport
from alphaforge.finance.policy import compile_profile
from alphaforge.finance.portfolio.optimizer import optimize
from alphaforge.finance.strategy import StyleInputs
from alphaforge.finance.strategy import select as sel

from ..policy import _personas as P


def _feasible(p):
    return optimize(p, P.AS_OF).status == "optimal"


def test_lens_prudence_wins_over_style_floors():
    comp = compile_profile(P.amira(), P.AS_OF)
    res = sel.apply_strategy(comp, P.amira(), P.AS_OF, FactBook("d"), inputs=StyleInputs())
    rep = LensReport(lens="risk", amendments=[
        Amendment(kind="tighten_limit", target="risk.cvar_m", value=0.040, reason_fr="t", evidence_fact_ids=["level"])
    ])
    new, log = apply_amendments(res.policy, [rep], {"risk": 1.0}, {"level"}, feasible=_feasible)
    assert log[0].status == "applique" and "planchers du style" in log[0].why_fr
    assert not any(x.rule_id.startswith("strat.floor.") for x in new.limits)


def test_invalid_style_preference_never_crashes():
    r = build_portfolio(P.mateo(), P.AS_OF, style_preference="aggressive")
    assert r.strategy is not None and any("inconnue" in x for x in r.strategy.decision.refused)


def test_step0_error_falls_back_to_base(monkeypatch):
    import alphaforge.finance.strategy as st

    def boom(*a, **k):
        raise RuntimeError("panne simulée")

    monkeypatch.setattr(st, "apply_strategy", boom)
    r = build_portfolio(P.mateo(), P.AS_OF)
    assert r.strategy is None and "strat.error" in {f.fact_id for f in r.decision.facts}
    assert r.decision.kind in ("proposition", "refus_encadre")


def test_explanation_uses_final_values_after_clamp():
    comp = compile_profile(P.amira(), P.AS_OF)
    book = FactBook("d")
    res = sel.apply_strategy(comp, P.amira(), P.AS_OF, book, inputs=StyleInputs())
    data = res.policy.model_dump()
    for lim in data["limits"]:
        if lim["rule_id"] == "strat.growth_floor":
            lim["min"] = 0.68
    final = type(res.policy).model_validate(data)
    with book.step("t"):
        pass
    out = pl._final_strategy_facts(book, res, final)
    assert out["band_target"] == "strat.final.band_target" and book.facts["strat.final.band_target"].value == 0.68


def test_fallback_respects_min_line(monkeypatch):
    real = sel.check

    def strict(weights, policy, as_of, **kw):
        rep = real(weights, policy, as_of, **kw)
        if any(lim.rule_id.startswith("strat.floor.") and lim.min >= 0.02 for lim in policy.limits):
            return type(rep)(**{**rep.__dict__, "blocking_violations": (*rep.blocking_violations, "simulée")})
        return rep

    monkeypatch.setattr(sel, "check", strict)
    comp = compile_profile(P.amira(), P.AS_OF)
    res = sel.apply_strategy(comp, P.amira(), P.AS_OF, FactBook("d"), inputs=StyleInputs(amount_cad=30_000))
    assert all(f * 30_000 >= 500 for f in res.plan.floors.values())


def test_strategy_false_keeps_crypto_core_role():
    r = build_portfolio(P.amira(), P.AS_OF, strategy=False)
    assert all(p.role == "coeur" for p in r.decision.positions if p.asset_id in ("BTC-USD", "ETH-USD"))


@pytest.mark.parametrize("name", ["amira", "mateo"])
def test_risk_effect_is_explained(name):
    d = build_portfolio(getattr(P, name)(), P.AS_OF).decision
    why = " ".join(s.text_fr for s in d.explanation.why)
    assert "risque minimisé" in why and "mandat de base" in why
