"""Issue #76, suite : un horizon absent du profil n'est pas présenté comme un fait.

Sans horizon, from_profile_view retient un horizon prudent d'un an pour l'objectif principal et ajoute « horizon » à
missing_info. Le profil partiel de la vérification (7e2152b2…) disait « Votre objectif principal fixe l'horizon de
placement à 12 mois », avec un Fact FAIT. La phrase dit maintenant que ces 12 mois sont un défaut (HYPOTHESE), et
« Compléter » nomme l'horizon en tête. La valeur retenue et les règles ne changent pas.
"""

from __future__ import annotations

from alphaforge.finance.policy import compile_profile
from alphaforge.finance.policy.compiler import no_mandate_cause

from .test_issue_76_missing_fields import PARTIAL_MISSING
from .test_issue_76_missing_fields import _profile as _view_profile
from .test_issue_76_protection import AS_OF, _apply, _assert_number_rule, _explain, _real, _texts

DEFAULTED = (
    "Faute d'horizon connu, le calcul retient 12 mois pour votre objectif principal, par prudence. La perte que cet "
    "horizon permet d'absorber (3,8 %) est sous la plus petite perte de planification des portefeuilles possibles "
    "(13,0 %) : aucune allocation ne respecte cette limite."
)
NO_HORIZON_FACTS = [  # profil sans aucune réponse d'horizon
    ("objective.goal", "growth"),
    ("context.amount_cad", 10000),
    ("risk_capacity.max_loss_cad", 5000),
    ("risk_capacity.emergency_fund", 6),
    ("risk_capacity.income_stability", "stable"),
]


def test_partial_profile_says_the_horizon_is_a_default():
    profile = _view_profile([], PARTIAL_MISSING)
    assert "horizon" in profile.missing_info and profile.goals[0].horizon_years == 1.0  # défaut de l'adaptateur
    comp, book, expl = _explain(profile)
    assert comp.decision_kind == "protection"
    why = expl.why[0]
    assert why.text_fr == DEFAULTED and why.label == "HYPOTHESE"
    assert "fixe l'horizon" not in " ".join(_texts(expl, "why"))
    horizon = book.facts["protection.horizon"]
    assert horizon.status == "HYPOTHESE" and horizon.value == 12  # valeur retenue inchangée
    assert "défaut prudent" in horizon.sources[0].processing
    complete = _texts(expl, "what_would_change")[0]
    assert complete.startswith("Compléter : horizon de placement, "), complete
    _assert_number_rule(book, expl)


def test_missing_horizon_alone():
    profile = _view_profile(NO_HORIZON_FACTS, {"missing": []}, {"tolerance": "medium", "capacity": "medium"})
    assert profile.missing_info == ["horizon"]
    comp, book, expl = _explain(profile)
    assert comp.decision_kind == "protection"
    assert _texts(expl, "why") == [DEFAULTED]
    assert _texts(expl, "what_would_change") == [
        "Compléter : horizon de placement.",
        "Un horizon de placement plus long serait nécessaire pour qu'une allocation soit possible. Par exemple : un "
        "horizon d'au moins 3,6 ans pour votre objectif principal.",
    ]
    levers = no_mandate_cause(comp, profile, AS_OF).levers
    assert compile_profile(_apply(profile, *levers.horizon), AS_OF).decision_kind == "position_attente"
    risk = {"tolerance": "medium", "capacity": "medium"}
    declared = _view_profile([*NO_HORIZON_FACTS, ("horizon.horizon_band", "gt10")], {"missing": []}, risk)
    assert compile_profile(declared, AS_OF).decision_kind is None  # l'horizon déclaré lève la protection
    _assert_number_rule(book, expl)


def test_declared_horizon_stays_a_fact():
    _, book, expl = _explain(_real())
    horizon_why = expl.why[1]
    assert horizon_why.text_fr.startswith("Votre objectif « retraits prévus sous 12 mois » fixe l'horizon")
    assert horizon_why.label == "FAIT" and book.facts["protection.horizon"].status == "FAIT"
    assert "Faute d'horizon" not in " ".join(_texts(expl, "why"))
