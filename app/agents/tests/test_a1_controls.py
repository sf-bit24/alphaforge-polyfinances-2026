"""Contrôles déterministes d'A1 sans modèle : tranches, questions ouvertes, citations, confirmations et secours."""

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


# ---------------------------------------------------------------------- citations d'un texte libre
def session_with(q, facts=None):
    from alphaforge.profile.state import ClientSession

    session = ClientSession.create("8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90", "fr", q)
    for field_id, value in (facts or {}).items():
        session.set_fact(field_id, value, "settings")
    return session


def a1_turn(q, session, texts):
    from alphaforge.trace import Trace

    return a1.A1Turn(
        q, session, locale="fr", turn=3, trace=Trace("fr", None), emitter=None, kb_search=None, investor_texts=texts
    )


def update(turn, field, value, evidence):
    import json

    return json.loads(turn._update_profile([{"field": field, "value": value, "evidence": evidence}]))["results"][0]


MONTHLY = "constraints.monthly_contribution_cad"


def test_quote_must_appear_in_this_turn_texts(q):
    turn = a1_turn(q, session_with(q), ["Je peux mettre 3 000 $ par mois.", "Une maison à Laval"])
    absent = update(turn, MONTHLY, 3000, "trois mille dollars")
    assert absent["status"] == "error" and "exact quote" in absent["reason"]
    assert update(turn, MONTHLY, 3000, "")["status"] == "error"
    assert turn.updates == {}
    # Une réponse texte du tour compte aussi; un texte d'un autre tour, non.
    assert update(turn, "objective.goal_detail", "Une maison", "une MAISON à laval")["status"] == "ok"
    later = a1_turn(q, session_with(q), [])
    assert update(later, "objective.goal_detail", "Une maison", "Une maison à Laval")["status"] == "error"


def test_number_must_appear_in_the_quote(q):
    turn = a1_turn(q, session_with(q), ["Je peux mettre 3 000 $ par mois, peut-être 2 500."])
    wrong = update(turn, MONTHLY, 2000, "3 000 $ par mois")
    assert wrong["status"] == "error" and "does not appear" in wrong["reason"]
    assert update(turn, MONTHLY, 3000, "Je peux mettre")["status"] == "error"


@pytest.mark.parametrize(
    ("message", "evidence"),
    [
        ("Je peux mettre 3 000 $ par mois.", "3 000 $ par mois"),
        ("Je peux mettre 3 000 $ par mois.", "mettre 3 000 $"),
        ("Je peux mettre 3000$ par mois.", "3000$"),
        ("Environ 3k par mois", "3k par mois"),
        ("Disons <3 000 $> par mois", "‹3 000 $›"),
        ("J’ajouterai « 3 000 $ » chaque mois", 'j\'ajouterai "3 000 $"'),
    ],
)
def test_accepted_quotes_and_numbers(q, message, evidence):
    turn = a1_turn(q, session_with(q), [message])
    result = update(turn, MONTHLY, 3000, evidence)
    assert result["status"] == "ok" and result["to_confirm"] is True
    assert turn.updates[MONTHLY]["value"] == 3000


def test_quote_normalization():
    assert (
        a1.normalize_quote("  L’ÉPARGNE : « oui » ‹x›  ") == 'l\'épargne :"oui"<x>'
    )  # espaces autour des guillemets retirés des deux côtés
    assert a1.number_in_quote(2500, "2,5k") and a1.number_in_quote(3.5, "3,5 ans")
    assert a1.number_in_quote(12500, "12 500 $") and not a1.number_in_quote(0, "3 000 $")
    assert not a1.number_in_quote(True, "1 an")


# ---------------------------------------------------------------------- valeurs à confirmer
def ready_facts(q):
    facts = {}
    for spec in q.fields.values():
        if spec.weight <= 0 or spec.computed or spec.when:
            continue
        if spec.type == "enum":
            facts[spec.id] = spec.value_ids[0]
        elif spec.type == "multi_enum":
            facts[spec.id] = [spec.value_ids[0]]
        elif spec.type == "boolean":
            facts[spec.id] = False
        elif spec.type == "text":
            continue
        else:
            facts[spec.id] = spec.min if spec.min is not None else 1
    for field_id in ("knowledge.invest_frequency", "knowledge.news_frequency"):
        facts[field_id] = q.fields[field_id].value_ids[0]
    facts["knowledge.products_known"] = ["none"]
    facts["knowledge.self_assessment"] = "beginner"
    return facts


def test_unconfirmed_value_does_not_count_until_confirmed(q):
    from alphaforge.profile import rules

    session = session_with(q, {"objective.goal": "growth"})
    before = rules.completeness(q, session.values())["score"]
    session.set_fact("objective.goal_detail", "Une maison", "a1:2", confirmed=False)
    assert "objective.goal_detail" not in session.values()
    assert list(session.unconfirmed()) == ["objective.goal_detail"]
    assert rules.completeness(q, session.values())["score"] == before
    session.confirm_fact("objective.goal_detail", "a1:3", question_id="cf_3_1")
    assert session.values()["objective.goal_detail"] == "Une maison" and session.unconfirmed() == {}
    assert rules.completeness(q, session.values())["score"] > before
    assert session.new_journal[-1] == {
        "at": session.new_journal[-1]["at"],
        "kind": "answer",
        "provenance": "a1:3",
        "field": "objective.goal_detail",
        "value": "Une maison",
        "question_id": "cf_3_1",
    }


def test_profile_complete_is_refused_while_a_value_waits(q):
    from alphaforge.profile import rules

    session = session_with(q, ready_facts(q))
    assert rules.completeness(q, session.values())["ready"]
    turn = a1_turn(q, session, ["Je n'ai aucune dette."])
    assert update(turn, "objective.goal_detail", "aucune dette", "aucune dette")["status"] == "ok"
    refused = turn._finish("Fini.", [], True)
    assert refused["status"] == "error" and "wait for the investor's confirmation" in refused["reason"]
    # Le décompte de complétude ignore les mises à jour du tour.
    assert json_load(turn._check_completeness())["to_confirm"] == ["objective.goal_detail"]
    session.set_fact("objective.goal_detail", "aucune dette", "a1:3", confirmed=False)
    assert a1_turn(q, session, [])._finish("Fini.", [], True)["status"] == "error"
    session.confirm_fact("objective.goal_detail", "a1:4", question_id="cf_4_1")
    assert a1_turn(q, session, [])._finish("Fini.", [], True)["status"] == "ok"


def json_load(value):
    return value if isinstance(value, dict) else __import__("json").loads(value)


def test_confirmation_questions_are_built_by_the_code(q):
    session = session_with(q)
    session.set_fact(MONTHLY, 3000, "a1:2", confirmed=False)
    session.set_fact("objective.goal_detail", "Une maison", "a1:2", confirmed=False)
    session.set_fact("preferences.approach", "mixed", "a1:2", confirmed=False)
    questions, targets = a1.confirmation_questions(q, session, turn=4, locale="en")
    assert [x["id"] for x in questions] == ["cf_4_1", "cf_4_2"]  # deux au plus, les plus lourds d'abord
    assert targets == {"cf_4_1": "objective.goal_detail", "cf_4_2": MONTHLY}
    assert questions[1]["prompt"] == "I understood: Planned monthly contribution = $3,000. Is that right?"
    assert all(x["kind"] == "boolean" and x["field"] is None and x["source"] == "deterministic" for x in questions)
