"""Issue #76 : une décision sans allocation nomme sa cause et son levier réel, avec des Facts cités.

Cas du test e2e du 2026-11-15 : profil à 95 % (« Prêt »), 10 000 $, perte maximale de 250 $, fonds d'urgence nul,
retraits de 25 % sous 12 mois. La règle des dollars le met en PROTECTION (l* = 2,5 % sous min_L_plan) ; la décision
disait « informations manquantes ou signaux de vulnérabilité » et « Compléter : le profil. ».

L'explication se construit sans le moteur (numpy, cvxpy) ; seul le test de ``build_portfolio`` en a besoin.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import UTC, date, datetime

import pytest

from alphaforge.finance.contracts.profile import InvestorProfile
from alphaforge.finance.debate.explain import no_allocation_explanation, verify
from alphaforge.finance.debate.facts import FactBook, fmt
from alphaforge.finance.policy import compile_profile
from alphaforge.finance.policy.compiler import no_mandate_cause
from alphaforge.finance.policy.from_profile_view import investor_profile_from_view

AS_OF = date(2026, 9, 30)
CREATED = datetime(2026, 11, 15, tzinfo=UTC)
SECTIONS = ("data_used", "why", "limits", "what_would_change")
GENERIC = "informations manquantes ou signaux de vulnérabilité"


def _view(amount=10_000, max_loss=250, emergency=0, withdrawal=25, band="gt10"):
    """ProfileView du parcours complet (valeurs de l'issue #76)."""
    fields = {
        "horizon.horizon_band": band,
        "objective.goal": "growth",
        "context.amount_cad": amount,
        "risk_capacity.max_loss_cad": max_loss,
        "risk_capacity.emergency_fund": emergency,
        "risk_capacity.income_stability": "stable",
        "constraints.withdrawal_pct_12m": withdrawal,
    }
    return {
        "knowledge_level": "intermediate",
        "risk": {"tolerance": "medium", "capacity": "medium"},
        "facts": [{"field": k, "value": v} for k, v in fields.items() if v is not None],
    }


def _profile(**kw) -> InvestorProfile:
    return investor_profile_from_view(_view(**kw), "c-issue-76", created_utc=CREATED)


def _with(profile: InvestorProfile, **update) -> InvestorProfile:
    return InvestorProfile.model_validate({**profile.model_dump(), **update})


def _explain(profile: InvestorProfile):
    """Mêmes étapes que la branche sans allocation de ``build_portfolio`` : compilation, Fact ``level``, explication."""
    comp = compile_profile(profile, AS_OF)
    book = FactBook("dec-issue-76")
    with book.step("s0.policy_compiler", tool="compile_profile"):
        level = book.add("level", "Niveau de risque effectif", comp.level, "niveau", dataset="risk_levels.yaml@0.2.0")
    expl = no_allocation_explanation(
        book, comp.decision_kind or "incomplet", no_mandate_cause(comp), profile.missing_info, level
    )
    return comp, book, expl


def _texts(expl, section: str) -> list[str]:
    return [st.text_fr for st in getattr(expl, section)]


def _cited(expl) -> set[str]:
    return {fid for sec in SECTIONS for st in getattr(expl, sec) for fid in st.fact_ids}


def _assert_number_rule(book: FactBook, expl) -> None:
    """Règle du volet (explain.verify, portée par app/web/tests/portfolio.test.ts) : chaque nombre d'une phrase est
    la valeur formatée (fmt) d'un Fact qu'elle cite ; une phrase sans Fact n'écrit aucun chiffre."""
    for sec in SECTIONS:
        for st in getattr(expl, sec):
            assert not verify(book, st), (sec, st.text_fr, verify(book, st))
            if not st.fact_ids:
                assert not re.search(r"\d", st.text_fr.replace("N0", "")), st.text_fr


# --------------------------------------------------------------------------- le cas e2e


def test_e2e_profile_is_protection_by_the_dollar_rule():
    profile = _profile()
    assert profile.status.value == "COMPLETE" and profile.missing_info == []
    comp = compile_profile(profile, AS_OF)
    assert comp.decision_kind == "protection" and comp.level == "N0" and comp.policy is None
    cause = no_mandate_cause(comp)
    rule = cause.dollar_rule
    assert rule is not None and not cause.profile_protection
    assert rule.l_star == pytest.approx(250 / 10_000)
    assert rule.min_planning_loss == pytest.approx(0.129886, abs=1e-6)
    assert rule.declared_in_dollars and rule.is_below(rule.declared_loss)
    assert not rule.is_below(rule.loss_capacity)  # l_cap = 32 % : seule la perte déclarée bloque
    assert rule.yaml_path.endswith("#dollar_rule.protection")


def test_e2e_protection_cites_l_star_and_min_l_plan_and_does_not_ask_to_complete():
    _, book, expl = _explain(_profile())
    why = " ".join(_texts(expl, "why"))
    assert GENERIC not in why
    assert "La perte que vous dites pouvoir absorber (250 $, soit 2,5 % du montant)" in why
    assert "(13,0 %) : aucune allocation ne respecte cette limite." in why
    assert {"protection.l_star", "protection.min_L_plan"} <= {fid for st in expl.why for fid in st.fact_ids}
    changes = _texts(expl, "what_would_change")
    assert not any(t.startswith("Compléter") for t in changes), changes
    assert changes == ["Une perte admissible d'au moins 1 299 $ sur ce montant rendrait une allocation possible."]
    assert "tant que le profil n'est pas complété" not in " ".join(_texts(expl, "limits"))
    _assert_number_rule(book, expl)


def test_protection_facts_are_sourced_and_traced_like_the_other_facts():
    _, book, expl = _explain(_profile())
    step = book.facts["level"].trace_id
    event = next(ev for ev in book.trace if ev.trace_id == step)
    for fid in ("protection.l_star", "protection.min_L_plan"):
        fact = book.facts[fid]
        assert fact.status == "FAIT" and fact.unit == "%" and fact.trace_id == step and fid in event.fact_ids
        assert fact.sources[0].dataset == "risk_levels.yaml@0.2.0#dollar_rule.protection"
        assert fact.sources[0].processing
    assert book.facts["protection.l_star"].value == pytest.approx(0.025)
    assert book.facts["protection.max_loss_cad"].unit == "CAD" and book.facts["protection.max_loss_cad"].value == 250
    assert _cited(expl) <= set(book.facts)


@pytest.mark.parametrize("max_loss", [1, 250, 1_000, 1_298])
def test_declared_loss_below_min_l_plan_gives_protection(max_loss):
    comp = compile_profile(_profile(max_loss=max_loss), AS_OF)
    rule = no_mandate_cause(comp).dollar_rule
    assert max_loss / 10_000 < rule.min_planning_loss
    assert comp.decision_kind == "protection"


def test_the_lever_is_real_a_loss_of_the_given_amount_allows_an_allocation():
    _, book, _ = _explain(_profile())
    need = book.facts["protection.min_loss_cad"].value
    assert fmt(need, "CAD") == "1 299 $"
    comp = compile_profile(_profile(max_loss=need), AS_OF)
    assert comp.decision_kind is None and comp.policy is not None
    assert compile_profile(_profile(max_loss=need - 1), AS_OF).decision_kind == "protection"


# --------------------------------------------------------------------------- les autres causes


def test_short_horizon_names_the_horizon_and_its_lever():
    """Bande 3to10 avec retraits sous 12 mois : tous les objectifs sont des seaux prudents, T = 1 an, l_cap = 3,8 %."""
    comp, book, expl = _explain(_profile(max_loss=5_000, band="3to10"))
    rule = no_mandate_cause(comp).dollar_rule
    assert comp.decision_kind == "protection" and not rule.is_below(rule.declared_loss)
    why = " ".join(_texts(expl, "why"))
    assert "La perte que l'horizon de votre objectif le plus proche permet d'absorber (3,8 %, à 1,0 ans)" in why
    assert "vous dites" not in why
    assert _texts(expl, "what_would_change") == [
        "Un horizon d'au moins 3,6 ans pour l'objectif le plus proche rendrait une allocation possible."
    ]
    longer = dataclasses.replace(rule, horizon_years=book.facts["protection.required_horizon_years"].value)
    assert not longer.is_below(longer.horizon_loss)
    _assert_number_rule(book, expl)


def test_several_causes_give_several_necessary_levers():
    _, book, expl = _explain(_profile(max_loss=250, band="3to10"))
    changes = _texts(expl, "what_would_change")
    assert len(changes) == 2
    assert all(t.endswith("serait nécessaire pour qu'une allocation soit possible.") for t in changes)
    assert changes[0].startswith("Une perte admissible d'au moins 1 299 $")
    assert changes[1].startswith("Un horizon d'au moins 3,6 ans")
    _assert_number_rule(book, expl)


def test_high_withdrawals_name_the_withdrawal_rate():
    base = _profile(max_loss=5_000)
    goals = [g.model_dump() for g in base.goals]
    goals[0]["recurring_withdrawal"] = 450.0  # 4,5 % de 10 000 $ par an : q = q_max, l_cap = 0
    goals[0]["horizon_years"] = 10.0
    comp, book, expl = _explain(_with(base, goals=goals))
    assert comp.decision_kind == "protection"
    why = " ".join(_texts(expl, "why"))
    assert "La perte que vos retraits prévus permettent d'absorber" in why
    assert "pour des retraits de 4,5 % du montant par an" in why
    changes = _texts(expl, "what_would_change")
    assert any(t.startswith("Un taux de retrait d'au plus 3,9 % du montant par an") for t in changes), changes
    _assert_number_rule(book, expl)


def test_declared_percentage_without_dollars():
    profile = _with(_profile(), max_acceptable_loss_cad=None, max_acceptable_loss_pct=0.05)
    _, book, expl = _explain(profile)
    assert "La perte que vous dites pouvoir absorber (5,0 % du montant)" in " ".join(_texts(expl, "why"))
    assert _texts(expl, "what_would_change") == [
        "Une perte admissible d'au moins 13,0 % du montant rendrait une allocation possible."
    ]
    _assert_number_rule(book, expl)


def test_profile_status_protection_is_named_with_a_human_referral():
    profile = _with(_profile(max_loss=5_000, emergency=6), status="PROTECTION")
    comp, book, expl = _explain(profile)
    cause = no_mandate_cause(comp)
    assert comp.decision_kind == "protection" and cause.profile_protection and cause.dollar_rule is None
    assert _texts(expl, "why") == [
        "Votre profil signale une situation de vulnérabilité (statut PROTECTION) : par prudence, aucune allocation "
        "n'est calculée."
    ]
    assert book.facts["protection.profile_status"].value == "PROTECTION"
    changes = _texts(expl, "what_would_change")
    assert len(changes) == 1 and "personne qualifiée" in changes[0] and not changes[0].startswith("Compléter")
    _assert_number_rule(book, expl)


def test_profile_status_and_dollar_rule_add_up():
    _, book, expl = _explain(_with(_profile(), status="PROTECTION"))
    why = " ".join(_texts(expl, "why"))
    assert "statut PROTECTION" in why and "250 $" in why
    changes = _texts(expl, "what_would_change")
    assert "personne qualifiée" in changes[0]
    assert changes[1] == (
        "Une perte admissible d'au moins 1 299 $ sur ce montant serait nécessaire pour qu'une allocation soit possible."
    )
    _assert_number_rule(book, expl)


# --------------------------------------------------------------------------- vraiment incomplet


def test_truly_incomplete_profile_keeps_complete_and_names_the_missing_field():
    profile = _profile(amount=None)
    comp, book, expl = _explain(profile)
    assert comp.decision_kind == "incomplet" and "context.amount_cad" in profile.missing_info
    assert _texts(expl, "why") == [
        "Le profil ne permet pas encore une proposition : il manque une information indispensable au calcul (le "
        "montant à investir) ; aucune allocation n'est calculée."
    ]
    assert _texts(expl, "what_would_change") == ["Compléter : context.amount_cad."]
    assert _texts(expl, "limits") == ["Aucune allocation n'est calculée tant que le profil n'est pas complété."]
    _assert_number_rule(book, expl)


def test_waiting_position_keeps_complete_with_the_missing_fields():
    comp, book, expl = _explain(_profile(max_loss=5_000, emergency=None))
    assert comp.decision_kind == "position_attente"
    assert _texts(expl, "what_would_change") == ["Compléter : risk_capacity.emergency_fund."]
    assert "position d'attente prudente" in _texts(expl, "why")[0]
    _assert_number_rule(book, expl)


def test_low_confidence_names_the_threshold_instead_of_the_profile():
    comp, book, expl = _explain(_with(_profile(max_loss=5_000, emergency=6), confidence=0.5))
    assert comp.decision_kind == "position_attente"
    assert "La confiance du profil (50,0 %) est sous le minimum requis pour une proposition (70,0 %)." in _texts(
        expl, "why"
    )
    changes = _texts(expl, "what_would_change")
    assert changes == ["Confirmer ou préciser les réponses du profil, pour que sa confiance atteigne au moins 70,0 %."]
    _assert_number_rule(book, expl)


def test_incomplete_and_protection_texts_stay_distinct():
    _, _, protection = _explain(_profile())
    _, _, incomplete = _explain(_profile(amount=None))
    for sec in ("why", "limits", "what_would_change"):
        assert not set(_texts(protection, sec)) & set(_texts(incomplete, sec)), sec


# --------------------------------------------------------------------------- décision complète (moteur)


def test_build_portfolio_protection_decision_is_explained_and_verified():
    pytest.importorskip("numpy")
    pytest.importorskip("pandas")
    pytest.importorskip("cvxpy")
    pytest.importorskip("opentelemetry")
    from alphaforge.finance.debate import build_portfolio
    from alphaforge.finance.observability.verify import verify_decision

    d = build_portfolio(_profile(), AS_OF).decision
    assert d.kind == "protection" and d.positions == [] and d.constraints == []
    facts = {f.fact_id: f for f in d.facts}
    cited = {fid for st in d.explanation.why for fid in st.fact_ids}
    assert {"protection.l_star", "protection.min_L_plan"} <= cited <= set(facts)
    assert facts["protection.l_star"].trace_id == facts["level"].trace_id
    assert not any(st.text_fr.startswith("Compléter") for st in d.explanation.what_would_change)
    assert GENERIC not in " ".join(st.text_fr for st in d.explanation.why)
    report = verify_decision(d)
    assert report.ok, [row for row in report.statements if not row["ok"]]
