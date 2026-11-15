"""Issue #76, suite : lisibilité des comparaisons et des durées (vérification de bout en bout du 2026-11-15).

(a) À 1 298 $, la phrase comparait « 13,0 % » à « 13,0 % » (12,98 % et 12,99 % une fois arrondis) : elle dit
maintenant « juste sous ». (b) « 12,0 mois » devient « 12 mois », « 5,0 ans » « 5 ans » ; « 5,1 ans » reste. Les
nombres restent la valeur formatée (fmt, et son port web) d'un Fact cité.
"""

from __future__ import annotations

from alphaforge.finance.debate.explain import _duration
from alphaforge.finance.debate.facts import fmt

from .test_issue_76_protection import _assert_number_rule, _explain, _profile, _real, _texts, _with


def test_equal_rounded_values_read_just_below():
    _, book, expl = _explain(_profile(max_loss=1_298))
    assert _texts(expl, "why") == [
        "La perte que vous dites pouvoir absorber (1 298 $, soit 13,0 % du montant) est juste sous la plus petite "
        "perte de planification des portefeuilles possibles (13,0 %) : aucune allocation ne respecte cette limite."
    ]
    assert book.facts["protection.l_star"].value < book.facts["protection.min_L_plan"].value
    _assert_number_rule(book, expl)


def test_distinct_rounded_values_still_read_below():
    _, book, expl = _explain(_profile(max_loss=250))
    assert " est sous la plus petite perte de planification" in _texts(expl, "why")[0]
    assert "juste sous" not in " ".join(_texts(expl, "why"))


def test_confidence_just_below_its_threshold():
    _, book, expl = _explain(_with(_profile(max_loss=5_000, emergency=6), confidence=0.6999))
    assert "La confiance du profil (70,0 %) est juste sous le minimum requis pour une proposition (70,0 %)." in _texts(
        expl, "why"
    )
    _assert_number_rule(book, expl)


def test_whole_durations_have_no_decimal():
    _, book, expl = _explain(_real())
    why = " ".join(_texts(expl, "why"))
    changes = " ".join(_texts(expl, "what_would_change"))
    assert "fixe l'horizon de placement à 12 mois." in why
    assert "l'horizon passerait à 5 ans ;" in changes and "un horizon d'au moins 5,1 ans" in changes
    assert ",0 mois" not in why + changes and ",0 ans" not in why + changes
    horizon = book.facts["protection.horizon"]
    assert (horizon.value, horizon.unit, fmt(horizon.value, horizon.unit)) == (12, "nombre de mois", "12")
    _assert_number_rule(book, expl)


def test_duration_units():
    assert _duration(1.0) == (12, "nombre de mois")
    assert _duration(0.5) == (6, "nombre de mois")
    assert _duration(1.55) == (18.6, "mois")
    assert _duration(5.0) == (5, "nombre d'années")
    assert _duration(5.1) == (5.1, "ans")
    assert fmt(*_duration(5.1)) == "5,1 ans" and fmt(*_duration(5.0)) == "5"
