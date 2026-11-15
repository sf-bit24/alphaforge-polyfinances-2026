import pytest

from alphaforge.profile.questionnaire import (
    KINDS,
    InvalidValue,
    Questionnaire,
    default_questionnaire,
    evaluate,
    validate_value,
)


@pytest.fixture(scope="module")
def q() -> Questionnaire:
    return default_questionnaire()


def test_yaml_is_versioned_and_marked_for_review(q):
    text = open("src/alphaforge/profile/questionnaire.yaml", encoding="utf-8").read()
    assert text.startswith("# À RELIRE PAR LE VOLET FINANCE DE L'ÉQUIPE LARPATHON")
    assert q.version == "2026-11-14.1"
    assert q.threshold == 0.70 and q.cap == 0.95


def test_every_text_has_french_and_english(q):
    for spec in q.fields.values():
        assert spec.label.get("fr") and spec.label.get("en"), spec.id
        for item in spec.values:
            assert item["label"].get("fr") and item["label"].get("en"), (spec.id, item["value"])
        if spec.fallback:
            assert spec.fallback["prompt"].get("fr") and spec.fallback["prompt"].get("en")
    for question in q.questions:
        assert question.prompt.get("fr") and question.prompt.get("en"), question.id
        if question.help:
            assert question.help.get("fr") and question.help.get("en"), question.id
        for option in question.options:
            assert option["label"].get("fr") and option["label"].get("en"), question.id


def test_order_knowledge_first_then_profile_then_existing_portfolio(q):
    dims = [question.field.dimension for question in q.questions]
    assert dims[:4] == ["knowledge"] * 4
    assert q.questions[-1].id == "q_existing_portfolio"
    assert "horizon" in dims and "risk_capacity" in dims and "preferences" in dims


def _walk(q, answers):
    values, answered, order = {}, {}, []
    while True:
        question = q.next_question(values, answered)
        if question is None:
            return order
        order.append(question.id)
        value = q.validate_answer(question, answers[question.id])
        answered[question.id] = value
        values[question.field.id] = value


BASE = {
    "q_kn_invest_freq": "never",
    "q_kn_news": "rarely",
    "q_kn_products": ["none"],
    "q_kn_self": "beginner",
    "q_goal": "growth",
    "q_project_type": "home",
    "q_horizon": "3to10",
    "q_drop_reaction": "sell_some",
    "q_risk_attitude": "small",
    "q_emergency_fund": 2,
    "q_income_stability": "stable",
    "q_loss_impact": "some",
    "q_liquidity": "none",
    "q_withdrawal_pct": 20,
    "q_accounts": ["tfsa"],
    "q_currency": "cad_only",
    "q_esg": 1,
    "q_exclusions": ["none"],
    "q_interests": ["none"],
    "q_amount": 5000,
    "q_existing_portfolio": True,
}


def test_sequence_is_deterministic(q):
    assert _walk(q, BASE) == _walk(q, BASE)


def test_branching_on_earlier_answers(q):
    plain = _walk(q, BASE)
    assert "q_project_type" not in plain and "q_withdrawal_pct" not in plain and "q_exclusions" not in plain
    branched = _walk(q, {**BASE, "q_goal": "project", "q_liquidity": "some", "q_esg": 4})
    assert branched.index("q_project_type") == branched.index("q_goal") + 1
    assert branched.index("q_withdrawal_pct") == branched.index("q_liquidity") + 1
    assert branched.index("q_exclusions") == branched.index("q_esg") + 1
    assert len(branched) == len(plain) + 3


def test_render_follows_the_question_shape(q):
    rendered = q.render(q.question("q_horizon"), "fr")
    assert set(rendered) >= {
        "id",
        "source",
        "dimension",
        "kind",
        "prompt",
        "help",
        "options",
        "min",
        "max",
        "unit",
        "required",
    }
    assert rendered["source"] == "deterministic" and rendered["dimension"] == "horizon"
    assert [o["value"] for o in rendered["options"]] == ["lt3", "3to10", "gt10"]
    assert rendered["options"][0]["label"] == "Moins de 3 ans"
    assert rendered["help"].startswith("L'horizon ne se déduit")
    english = q.render(q.question("q_horizon"), "en")
    assert english["options"][0]["label"] == "Less than 3 years"
    money = q.render(q.question("q_amount"), "en")
    assert money["kind"] == "money" and money["unit"] == "CAD" and money["min"] == 0 and money["options"] == []
    scale = q.render(q.question("q_esg"), "fr")
    assert (scale["min"], scale["max"]) == (1, 5)
    number = q.render(q.question("q_emergency_fund"), "fr")
    assert number["unit"] == "mois"


def test_all_contract_kinds_are_used(q):
    assert {question.kind for question in q.questions} == set(KINDS) - {"text"}
    assert any(spec.kind == "text" for spec in q.fields.values())


@pytest.mark.parametrize(
    ("kind", "value", "kwargs", "expected"),
    [
        ("single_choice", "a", {"options": ("a", "b")}, "a"),
        ("multi_choice", ["b", "a"], {"options": ("a", "b")}, ["a", "b"]),
        ("boolean", True, {}, True),
        ("boolean", "false", {}, False),
        ("number", "12,5", {"minimum": 0, "maximum": 60}, 12.5),
        ("money", "25 000", {"minimum": 0}, 25000),
        ("percent", 40, {"minimum": 0, "maximum": 100}, 40),
        ("scale", 3, {"minimum": 1, "maximum": 5}, 3),
        ("text", "  Une mise de fonds  ", {}, "Une mise de fonds"),
    ],
)
def test_validation_accepts_typed_values(kind, value, kwargs, expected):
    assert validate_value(kind, value, **kwargs) == expected


@pytest.mark.parametrize(
    ("kind", "value", "kwargs", "reason"),
    [
        ("single_choice", "c", {"options": ("a", "b")}, "not_in_options"),
        ("single_choice", 1, {"options": ("a", "b")}, "not_a_string"),
        ("multi_choice", [], {"options": ("a", "b")}, "empty"),
        ("multi_choice", ["a", "a"], {"options": ("a", "b")}, "duplicate"),
        ("multi_choice", ["a", "none"], {"options": ("a", "none"), "exclusive": ("none",)}, "exclusive"),
        ("boolean", "maybe", {}, "not_boolean"),
        ("boolean", 1, {}, "not_boolean"),
        ("number", "abc", {}, "not_a_number"),
        ("number", True, {}, "not_a_number"),
        ("number", 61, {"maximum": 60}, "above_max"),
        ("money", -1, {"minimum": 0}, "below_min"),
        ("percent", 101, {"minimum": 0, "maximum": 100}, "above_max"),
        ("scale", 2.5, {"minimum": 1, "maximum": 5}, "not_integer"),
        ("text", "x" * 2001, {}, "too_long"),
        ("text", None, {}, "required"),
    ],
)
def test_validation_rejects_wrong_values(kind, value, kwargs, reason):
    with pytest.raises(InvalidValue) as exc:
        validate_value(kind, value, **kwargs)
    assert exc.value.reason == reason


def test_optional_question_accepts_null():
    assert validate_value("text", None, required=False) is None


def test_conditions():
    values = {"a.x": "project", "a.n": 4, "a.l": ["tfsa"]}
    assert evaluate({"field": "a.x", "in": ["project"]}, values)
    assert not evaluate({"field": "a.x", "not_in": ["project"]}, values)
    assert evaluate({"field": "a.n", "gte": 3}, values)
    assert not evaluate({"field": "a.n", "lt": 3}, values)
    assert evaluate({"field": "a.l", "contains": "tfsa"}, values)
    assert evaluate({"all": [{"field": "a.n", "gt": 1}, {"not": {"field": "a.x", "eq": "growth"}}]}, values)
    assert not evaluate({"field": "missing.field", "in": ["x"]}, values)
    assert evaluate(None, values)
