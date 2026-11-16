"""Issue #78 : les libellés français du moteur traduisent les codes internes (offensive, technology, energy,
timeline, low_composure, refuse…) et gardent les identifiants (risk.cdar_m, risk_levels.yaml#…) hors du libellé.

Tests purs (sans données longues ni optimiseur), sauf le résumé du Judge, sauté sans numpy."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from alphaforge.finance.contracts import PolicySpec
from alphaforge.finance.debate.explain import skeleton, strategy_statements
from alphaforge.finance.debate.facts import FactBook
from alphaforge.finance.debate.schemas import LENS_FR, LENSES, Amendment, AppliedAmendment
from alphaforge.finance.policy import compile_profile
from alphaforge.finance.strategy import Plan, StyleInputs, behavior_flags, build_limits, derive_style, load_strategy
from alphaforge.finance.strategy.labels import evidence_text, flag_fr
from alphaforge.finance.strategy.rules import Candidate, eligibility, sector_caps

from .finance.policy import _personas as P
from .finance.strategy._helpers import make_comp

CFG = load_strategy()
NBSP = "\u00a0"
RAW = re.compile(r"(?<![\w.])(offensive|defensive|technology|energy|refuse|timeline|low_composure)(?![\w])")


def _candidate(**kw) -> Candidate:
    base = {"ticker": "AMZN", "sector": "Consumer Discretionary", "tags": (), "currency": "USD", "features": {}}
    return Candidate(**{**base, **kw})


def test_long_drawdown_reason_writes_percent_with_a_non_breaking_space():
    ok, why = eligibility(_candidate(features={"mdd_long": 0.93}), {}, StyleInputs(), CFG)
    assert not ok
    assert f"baisse maximale longue 93{NBSP}% > 80{NBSP}% (δ des titres individuels)" in why
    assert not any(re.search(r"\d%", w) for w in why)


def test_employment_sector_and_value_exclusion_reasons_are_in_french():
    tech = _candidate(ticker="AAPL", sector="Information Technology", tags=("tech",), features={"mdd_long": 0.5})
    _, why = eligibility(tech, {}, StyleInputs(employment_sector="technology"), CFG)
    assert "secteur d'emploi (technologie) : capital humain déjà exposé" in why
    oil = _candidate(ticker="CNQ.TO", sector="Energy", tags=("fossil_fuel",), features={"mdd_long": 0.5})
    _, why = eligibility(oil, {}, StyleInputs(exclusions=("fossil_fuels",), exclusion_strictness="absolute"), CFG)
    assert "exclusion de valeurs : combustibles fossiles" in why
    assert not any(RAW.search(w) for w in why)


def test_sector_caps_and_interest_floors_name_the_sector_and_interest_in_french():
    caps = sector_caps(make_comp(), "defensive", StyleInputs(), set(), CFG)
    assert caps and all("style défensif" in why for _, why in caps.values())
    plan = Plan(None, {"GLD": 0.02}, {"energy": (0.02, caps["energy"][1])}, {}, interest_floors={"GLD": "gold"})
    lims = {lim.rule_id: lim for lim in build_limits(plan, CFG)}
    cap = lims["strat.sector_cap.energy"]
    assert cap.description_fr == "plafond d'exposition au secteur de l'énergie (look-through)"
    assert cap.derived_from == "étape 0 : style défensif (τ = -0,25)"
    floor = lims["strat.floor.GLD"]
    assert floor.description_fr == "plancher de GLD (intérêt or)"
    assert floor.derived_from == "étape 0 : intérêt « or » de l'investisseur"
    for lim in lims.values():
        assert not RAW.search(lim.description_fr) and not RAW.search(lim.derived_from)


def test_style_contradiction_names_the_style_in_french():
    d = derive_style(make_comp(horizon=2.0), StyleInputs(explicit_preference="offensive"))
    assert "horizon court × préférence pour le style offensif" in d.contradictions
    assert not any(RAW.search(t) for t in (*d.contradictions, *d.refused))


def test_behavior_signal_is_readable_and_keeps_its_evidence_ids_out_of_the_text():
    flags = behavior_flags(StyleInputs(drop_reaction="sell_all"), comp=make_comp(cdar=True))
    raw = flags.evidence["low_composure"]
    assert any(item.startswith("risk.cdar_m") for item in raw)  # l'identifiant reste dans la preuve (traitement)
    text = evidence_text(raw)
    assert "réaction à une forte baisse : tout vendre" in text
    assert "limite de baisse conditionnelle du mandat" in text
    assert "risk.cdar_m" not in text and "risk_levels.yaml" not in text and "=" not in text
    assert flag_fr("low_composure") == "faible sang-froid face aux baisses"
    fomo = behavior_flags(StyleInputs(hype_reaction="buy_a_lot"))  # part dans un titre médiatisé : sans réponse
    assert evidence_text(fomo.evidence["fomo"]) == "réaction à un titre très médiatisé : en acheter beaucoup"


def test_limit_descriptions_of_the_mandate_hide_the_rule_id():
    comp = compile_profile(P.robert(), P.AS_OF)
    template = [lim for lim in comp.policy.limits if lim.description_fr and lim.description_fr.endswith(" N0")]
    assert {"risk.cdar_m", "risk.cvar_m", "alloc.growth"} <= {lim.rule_id for lim in template}
    for lim in template:
        assert lim.rule_id not in lim.description_fr, lim.description_fr
        assert lim.description_fr.endswith(", niveau N0")
    by_id = {lim.rule_id: lim.description_fr for lim in template}
    assert by_id["risk.cdar_m"] == "CDaR mensuelle (risque mesuré par les baisses), niveau N0"


def test_lenses_have_french_names_in_the_explanation():
    assert set(LENS_FR) == set(LENSES)
    assert LENS_FR == {
        "timeline": "horizon",
        "risk": "risque",
        "diversity": "diversité et préférences",
        "constraints": "contraintes",
    }
    book = FactBook("dec-test")
    with book.step("test"):
        book.add("level", "Niveau de risque effectif", "N2", "niveau", dataset="test")
    amendment = Amendment(kind="cap_group", target="alloc.growth", value=0.3, reason_fr="moins d'actions",
                          evidence_fact_ids=["level"])
    applied = [AppliedAmendment(lens="timeline", amendment=amendment, status="applique", why_fr="appliqué")]
    expl = skeleton(book, kind="proposition", level_fid="level", cand="r2", active_fids=[], applied=applied,
                    counterfactual_stmts=[])
    assert "La lentille « horizon » a resserré le mandat : moins d'actions." in [s.text_fr for s in expl.why]


def test_strategy_statements_translate_the_sector_and_the_signal():
    book = FactBook("dec-test")
    with book.step("test"):
        book.add("strat.style", "style de composition retenu (étape 0)", "défensif", "texte", dataset="test")
        book.add("strat.sector_cap.energy", "plafond", 0.0225, "%", dataset="test")
        book.add("strat.flag.low_composure", "signal", "aversion", "texte", dataset="test")
    out = strategy_statements(book)
    texts = [s.text_fr for sec in out.values() for s in sec]
    assert "Plafond d'exposition au secteur de l'énergie (look-through) : 2,2 %." in texts
    assert any(t.startswith("Signal de comportement « faible sang-froid face aux baisses »") for t in texts)
    assert "Style de composition retenu : défensif." in texts[0]
    assert not any(RAW.search(t) for t in texts)


def test_judge_summary_says_refused_and_agrees_the_plural():
    pytest.importorskip("numpy")
    from alphaforge.finance.portfolio.judge import _Ledger

    policy = PolicySpec(policy_id="p", profile_id="t", profile_version=1, created_utc=datetime(2026, 9, 30, tzinfo=UTC),
                        universe=["SPY", "AGG"], limits=[])
    window = SimpleNamespace(as_of=datetime(2026, 9, 30), data_version="v")

    def summary(blocking):
        ledger = _Ledger("judge-test", window)
        ledger.blocking = list(blocking)
        return ledger.trace_event(policy, {}, datetime.now(UTC)).output_summary

    assert summary(["a", "b", "c", "d"]) == "refusée ; 4 violations bloquantes"
    assert summary(["a"]) == "refusée ; 1 violation bloquante"
    assert summary([]) == "approuvée ; aucune violation bloquante"
