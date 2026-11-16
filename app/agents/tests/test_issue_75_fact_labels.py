"""Suite de #75 : la liste « Faits » du panneau Profil lit le libellé de chaque valeur, pas son code.

``ProfileView.facts[].label`` (facultatif) donne la valeur dans la langue de la vue : « Très stables » et non
``very_stable``, « CELI, REER » et non ``["tfsa", "rrsp"]``, « Non » et non ``false``. ``value`` ne change pas :
le volet finance lit toujours le même code ou le même nombre.
"""

import pytest

from alphaforge.finance.policy.from_profile_view import investor_profile_from_view, style_inputs_from_view
from alphaforge.profile.questionnaire import default_questionnaire, fact_label

from .conftest import answer_base, make_service


@pytest.fixture(scope="module")
def q():
    return default_questionnaire()


def started(service, locale="fr"):
    client_id = service.handle({"action": "session.start", "locale": locale})["client_id"]
    return client_id, answer_base(service, client_id)


def by_field(response):
    return {fact["field"]: fact for fact in response["profile"]["facts"]}


def test_choice_facts_carry_the_label_of_the_chosen_option(settings, store):
    service = make_service(settings, store)
    client_id, response = started(service)
    facts = by_field(response)
    # Les valeurs restent les codes du questionnaire.
    assert facts["risk_capacity.income_stability"]["value"] == "very_stable"
    assert facts["constraints.account_types"]["value"] == ["tfsa", "rrsp"]
    assert facts["context.has_existing_portfolio"]["value"] is False
    labels = {field: fact["label"] for field, fact in facts.items()}
    assert labels["risk_capacity.income_stability"] == "Très stables"
    assert labels["constraints.account_types"] == "CELI, REER"
    assert labels["horizon.horizon_band"] == "10 ans et plus"
    assert labels["risk_tolerance.sell_threshold_pct"] == "De 20 % à moins de 30 %"
    assert labels["constraints.currency_preference"] == "Dollars canadiens et américains"
    assert labels["knowledge.products_known"] == "FNB (fonds négociés en bourse), Actions, Cryptoactifs"
    assert labels["context.has_existing_portfolio"] == "Non"
    assert labels["preferences.esg_importance"] == "4/5"
    assert labels["risk_capacity.emergency_fund"] == "De 6 à moins de 12 mois"  # tranche : son libellé
    # Aucun fait connu du questionnaire n'est montré en code JSON.
    assert all(not label.startswith(("[", "{")) and '"' not in label for label in labels.values())
    # La vue en anglais donne les libellés anglais.
    english = by_field(service.handle({"action": "profile.get", "client_id": client_id, "locale": "en"}))
    assert english["risk_capacity.income_stability"]["label"] == "Very stable"
    assert english["constraints.account_types"]["label"] == "TFSA, RRSP"
    assert english["context.has_existing_portfolio"]["label"] == "No"
    assert english["horizon.horizon_band"]["label"] == "10 years or more"


def test_labels_change_nothing_the_finance_engine_reads(settings, store):
    service = make_service(settings, store)
    client_id, response = started(service)
    view = response["profile"]
    bare = {**view, "facts": [{k: v for k, v in f.items() if k not in {"label", "band"}} for f in view["facts"]]}

    def read(profile_view):
        profile = investor_profile_from_view(profile_view, client_id).model_dump(mode="json")
        profile.pop("created_utc", None)
        return profile, repr(style_inputs_from_view(profile_view))

    assert read(view) == read(bare)


def test_unknown_codes_and_malformed_values_stay_plain_text(q):
    def label(field_id, value):
        return fact_label(q.fields[field_id], {"value": value}, "fr")

    assert label("risk_capacity.income_stability", "code_retire") == "code_retire"  # code sans libellé : tel quel
    assert label("constraints.account_types", ["tfsa", "code_retire"]) == "CELI, code_retire"
    assert label("constraints.account_types", "tfsa") == "CELI"  # une valeur seule au lieu d'une liste
    assert label("constraints.account_types", []) == "—"
    assert label("objective.goal", ["growth", "income"]) == "growth, income"  # liste dans un choix simple
    assert label("context.amount_cad", "beaucoup") == "beaucoup"  # nombre illisible : sans erreur
    assert label("constraints.monthly_contribution_cad", 3000) == "3\u202f000 $"
    assert label("objective.goal_detail", "Une mise de fonds dans 5 ans") == "Une mise de fonds dans 5 ans"
    assert fact_label(q.fields["risk_capacity.high_interest_debt"], {"value": True}, "en") == "Yes"
