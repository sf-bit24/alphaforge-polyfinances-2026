import pytest

from alphaforge.profile import rules
from alphaforge.profile.questionnaire import default_questionnaire


@pytest.fixture(scope="module")
def q():
    return default_questionnaire()


def knowledge(invest, news, products, declared):
    return {
        "knowledge.invest_frequency": invest,
        "knowledge.news_frequency": news,
        "knowledge.products_known": products,
        "knowledge.self_assessment": declared,
    }


@pytest.mark.parametrize(
    ("values", "points", "measured", "level"),
    [
        (knowledge("never", "rarely", ["none"], "beginner"), 0, "beginner", "beginner"),
        (
            knowledge("several_per_year", "weekly", ["etf", "stocks", "crypto"], "intermediate"),
            5,
            "intermediate",
            "intermediate",
        ),
        # l'auto-évaluation peut dépasser le niveau mesuré d'un cran au plus
        (knowledge("never", "rarely", ["savings_gic"], "advanced"), 0, "beginner", "intermediate"),
        # une auto-évaluation plus modeste est respectée
        (knowledge("monthly", "daily", ["etf", "stocks", "bonds", "options"], "beginner"), 9, "advanced", "beginner"),
        (knowledge("monthly", "daily", ["etf", "stocks", "bonds", "options"], "advanced"), 9, "advanced", "advanced"),
        (knowledge("rarely", "monthly", ["mutual_funds"], "advanced"), 3, "intermediate", "advanced"),
    ],
)
def test_knowledge_level_rule(q, values, points, measured, level):
    assert rules.measured_knowledge_points(q, values) == points
    assert rules.measured_knowledge_level(q, values) == measured
    assert rules.knowledge_level(q, values) == level


def test_knowledge_level_unknown_until_all_answers(q):
    values = knowledge("monthly", "daily", ["etf"], None)
    assert rules.knowledge_level(q, values) is None


def test_settings_override_knowledge_level(q):
    values = {**knowledge("never", "rarely", ["none"], "beginner"), "knowledge.level": "advanced"}
    assert rules.knowledge_level(q, values) == "advanced"


def risk_values(**overrides):
    values = {
        "risk_tolerance.drop_reaction": "hold",
        "risk_tolerance.risk_attitude": "large",
        "risk_capacity.emergency_fund": 6,
        "risk_capacity.income_stability": "very_stable",
        "risk_capacity.loss_impact": "none",
        "horizon.horizon_band": "gt10",
        "constraints.liquidity_need": "none",
    }
    values.update(overrides)
    return values


def test_effective_risk_is_min_of_tolerance_and_capacity(q):
    profile = rules.risk_profile(q, risk_values())
    assert profile == {"tolerance": "medium_high", "capacity": "high", "effective": "medium_high"}
    high = rules.risk_profile(q, risk_values(**{"risk_tolerance.drop_reaction": "buy_more"}))
    assert high["effective"] == "high"
    cautious = rules.risk_profile(
        q,
        risk_values(
            **{
                "risk_tolerance.drop_reaction": "sell_some",
                "risk_tolerance.risk_attitude": "small",
                "risk_capacity.emergency_fund": 12,
                "risk_capacity.income_stability": "stable",
                "risk_capacity.loss_impact": "some",
                "horizon.horizon_band": "3to10",
            }
        ),
    )
    assert cautious == {"tolerance": "low_medium", "capacity": "medium_high", "effective": "low_medium"}


def test_high_tolerance_does_not_beat_low_capacity(q):
    profile = rules.risk_profile(
        q,
        risk_values(
            **{
                "risk_tolerance.drop_reaction": "buy_more",
                "risk_capacity.emergency_fund": 0,
                "risk_capacity.income_stability": "none",
                "risk_capacity.loss_impact": "major",
            }
        ),
    )
    assert profile["tolerance"] == "high"
    assert profile["capacity"] == "low"
    assert profile["effective"] == "low"


@pytest.mark.parametrize(
    ("overrides", "capacity"),
    [
        ({"horizon.horizon_band": "lt3"}, "low_medium"),
        ({"horizon.horizon_band": "3to10"}, "medium_high"),
        ({"constraints.liquidity_need": "large"}, "low_medium"),
        ({"risk_capacity.high_interest_debt": True}, "medium"),
        ({"risk_capacity.high_interest_debt": False}, "high"),
        ({"risk_capacity.emergency_fund": 2}, "medium_high"),
        ({"risk_capacity.emergency_fund": 0}, "medium"),
    ],
)
def test_capacity_caps(q, overrides, capacity):
    assert rules.risk_profile(q, risk_values(**overrides))["capacity"] == capacity


def test_past_behaviour_counts_only_when_experienced(q):
    assert rules.tolerance_score(q, risk_values(**{"risk_tolerance.past_drop_behavior": "sold"})) == 2
    assert rules.tolerance_score(q, risk_values(**{"risk_tolerance.past_drop_behavior": "never_experienced"})) == 3


def test_effective_risk_unknown_when_a_component_is_missing(q):
    values = risk_values()
    del values["risk_capacity.loss_impact"]
    assert rules.risk_profile(q, values)["effective"] is None


def test_completeness_weights_threshold_and_cap(q):
    empty = rules.completeness(q, {}, "fr")
    assert empty["score"] == 0 and not empty["ready"] and empty["threshold"] == 0.7 and empty["cap"] == 0.95
    assert empty["missing"][0]["field"] in ("goal", "horizon_band")
    everything = {spec.id: _sample(spec) for spec in q.fields.values() if not spec.computed}
    everything["knowledge.level"] = "advanced"
    full = rules.completeness(q, everything, "fr")
    assert full["score"] == 1.0 and full["displayed"] == 0.95 and full["ready"] and full["missing"] == []


def test_base_answers_alone_stay_below_the_threshold(q):
    base_only = {}
    for question in q.questions:
        base_only[question.field.id] = _sample(question.field)
    base_only["objective.goal"] = "growth"
    base_only["constraints.liquidity_need"] = "none"
    base_only["preferences.esg_importance"] = 2
    score = rules.completeness(q, base_only, "fr")
    assert 0.6 < score["score"] < q.threshold
    assert {m["field"] for m in score["missing"]} == {
        spec.name
        for spec in q.fields.values()
        if spec.weight > 0 and "base" not in spec.writable_by and not spec.computed
    }


def test_conditional_fields_leave_the_denominator(q):
    values = {"objective.goal": "growth"}
    missing = {m["field"] for m in rules.completeness(q, values, "fr")["missing"]}
    assert "project_type" not in missing
    missing = {m["field"] for m in rules.completeness(q, {"objective.goal": "project"}, "fr")["missing"]}
    assert "project_type" in missing


def _sample(spec):
    if spec.type == "enum":
        return spec.value_ids[0]
    if spec.type == "multi_enum":
        return [spec.value_ids[0]]
    if spec.type == "boolean":
        return False
    if spec.type == "text":
        return "texte"
    return spec.min if spec.min is not None else 1
