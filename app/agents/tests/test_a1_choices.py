"""Contrôles déterministes d'A1 sans modèle : questions à tranches, questions ouvertes et questions de secours."""

import pytest

from alphaforge.profile import a1
from alphaforge.profile.questionnaire import default_questionnaire, numeric_choices

VALUES = {"horizon.horizon_band": "gt10", "context.amount_cad": 40000}


@pytest.fixture(scope="module")
def q():
    return default_questionnaire()


def build(q, raw, **kwargs):
    return a1.build_question(q, raw, turn=2, index=1, locale="fr", values=VALUES, **kwargs)


def loss(options=None, kind="single_choice"):
    raw = {"field": "risk_capacity.max_loss_cad", "kind": kind, "prompt": "Quelle perte pourriez-vous absorber ?"}
    if options is not None:
        raw["options"] = options
    return raw


def test_money_kind_is_refused_on_a_numeric_field(q):
    for kind in ("money", "number", "percent"):
        question, error = build(q, loss(kind=kind))
        assert question is None and f"kind {kind} is not allowed" in error
    question, error = build(q, {"kind": "number", "prompt": "Combien de comptes avez-vous ?", "dimension": "context"})
    assert question is None and "not allowed" in error  # sans champ non plus : pas de saisie libre d'un nombre


def test_invented_tranche_is_refused(q):
    question, error = build(q, loss([{"value": "lt2_5pct", "label": "x"}, {"value": "lt9k", "label": "Moins de 9 k$"}]))
    assert question is None and "'lt9k' is not a tranche" in error
    gap, error = build(q, loss([{"value": "lt2_5pct", "label": "x"}, {"value": "5to10pct", "label": "y"}]))
    assert gap is None and "adjacent" in error
    single, error = build(q, loss([{"value": "lt2_5pct", "label": "x"}]))
    assert single is None and "2 to 8 options" in error


def test_a_run_of_adjacent_tranches_is_accepted_with_the_code_labels(q):
    computed = numeric_choices(q, "risk_capacity.max_loss_cad", VALUES, "fr")
    picked = [{"value": t["value"], "label": "Libellé inventé"} for t in computed[3:1:-1]]  # désordre accepté
    question, error = build(q, loss(picked))
    assert error is None
    assert question["kind"] == "single_choice" and question["id"] == "a1_2_1"
    assert question["options"] == [{"value": t["value"], "label": t["label"]} for t in computed[2:4]]
    assert question["options"][0]["label"] == "De 2 000 $ à moins de 4 000 $ (5 à 10 %)"
    assert (question["min"], question["max"], question["unit"]) == (None, None, None)
    table = a1.choice_numbers(q, question, VALUES, "fr")
    assert table == {"5to10pct": 2000, "10to20pct": 4000}
    everything, error = build(q, loss())
    assert error is None and [o["value"] for o in everything["options"]] == [t["value"] for t in computed]


def test_horizon_tranches_stay_inside_the_known_band(q):
    question, error = build(q, {"field": "horizon.horizon_years", "kind": "single_choice", "prompt": "Dans combien ?"})
    assert error is None and [o["value"] for o in question["options"]] == ["10to15", "15to20", "20to30", "30plus"]
    outside, error = build(
        q,
        {
            "field": "horizon.horizon_years",
            "kind": "single_choice",
            "prompt": "Dans combien ?",
            "options": [{"value": "5to7", "label": "x"}, {"value": "7to10", "label": "y"}],
        },
    )
    assert outside is None and "not a tranche" in error
    for t in numeric_choices(q, "horizon.horizon_years", VALUES, "fr"):
        assert a1.consistency_warnings(q, VALUES, "horizon.horizon_years", t["number"]) == []


def test_open_questions_are_the_exception(q):
    goal = {"field": "objective.goal_detail", "kind": "text", "prompt": "Que voulez-vous accomplir ?"}
    explore = {"kind": "text", "prompt": "Y a-t-il autre chose à savoir ?", "dimension": "context"}
    assert build(q, goal)[1] is None
    assert build(q, explore)[1] is None
    # Un champ qui admet des choix ne se demande pas en texte libre.
    question, error = build(q, {"field": "preferences.approach", "kind": "text", "prompt": "Comment investir ?"})
    assert question is None and "admits choices" in error
    question, error = build(q, {"field": "horizon.horizon_years", "kind": "text", "prompt": "Dans combien d'années ?"})
    assert question is None and "single_choice" in error
    # La troisième question ouverte de la session est refusée.
    assert build(q, explore, open_used=1)[1] is None
    question, error = build(q, explore, open_used=2)
    assert question is None and "maximum is 2" in error


def test_open_fields_come_from_the_yaml(q):
    assert q.open_fields == ("objective.goal_detail",)
    assert (q.max_open_questions, q.max_generated) == (2, 8)


def test_fallback_questions_offer_tranches(q):
    values = {**VALUES, "objective.goal": "growth"}
    questions = a1.fallback_questions(q, values, turn=3, locale="fr")
    assert [(x["id"], x["field"], x["kind"]) for x in questions] == [
        ("fb_3_1", "objective.goal_detail", "text"),
        ("fb_3_2", "horizon.horizon_years", "single_choice"),
        ("fb_3_3", "risk_capacity.max_loss_cad", "single_choice"),
    ]
    computed = numeric_choices(q, "risk_capacity.max_loss_cad", values, "fr")
    assert questions[2]["options"] == [{"value": t["value"], "label": t["label"]} for t in computed]
    # Plus de question ouverte possible : le secours passe au champ suivant; limit et skip sont respectés.
    closed = a1.fallback_questions(q, values, turn=3, locale="fr", open_left=0, limit=2, skip={"horizon.horizon_years"})
    assert [x["field"] for x in closed] == ["risk_capacity.max_loss_cad", "horizon.withdrawal_pattern"]
