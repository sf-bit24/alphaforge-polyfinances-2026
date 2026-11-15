import copy

import pytest
import yaml

from alphaforge.profile import rules
from alphaforge.profile.questionnaire import (
    CHOICE_NUMBER_TYPES,
    KINDS,
    TYPE_TO_KIND,
    YAML_PATH,
    InvalidValueError,
    Questionnaire,
    default_questionnaire,
    evaluate,
    numeric_choices,
    validate_value,
)


@pytest.fixture(scope="module")
def q() -> Questionnaire:
    return default_questionnaire()


def test_yaml_is_versioned_and_marked_for_review(q):
    text = open("src/alphaforge/profile/questionnaire.yaml", encoding="utf-8").read()
    assert text.startswith("# À RELIRE PAR LE VOLET FINANCE DE L'ÉQUIPE LARPATHON")
    assert q.version == "2026-11-15.1"
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
    "q_kn_quiz_diversification": "dont_know",
    "q_kn_quiz_bond_rates": "dont_know",
    "q_kn_self": "beginner",
    "q_goal": "growth",
    "q_project_type": "home",
    "q_horizon": "3to10",
    "q_drop_reaction": "sell_some",
    "q_risk_attitude": "small",
    "q_sell_threshold": "10to20",
    "q_emergency_fund": "1to3",
    "q_income_stability": "stable",
    "q_employment_sector": "industry",
    "q_loss_impact": "some",
    "q_liquidity": "none",
    "q_withdrawal_pct": "10to25",
    "q_accounts": ["tfsa"],
    "q_currency": "cad_only",
    "q_esg": 1,
    "q_exclusions": ["none"],
    "q_exclusion_strictness": "absolute",
    "q_interests": ["none"],
    "q_crypto_place": "small",
    "q_crypto_max": "lt2",
    "q_hype_reaction": "no_change",
    "q_hype_share": "lt2",
    "q_amount": "lt10k",
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
    # Un champ numérique se demande par tranches : options sans nombre, ni bornes ni unité.
    money = q.render(q.question("q_amount"), "en")
    assert money["kind"] == "single_choice" and money["field"] == "context.amount_cad"
    assert (money["min"], money["max"], money["unit"]) == (None, None, None)
    assert money["options"][0] == {"value": "lt10k", "label": "Less than $10,000"}
    assert all(set(option) == {"value", "label"} for option in money["options"])
    assert money["options"][-1]["value"] == "unknown"
    scale = q.render(q.question("q_esg"), "fr")
    assert (scale["min"], scale["max"]) == (1, 5)
    months = q.render(q.question("q_emergency_fund"), "fr")
    assert months["kind"] == "single_choice" and months["options"][-1]["label"] == "12 mois ou plus"
    assert all(isinstance(option["value"], str) for option in months["options"])


def test_all_contract_kinds_are_used(q):
    # Les questions de base n'ont plus de saisie libre : number, money et percent se posent par tranches.
    assert {question.kind for question in q.questions} == {"single_choice", "multi_choice", "boolean", "scale"}
    assert {spec.type for spec in q.fields.values()} == set(TYPE_TO_KIND)
    assert set(TYPE_TO_KIND.values()) == set(KINDS)
    numeric = [question for question in q.questions if question.field.type in CHOICE_NUMBER_TYPES]
    assert {question.field.type for question in numeric} == set(CHOICE_NUMBER_TYPES)
    assert all(question.numeric_choice for question in numeric)
    assert any(spec.kind == "text" for spec in q.fields.values())


def _raw():
    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))


def _question(raw, question_id):
    return next(item for item in raw["questions"] if item["id"] == question_id)


def test_numeric_choice_questions_need_a_number_within_the_field_bounds():
    raw = _raw()
    Questionnaire.from_dict(raw)
    cases = []
    missing = copy.deepcopy(raw)
    del _question(missing, "q_emergency_fund")["options"][2]["number"]
    cases.append(missing)
    text = copy.deepcopy(raw)
    _question(text, "q_withdrawal_pct")["options"][0]["number"] = "10"
    cases.append(text)
    boolean = copy.deepcopy(raw)
    _question(boolean, "q_amount")["options"][0]["number"] = True
    cases.append(boolean)
    above = copy.deepcopy(raw)
    _question(above, "q_withdrawal_pct")["options"][-1]["number"] = 150
    cases.append(above)
    below = copy.deepcopy(raw)
    _question(below, "q_emergency_fund")["options"][0]["number"] = -1
    cases.append(below)
    bad_id = copy.deepcopy(raw)
    _question(bad_id, "q_amount")["options"][0]["value"] = "Moins de 10 000"
    cases.append(bad_id)
    for broken in cases:
        with pytest.raises(ValueError):
            Questionnaire.from_dict(broken)


def test_other_questions_keep_the_kind_and_value_checks():
    raw = _raw()
    wrong_kind = copy.deepcopy(raw)
    _question(wrong_kind, "q_esg")["kind"] = "single_choice"  # scale : pas de tranches
    _question(wrong_kind, "q_esg")["options"] = [
        {"value": "a", "number": 1, "label": {"fr": "a", "en": "a"}},
        {"value": "b", "number": 2, "label": {"fr": "b", "en": "b"}},
    ]
    other_values = copy.deepcopy(raw)
    _question(other_values, "q_currency")["options"] = [
        {"value": "cad_only", "label": {"fr": "a", "en": "a"}},
        {"value": "eur", "label": {"fr": "b", "en": "b"}},
    ]
    free_number = copy.deepcopy(raw)
    _question(free_number, "q_amount")["kind"] = "number"  # money demandé en number
    for broken in (wrong_kind, other_values, free_number):
        with pytest.raises(ValueError):
            Questionnaire.from_dict(broken)


@pytest.mark.parametrize(
    ("question_id", "option", "number"),
    [
        ("q_emergency_fund", "none", 0),
        ("q_emergency_fund", "lt1", 0),
        ("q_emergency_fund", "1to3", 1),
        ("q_emergency_fund", "3to6", 3),
        ("q_emergency_fund", "6to12", 6),
        ("q_emergency_fund", "12plus", 12),
        ("q_withdrawal_pct", "lt10", 10),
        ("q_withdrawal_pct", "10to25", 25),
        ("q_withdrawal_pct", "25to50", 50),
        ("q_withdrawal_pct", "50plus", 100),
        ("q_amount", "lt10k", 5000),
        ("q_amount", "10k_50k", 10000),
        ("q_amount", "50k_150k", 50000),
        ("q_amount", "150k_500k", 150000),
        ("q_amount", "500k_plus", 500000),
        ("q_amount", "unknown", 10000),
    ],
)
def test_tranche_numbers_are_the_prudent_bound(q, question_id, option, number):
    question = q.question(question_id)
    assert q.validate_answer(question, option) == option
    assert question.option_number(option) == number
    with pytest.raises(InvalidValueError):
        q.validate_answer(question, number)  # le nombre n'est pas une réponse : seul l'identifiant l'est


@pytest.mark.parametrize(("months", "points"), [(0, 0), (1, 1), (3, 3), (6, 4), (12, 4)])
def test_emergency_fund_tranches_keep_the_capacity_points(q, months, points):
    # Mêmes points qu'avant pour les valeurs des tranches (seuils [[0, 0], [0.5, 1], [3, 3], [6, 4]]).
    base = {
        "risk_capacity.income_stability": "very_stable",
        "risk_capacity.loss_impact": "none",
        "horizon.horizon_band": "gt10",
    }
    # income 4 + loss 4 + fonds : la moyenne entière donne le point du fonds d'urgence.
    assert rules.capacity_score(q, {**base, "risk_capacity.emergency_fund": months}) == (8 + points) // 3


def test_numeric_choices_are_computed_by_the_code(q):
    years = numeric_choices(q, "horizon.horizon_years", {"horizon.horizon_band": "3to10"}, "fr")
    assert [(t["value"], t["number"], t["min"], t["max"]) for t in years] == [
        ("3to5", 3, 3, 5),
        ("5to7", 5, 5, 7),
        ("7to10", 7, 7, 10),
    ]
    assert len(numeric_choices(q, "horizon.horizon_years", {}, "fr")) == 10  # bande inconnue : toutes
    loss = numeric_choices(q, "risk_capacity.max_loss_cad", {"context.amount_cad": 50000}, "fr")
    assert [t["number"] for t in loss] == [0, 1250, 2500, 5000, 10000, 15000]
    assert loss[1]["label"] == "De 1\u202f250 $ à moins de 2\u202f500 $ (2,5 à 5 %)"
    english = numeric_choices(q, "risk_capacity.max_loss_cad", {"context.amount_cad": 50000}, "en")
    assert english[-1]["label"] == "$15,000 or more (30% or more)"
    absolute = numeric_choices(q, "risk_capacity.max_loss_cad", {}, "fr")
    assert absolute[0]["value"] == "lt1k" and absolute[-1]["value"] == "25k_plus"
    monthly = numeric_choices(q, "constraints.monthly_contribution_cad", {}, "en")
    assert (monthly[0]["value"], monthly[0]["label"], monthly[0]["number"]) == ("none", "No contribution", 0)
    # Les champs d'une question de base reprennent ses options.
    assert [t["value"] for t in numeric_choices(q, "constraints.withdrawal_pct_12m", {}, "fr")] == [
        "lt10",
        "10to25",
        "25to50",
        "50plus",
    ]
    assert numeric_choices(q, "preferences.esg_importance", {}, "fr") == []
    assert numeric_choices(q, "objective.goal", {}, "fr") == []


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
    with pytest.raises(InvalidValueError) as exc:
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


# ---------------------------------------------------------------------- profil court lu par l'étape 0 (finance)
SHORT_PROFILE_CODES = {
    "knowledge.quiz_diversification": ["single_stock", "etf", "same", "dont_know"],
    "knowledge.quiz_bond_rates": ["rises", "falls", "same", "no_link", "dont_know"],
    "risk_tolerance.sell_threshold_pct": ["none", "lt5", "5to10", "10to20", "20to30", "gte30", "dont_know"],
    "risk_capacity.employment_sector": [
        "technology",
        "finance",
        "energy",
        "healthcare",
        "public",
        "industry",
        "retail",
        "unemployed",
        "prefer_not",
    ],
    "preferences.exclusion_strictness": ["absolute", "small_share_in_fund", "preference", "dont_know"],
    "preferences.crypto_place": ["none", "small", "larger", "let_system_decide", "dont_know"],
    "preferences.crypto_max_pct": ["lt2", "2to5", "5to10", "gt10", "propose_limit"],
    "behavior.hype_reaction": ["buy_a_lot", "buy_some", "wait", "no_change", "dont_know"],
    "behavior.hype_position_share": ["lt2", "2to5", "5to10", "gt10", "dont_know"],
}


def test_short_profile_fields_carry_the_engine_codes(q):
    from alphaforge.finance.strategy.config import load_strategy

    for field_id, codes in SHORT_PROFILE_CODES.items():
        spec = q.fields[field_id]
        assert spec.type == "enum" and list(spec.value_ids) == codes, field_id
        assert spec.weight == 0 and not spec.summary, field_id  # hors complétude et hors résumés
        assert q.question_for_field(field_id) is not None, field_id
    # Les quiz ne s'écrivent que par un clic; le reste peut aussi venir d'un texte libre confirmé (A1).
    assert q.fields["knowledge.quiz_bond_rates"].writable_by == ("base",)
    assert "a1" in q.fields["behavior.hype_reaction"].writable_by
    # Chaque code comparé par strategy.yaml existe dans le champ que lit style_inputs_from_view.
    cfg = load_strategy()
    pc = cfg.profile_codes
    values = {field_id: set(codes) for field_id, codes in SHORT_PROFILE_CODES.items()}
    assert set(pc["fomo_hype_reaction"]) | set(pc["attention_hype_reaction"]) <= values["behavior.hype_reaction"]
    assert set(pc["fomo_hype_share"]) <= values["behavior.hype_position_share"]
    assert set(pc["low_composure_sell_threshold"]) <= values["risk_tolerance.sell_threshold_pct"]
    for quiz, correct in pc["quiz_correct"].items():
        assert correct in values[f"knowledge.{quiz}"]
    assert set(pc["exclusion_strictness"].values()) <= values["preferences.exclusion_strictness"]
    assert set(cfg.sectors.employment_to_tag) <= values["risk_capacity.employment_sector"]


def test_short_profile_questions_follow_their_conditions(q):
    plain = _walk(q, BASE)
    for question_id in ("q_kn_quiz_diversification", "q_kn_quiz_bond_rates"):
        assert plain.index(question_id) < plain.index("q_kn_self")  # questions rapides, puis l'auto-évaluation
    assert plain.index("q_sell_threshold") == plain.index("q_risk_attitude") + 1
    assert plain.index("q_employment_sector") == plain.index("q_income_stability") + 1
    assert plain.index("q_hype_reaction") == plain.index("q_interests") + 1
    for question_id in ("q_exclusion_strictness", "q_crypto_place", "q_crypto_max", "q_hype_share"):
        assert question_id not in plain
    branched = _walk(
        q,
        {
            **BASE,
            "q_esg": 4,
            "q_exclusions": ["fossil_fuels", "tobacco"],
            "q_interests": ["technology", "crypto"],
            "q_crypto_place": "larger",
            "q_hype_reaction": "buy_some",
        },
    )
    assert branched.index("q_exclusion_strictness") == branched.index("q_exclusions") + 1
    assert branched.index("q_crypto_place") == branched.index("q_interests") + 1
    assert branched.index("q_crypto_max") == branched.index("q_crypto_place") + 1
    assert branched.index("q_hype_share") == branched.index("q_hype_reaction") + 1
    # Aucune exclusion, aucune envie de cryptoactifs, aucun achat : pas de relance.
    quiet = _walk(
        q,
        {
            **BASE,
            "q_esg": 4,
            "q_exclusions": ["none"],
            "q_interests": ["crypto"],
            "q_crypto_place": "let_system_decide",
            "q_hype_reaction": "wait",
        },
    )
    assert "q_crypto_place" in quiet
    for question_id in ("q_exclusion_strictness", "q_crypto_max", "q_hype_share"):
        assert question_id not in quiet
    strictness = q.fields["preferences.exclusion_strictness"]
    assert not q.applicable(strictness.when, {"preferences.exclusions": []})
    assert not q.applicable(strictness.when, {})


@pytest.mark.parametrize(
    ("question_id", "accepted", "rejected"),
    [
        ("q_kn_quiz_diversification", "single_stock", "stock"),
        ("q_kn_quiz_bond_rates", "falls", "down"),
        ("q_sell_threshold", "5to10", "5-10"),
        ("q_employment_sector", "prefer_not", "tech"),
        ("q_exclusion_strictness", "small_share_in_fund", "fund_tolerated"),
        ("q_crypto_place", "let_system_decide", "some"),
        ("q_crypto_max", "propose_limit", "dont_know"),
        ("q_hype_reaction", "buy_a_lot", "buy"),
        ("q_hype_share", "gt10", "10plus"),
    ],
)
def test_short_profile_answers_are_checked_against_the_codes(q, question_id, accepted, rejected):
    question = q.question(question_id)
    assert q.validate_answer(question, accepted) == accepted
    assert q.validate_field_value(question.field.id, accepted) == accepted
    with pytest.raises(InvalidValueError) as exc:
        q.validate_answer(question, rejected)
    assert exc.value.reason == "not_in_options"
    rendered = q.render(question, "fr")
    assert rendered["kind"] == "single_choice" and rendered["field"] == question.field.id
    assert [o["value"] for o in rendered["options"]] == SHORT_PROFILE_CODES[question.field.id]


def test_short_profile_fields_leave_completeness_unchanged(q):
    branches = {"q_esg": 4, "q_exclusions": ["tobacco"], "q_interests": ["crypto"], "q_hype_reaction": "buy_a_lot"}
    answers = {**BASE, **branches}
    values = {}
    for question_id in _walk(q, answers):
        question = q.question(question_id)
        value = q.validate_answer(question, answers[question_id])
        values[question.field.id] = question.option_number(value) if question.numeric_choice else value
    core = {field_id: value for field_id, value in values.items() if field_id not in SHORT_PROFILE_CODES}
    assert set(values) - set(core) == set(SHORT_PROFILE_CODES)  # toutes posées dans ce parcours
    before, after = rules.completeness(q, core, "fr"), rules.completeness(q, values, "fr")
    assert before["score"] == after["score"] < q.threshold == 0.70
    assert before["missing"] == after["missing"]
    assert not set(rules.missing_fields(q, {})) & set(SHORT_PROFILE_CODES)  # jamais dans les champs manquants d'A1
    assert q.render(q.question("q_hype_reaction"), "en")["dimension"] == "behavior"
