"""Issue #76, suite : « Compléter : … » nomme les champs manquants en français, jamais par leur identifiant.

Vérification de bout en bout du 2026-11-15 (« Mon profil », moteur Règles). Un profil rempli par le parcours (79 %)
disait « Compléter : approach, goal_detail, monthly_contribution_cad, past_drop_behavior, withdrawal_pattern. », un
profil partiel « Compléter : account_types, amount_cad, … ». ``missing_info`` (from_profile_view) mêle les noms courts
de ``completeness.missing``, les identifiants complets et les dimensions qu'ajoute l'adaptateur ; il les garde pour
l'audit, seule la phrase change.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from alphaforge.finance.debate.explain import missing_fields_fr, no_allocation_explanation
from alphaforge.finance.debate.facts import FactBook
from alphaforge.finance.policy import compile_profile
from alphaforge.finance.policy.compiler import no_mandate_cause
from alphaforge.finance.policy.from_profile_view import investor_profile_from_view

AS_OF = date(2026, 9, 30)
CREATED = datetime(2026, 11, 15, tzinfo=UTC)
RAW_ID = re.compile(r"\b[a-z]+_[a-z_]+\b|\b[a-z_]+\.[a-z_]+\b")  # identifiant de champ : snake_case ou dimension.champ


def _missing(*entries: tuple[str, str, str]) -> dict:
    return {"missing": [{"dimension": d, "field": f, "label": label} for d, f, label in entries]}


# Profil rempli par le parcours (client cbaf00f4…, 79 %) : les faits utiles au moteur et ses 5 champs manquants.
PARCOURS_79_FACTS = [
    ("objective.goal", "retirement"),
    ("horizon.horizon_band", "3to10"),
    ("horizon.horizon_years", 5),
    ("risk_capacity.emergency_fund", 0),
    ("risk_capacity.income_stability", "stable"),
    ("risk_capacity.employment_sector", "finance"),
    ("risk_capacity.loss_impact", "some"),
    ("risk_capacity.high_interest_debt", False),
    ("risk_capacity.max_loss_cad", 250),
    ("constraints.liquidity_need", "some"),
    ("constraints.withdrawal_pct_12m", 25),
    ("constraints.account_types", ["tfsa"]),
    ("constraints.currency_preference", "cad_usd"),
    ("context.amount_cad", 10000),
    ("context.has_existing_portfolio", False),
]
PARCOURS_79_MISSING = _missing(
    ("objective", "goal_detail", "Précision de l'objectif"),
    ("horizon", "withdrawal_pattern", "Façon de retirer l'argent"),
    ("risk_tolerance", "past_drop_behavior", "Comportement lors d'une baisse réelle"),
    ("constraints", "monthly_contribution_cad", "Ajout mensuel prévu"),
    ("preferences", "approach", "Façon d'investir préférée"),
)
# Profil partiel (client 7e2152b2…, 2 réponses) : aucun fait, 23 champs manquants (libellés du questionnaire).
PARTIAL_MISSING = _missing(
    ("objective", "goal", "Objectif principal"),
    ("horizon", "horizon_band", "Horizon de placement"),
    ("risk_tolerance", "drop_reaction", "Réaction à une baisse de 20 %"),
    ("objective", "goal_detail", "Précision de l'objectif"),
    ("horizon", "horizon_years", "Années avant le premier retrait important"),
    ("risk_capacity", "emergency_fund", "Fonds d'urgence"),
    ("risk_capacity", "loss_impact", "Effet d'une perte du quart de ce placement"),
    ("risk_capacity", "max_loss_cad", "Perte admissible"),
    ("knowledge", "level", "Niveau de connaissances"),
    ("horizon", "withdrawal_pattern", "Façon de retirer l'argent"),
    ("risk_tolerance", "risk_attitude", "Attitude face aux variations"),
    ("risk_tolerance", "past_drop_behavior", "Comportement lors d'une baisse réelle"),
    ("risk_capacity", "income_stability", "Stabilité des revenus"),
    ("risk_capacity", "high_interest_debt", "Dettes à taux d'intérêt élevé"),
    ("constraints", "liquidity_need", "Retraits prévus dans les 12 prochains mois"),
    ("constraints", "monthly_contribution_cad", "Ajout mensuel prévu"),
    ("preferences", "approach", "Façon d'investir préférée"),
    ("context", "amount_cad", "Montant à investir"),
    ("constraints", "account_types", "Types de comptes"),
    ("preferences", "esg_importance", "Importance des critères ESG"),
    ("constraints", "currency_preference", "Préférence de devise"),
    ("preferences", "interests", "Thèmes d'intérêt"),
    ("context", "has_existing_portfolio", "Portefeuille existant"),
)


def _profile(facts, completeness, risk=None):
    view = {
        "knowledge_level": "intermediate" if facts else None,
        "risk": risk or {"tolerance": None, "capacity": None},
        "facts": [{"field": k, "value": v} for k, v in facts],
    }
    return investor_profile_from_view(view, "c-issue-76-suite", created_utc=CREATED, completeness=completeness)


def _complete_statement(profile):
    comp = compile_profile(profile, AS_OF)
    book = FactBook("dec-issue-76-suite")
    with book.step("s0.policy_compiler", tool="compile_profile"):
        level = book.add("level", "Niveau de risque effectif", comp.level, "niveau", dataset="risk_levels.yaml@0.2.0")
    cause = no_mandate_cause(comp, profile, AS_OF)
    expl = no_allocation_explanation(book, comp.decision_kind or "incomplet", cause, profile.missing_info, level)
    texts = [st.text_fr for st in expl.what_would_change if st.text_fr.startswith("Compléter")]
    assert len(texts) == 1, [st.text_fr for st in expl.what_would_change]
    return comp, texts[0]


def _assert_readable(text: str) -> None:
    assert not RAW_ID.search(text), text  # aucun identifiant brut
    assert not re.search(r"\d", text), text  # phrase sans Fact : aucun chiffre
    items = text.removeprefix("Compléter : ").removesuffix(".").split(", ")
    assert len(items) == len(set(items)), items  # aucun doublon


def test_parcours_profile_at_79_names_its_missing_fields_in_french():
    profile = _profile(PARCOURS_79_FACTS, PARCOURS_79_MISSING, {"tolerance": "low_medium", "capacity": "low_medium"})
    assert profile.missing_info == [  # l'audit garde les identifiants
        "approach",
        "goal_detail",
        "monthly_contribution_cad",
        "past_drop_behavior",
        "withdrawal_pattern",
    ]
    comp, text = _complete_statement(profile)
    assert comp.decision_kind == "protection"
    assert text == (
        "Compléter : précision de l'objectif, façon de retirer l'argent, comportement lors d'une baisse réelle, ajout "
        "mensuel prévu, façon d'investir préférée."
    )
    _assert_readable(text)


def test_partial_profile_names_each_missing_field_once():
    profile = _profile([], PARTIAL_MISSING)
    assert {"amount_cad", "context.amount_cad", "horizon", "risk_tolerance"} <= set(profile.missing_info)
    comp, text = _complete_statement(profile)
    assert comp.decision_kind == "protection"
    _assert_readable(text)
    items = text.removeprefix("Compléter : ").removesuffix(".").split(", ")
    assert items.count("montant à investir") == 1  # amount_cad et context.amount_cad
    assert items.count("fonds d'urgence") == 1  # emergency_fund et risk_capacity.emergency_fund
    assert items.count("horizon de placement") == 1  # horizon (adaptateur) et horizon_band
    assert {"tolérance au risque", "capacité à prendre des risques", "réaction à une baisse", "retraits prévus"} <= set(
        items
    )
    assert "importance des critères ESG" in items  # le sigle garde sa casse


def test_incomplete_profile_names_the_amount():
    """Sans montant, pas d'objectif de retraits à 12 mois (il en faut le montant) : T = 5 ans, décision incomplet."""
    facts = [f for f in PARCOURS_79_FACTS if f[0] != "context.amount_cad"]
    profile = _profile(facts, {"missing": []}, {"tolerance": "low_medium", "capacity": "low_medium"})
    assert profile.missing_info == ["context.amount_cad"]
    comp, text = _complete_statement(profile)
    assert comp.decision_kind == "incomplet" and comp.policy is None
    assert text == "Compléter : montant à investir."


def test_missing_fields_fr_keeps_unknown_entries_readable():
    assert missing_fields_fr(["investable_wealth"]) == ["montant à investir"]
    assert missing_fields_fr(["mystery_field", "x.other_thing_12m"]) == ["mystery field", "other thing"]
    assert missing_fields_fr(["drop_reaction", "behavior.hype_reaction", "knowledge.invest_frequency"]) == [
        "fréquence des placements",
        "réaction à une baisse",
        "réaction à une action très médiatisée",
    ]
    assert missing_fields_fr([]) == []
