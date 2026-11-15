"""#75 : une réponse par tranche reste une tranche partout où elle est montrée. #80, point 5 : le séparateur
des résumés suit la langue.

Le code garde la borne prudente comme valeur du fait (inchangée, lue par le volet finance) et la tranche choisie
avec le fait (``band``). Le résumé, ``profil.md``, les notes de la base du client et le contexte d'A1 citent la
tranche : « moins de 1 mois », jamais « 0 mois ».

Les libellés de questionnaire.yaml séparent les milliers par une espace ordinaire (« 10 000 $ »), les montants
calculés par le code par une espace fine insécable (``THIN``).
"""

import json
import re

import pytest

from alphaforge import okf
from alphaforge.finance.policy.from_profile_view import investor_profile_from_view
from alphaforge.profile import a1, brain
from alphaforge.profile.questionnaire import default_questionnaire, format_fact, numeric_choices
from alphaforge.profile.service import render_portfolio_body
from alphaforge.profile.state import ClientSession, journal_key, profile_key

from .conftest import ScriptedFactory, answer_base, make_service

NBSP = "\u00a0"
THIN = "\u202f"
EMERGENCY = "risk_capacity.emergency_fund"
AMOUNT = "context.amount_cad"
WITHDRAWAL = "constraints.withdrawal_pct_12m"
LOSS = "risk_capacity.max_loss_cad"
# Fonds d'urgence de moins de 1 mois, montant de 10 000 $ à moins de 50 000 $, retraits de 10 % à moins de 25 %.
BANDED = {"q_emergency_fund": "lt1", "q_amount": "10k_50k", "q_liquidity": "some", "q_withdrawal_pct": "10to25"}
TURN = a1.TurnInput(turn=1, locale="fr", investor_message=None, new_answers=[], journal=[], portfolio=None)


@pytest.fixture(scope="module")
def q():
    return default_questionnaire()


def started(service, locale="fr", overrides=BANDED):
    client_id = service.handle({"action": "session.start", "locale": locale})["client_id"]
    return client_id, answer_base(service, client_id, overrides)


def stored_facts(store, client_id):
    return okf.parse(store.get(profile_key(client_id)).text).data["facts"]


def context_of(model) -> dict:
    """Contexte JSON qu'A1 a lu au premier appel de ce modèle."""
    text = model.calls[0]["messages"][0]["content"][0]["text"]
    return json.loads(text.split("<context>\n", 1)[1].split("\n</context>", 1)[0])


# ---------------------------------------------------------------------- questions de base
def test_the_value_is_unchanged_and_the_band_is_kept_with_the_fact(settings, store):
    service = make_service(settings, store)
    client_id, response = started(service)
    facts = stored_facts(store, client_id)
    # Valeurs prudentes inchangées, documentées dans questionnaire.yaml.
    assert (facts[EMERGENCY]["value"], facts[AMOUNT]["value"], facts[WITHDRAWAL]["value"]) == (0, 10000, 25)
    assert facts[EMERGENCY]["band"] == {
        "option": "lt1",
        "min": 0,
        "max": 1,
        "label": {"fr": "Moins de 1 mois", "en": "Less than 1 month"},
    }
    assert facts[AMOUNT]["band"]["option"] == "10k_50k" and facts[AMOUNT]["band"]["max"] == 50000
    # Le journal garde l'identifiant de la tranche, comme avant.
    entries = okf.parse(store.get(journal_key(client_id)).text).data["entries"]
    assert next(e for e in entries if e.get("field") == EMERGENCY)["option"] == "lt1"
    # ProfileView garde les nombres que lit le volet finance; la tranche s'y ajoute en champ facultatif.
    view = response["profile"]
    assert all(set(fact) - {"band"} == {"field", "value", "provenance", "at"} for fact in view["facts"])
    profile = investor_profile_from_view(view, client_id)
    assert (profile.emergency_fund_months, profile.investable_wealth) == (0.0, 10000.0)


def test_summary_and_profile_document_cite_the_band(settings, store):
    service = make_service(settings, store)
    client_id, response = started(service)
    dimensions = response["profile"]["dimensions"]
    assert f"de 10 000 $ à moins de 50 000 $ (10{THIN}000 $ retenus par prudence)" in dimensions["context"]["summary"]
    constraints = dimensions["constraints"]["summary"]
    assert "Part à retirer sous 12 mois" in constraints
    assert "de 10 % à moins de 25 % (25 % retenus par prudence)" in constraints
    body = okf.parse(store.get(profile_key(client_id)).text).body
    assert "| Fonds d'urgence | moins de 1 mois |" in body
    assert "0 mois" not in body
    assert f"| Montant à investir | de 10 000 $ à moins de 50 000 $ (10{THIN}000 $ retenus par prudence) |" in body


def test_no_emergency_fund_and_less_than_one_month_stay_distinct(q, settings, store):
    """Même valeur (0) pour « Aucun fonds d'urgence » et « Moins de 1 mois » : seule la tranche les distingue."""
    service = make_service(settings, store)
    shown = {}
    for option in ("none", "lt1"):
        client_id, _ = started(service, overrides={**BANDED, "q_emergency_fund": option})
        session = ClientSession.load(store, client_id)
        assert session.facts[EMERGENCY]["value"] == 0
        known = {item["field"]: item for item in a1.build_context(q, session, TURN)["known_fields"]}
        shown[option] = known[EMERGENCY]["shown_as"]
    assert shown == {"none": "aucun fonds d'urgence", "lt1": "moins de 1 mois"}


def test_profile_view_facts_carry_the_band_in_the_view_language(settings, store):
    """Le panneau Profil du web affiche la tranche (``facts[].band.label``), pas « 0 »."""
    service = make_service(settings, store)
    client_id, response = started(service)
    facts = {fact["field"]: fact for fact in response["profile"]["facts"]}
    assert facts[EMERGENCY]["value"] == 0
    assert facts[EMERGENCY]["band"] == {"option": "lt1", "label": "Moins de 1 mois", "min": 0, "max": 1}
    assert facts[AMOUNT]["band"]["label"] == "De 10 000 $ à moins de 50 000 $"
    assert "band" not in facts["horizon.horizon_band"]  # un choix sans nombre n'a pas de tranche
    english = service.handle({"action": "profile.get", "client_id": client_id, "locale": "en"})
    by_field = {fact["field"]: fact for fact in english["profile"]["facts"]}
    assert by_field[EMERGENCY]["band"]["label"] == "Less than 1 month"
    assert by_field[EMERGENCY]["value"] == 0


# ---------------------------------------------------------------------- contexte et consigne d'A1
def test_a1_context_carries_the_band_and_never_the_bound_alone(q, settings, store):
    service = make_service(settings, store)
    client_id, _ = started(service)
    context = a1.build_context(q, ClientSession.load(store, client_id), TURN)
    known = {item["field"]: item for item in context["known_fields"]}
    emergency = known[EMERGENCY]
    assert emergency["value"] == 0  # le chiffre du calcul reste lisible
    assert emergency["shown_as"] == "moins de 1 mois"
    assert emergency["band"] == {"option": "lt1", "label": "Moins de 1 mois", "min": 0, "max": 1}
    assert known[AMOUNT]["shown_as"] == f"de 10 000 $ à moins de 50 000 $ (10{THIN}000 $ retenus par prudence)"
    assert known[WITHDRAWAL]["shown_as"] == "de 10 % à moins de 25 % (25 % retenus par prudence)"
    assert all(item["shown_as"] not in {"0 mois", f"10{THIN}000 $", "25 %"} for item in context["known_fields"])
    # Les tranches de perte sont des parts de la borne basse : elles le disent, et A1 en est averti.
    loss = next(item for item in context["missing_fields"] if item["field"] == LOSS)
    assert loss["choices"][0] == {"value": "lt2_5pct", "label": f"Moins de 250 $ (2,5 % de 10{THIN}000 $)"}
    assert loss["choices"][-1]["label"] == f"3{THIN}000 $ ou plus (30 % ou plus de 10{THIN}000 $)"
    assert f'never "your 10{THIN}000 $"' in loss["choices_note"]
    assert all("du montant" not in choice["label"] for choice in loss["choices"])


def test_loss_tranches_keep_their_numbers_and_the_amount_wording_when_it_is_exact(q):
    banded = {AMOUNT: q.question("q_amount").option_band("10k_50k")}
    values = {AMOUNT: 10000}
    plain = numeric_choices(q, LOSS, values, "en")
    worded = numeric_choices(q, LOSS, values, "en", bands=banded)
    assert [(t["value"], t["number"], t["min"], t["max"]) for t in plain] == [
        (t["value"], t["number"], t["min"], t["max"]) for t in worded
    ]
    assert plain[0]["label"] == "Less than $250 (2.5% of the amount)"  # montant exact : inchangé
    assert worded[0]["label"] == "Less than $250 (2.5% of $10,000)"
    assert worded[1]["label"] == "$250 to less than $500 (2.5 to 5% of $10,000)"


def test_a1_instructions_forbid_presenting_the_cautious_value_as_an_answer(q):
    prompt = a1.system_prompt(q)
    assert "never what the investor said" in prompt
    assert 'never "your $10,000"' in prompt
    flat = " ".join(prompt.split())
    assert 'An emergency fund of "less than 1 month" is not "no emergency fund"' in flat
    # La valeur n'est pas toujours une borne : milieu (lt10k, 5 000 $) ou défaut sans bornes (unknown, 10 000 $).
    assert 'sometimes its midpoint (an amount of "less than $10,000" counts as $5,000)' in flat
    assert '"I don\'t know" counts as $10,000' in flat
    assert 'Write "at least X" only when X is `band.min`' in flat
    assert 'for "less than $10,000", never "at least $5,000"' in flat


def test_an_a1_tranche_answer_keeps_its_band(settings, store):
    loss_question = {"field": LOSS, "kind": "single_choice", "prompt": "Quelle perte pourriez-vous absorber ?"}
    factory = ScriptedFactory(
        [
            [
                (
                    "tool",
                    "finish_turn",
                    {"message": "Une question.", "questions": [loss_question], "profile_complete": False},
                )
            ]
        ],
        [[("tool", "finish_turn", {"message": "Merci.", "questions": [], "profile_complete": False})]],
    )
    service = make_service(settings, store, factory)
    client_id, _ = started(service)
    first = service.handle({"action": "followup.reply", "client_id": client_id})
    assert first["ok"], first
    option = next(o for o in first["questions"][0]["options"] if o["value"] == "2_5to5pct")
    assert option["label"] == f"De 250 $ à moins de 500 $ (2,5 à 5 % de 10{THIN}000 $)"
    pending = okf.parse(store.get(profile_key(client_id)).text).data
    assert pending["pending_choices"]["a1_1_1"]["2_5to5pct"] == 250
    assert (
        pending["pending_bands"]["a1_1_1"]["2_5to5pct"]["label"]["en"]
        == "$250 to less than $500 (2.5 to 5% of $10,000)"
    )

    answered = service.handle(
        {
            "action": "followup.reply",
            "client_id": client_id,
            "answers": [{"question_id": "a1_1_1", "value": "2_5to5pct"}],
        }
    )
    assert answered["ok"], answered
    data = okf.parse(store.get(profile_key(client_id)).text).data
    assert data["facts"][LOSS]["value"] == 250  # borne basse, inchangée
    assert data["facts"][LOSS]["band"]["option"] == "2_5to5pct"
    assert "a1_1_1" not in data["pending_bands"]  # la question répondue quitte la table
    body = okf.parse(store.get(profile_key(client_id)).text).body
    assert (
        f"| Perte admissible | de 250 $ à moins de 500 $ (2,5 à 5 % de 10{THIN}000 $; 250 $ retenus par prudence) |"
        in body
    )
    # Le tour suivant d'A1 lit la tranche de la réponse, pas seulement le nombre.
    context = context_of(factory.models[1])
    answer = context["new_answers_this_turn"][0]
    assert (
        answer["value"] == 250 and answer["band"]["label"] == f"De 250 $ à moins de 500 $ (2,5 à 5 % de 10{THIN}000 $)"
    )
    known = {item["field"]: item for item in context["known_fields"]}
    assert known[LOSS]["shown_as"].startswith("de 250 $ à moins de 500 $")


# ---------------------------------------------------------------------- notes de la base du client
def test_client_brain_context_and_skill_cite_the_band(q, settings, store):
    service = make_service(settings, store)
    client_id, _ = started(service)
    context = brain.build_context(q, ClientSession.load(store, client_id), skill=brain.INIT_SKILL)
    facts = {item["field"]: item for item in context["facts"]}
    assert facts[EMERGENCY]["shown_as"] == "moins de 1 mois"
    assert facts[EMERGENCY]["band"]["label"] == "Moins de 1 mois"
    skill = brain.load_skill(brain.INIT_SKILL).body
    assert "« Moins de 1 mois » de fonds d'urgence n'est pas « aucun fonds d'urgence »" in skill
    assert "parfois son milieu (« Moins de 10 000 $ » compte pour 5 000 $)" in skill
    assert "n'écris « au moins X » que si X est `band.min`" in skill


# ---------------------------------------------------------------------- rendu d'un fait
def test_format_fact_cites_the_band_and_the_retained_number_only_when_useful(q):
    def shown(field_id, question_id, option, locale="fr"):
        question = q.question(question_id)
        fact = {"value": question.option_number(option), "band": question.option_band(option)}
        return format_fact(q.fields[field_id], fact, locale)

    assert shown(EMERGENCY, "q_emergency_fund", "lt1") == "moins de 1 mois"
    assert shown(EMERGENCY, "q_emergency_fund", "lt1", "en") == "less than 1 month"
    assert shown(EMERGENCY, "q_emergency_fund", "1to3") == "de 1 à moins de 3 mois (1 mois retenu par prudence)"
    assert shown(EMERGENCY, "q_emergency_fund", "12plus") == "12 mois ou plus"
    assert shown(AMOUNT, "q_amount", "lt10k") == f"moins de 10 000 $ (5{THIN}000 $ retenus pour les calculs)"
    assert shown(AMOUNT, "q_amount", "unknown") == "je ne sais pas (10 000 $ retenus)"
    assert shown(AMOUNT, "q_amount", "unknown", "en") == "I don't know ($10,000 used)"
    assert (
        shown(AMOUNT, "q_amount", "10k_50k", "en") == "$10,000 to less than $50,000 ($10,000 used as a cautious figure)"
    )
    assert (
        shown(WITHDRAWAL, "q_withdrawal_pct", "10to25", "en") == "10% to less than 25% (25% used as a cautious figure)"
    )
    # Un nombre dit par l'investisseur, ou une tranche qui ne s'accorde plus avec la valeur : la valeur seule.
    assert format_fact(q.fields[EMERGENCY], {"value": 0}, "fr") == "0 mois"
    stale = {"value": 7, "band": q.question("q_emergency_fund").option_band("lt1")}
    assert format_fact(q.fields[EMERGENCY], stale, "fr") == "7 mois"


def test_a_free_text_value_replaces_the_band_and_a_refusal_restores_it(settings, store):
    service = make_service(settings, store)
    client_id, _ = started(service)
    session = ClientSession.load(store, client_id)
    band = session.facts[AMOUNT]["band"]
    session.set_fact(AMOUNT, 45000, "a1:1", confirmed=False)
    assert session.facts[AMOUNT]["replaces"]["band"] == band  # la valeur en vigueur garde sa tranche
    assert session.bands()[AMOUNT] == band
    session.reject_fact(AMOUNT, "a1:2")
    assert session.facts[AMOUNT]["band"] == band and session.facts[AMOUNT]["value"] == 10000
    session.set_fact(AMOUNT, 45000, "a1:1")  # nombre exact : plus de tranche
    assert "band" not in session.facts[AMOUNT] and AMOUNT not in session.bands()


# ---------------------------------------------------------------------- #80, point 5 : séparateur
def test_english_summaries_have_no_space_before_the_colon(settings, store):
    service = make_service(settings, store)
    client_id, response = started(service, locale="en")
    summaries = [view["summary"] for view in response["profile"]["dimensions"].values() if view["summary"]]
    constraints = response["profile"]["dimensions"]["constraints"]["summary"]
    assert "Account types: TFSA, RRSP" in constraints
    assert "Share to withdraw within 12 months: 10% to less than 25%" in constraints
    assert response["profile"]["dimensions"]["context"]["summary"].startswith(
        "Amount to invest: $10,000 to less than $50,000 ($10,000 used as a cautious figure)"
    )
    assert not any(re.search(r"\s:", summary) for summary in summaries)
    body = okf.parse(store.get(profile_key(client_id)).text).body
    assert not re.search(r"\s:", body)
    assert (
        "- Completeness: " in body and "- Risk tolerance: " in body and "| Emergency fund | less than 1 month |" in body
    )


def test_french_summaries_put_a_no_break_space_before_the_colon(settings, store):
    service = make_service(settings, store)
    client_id, response = started(service)
    summaries = [view["summary"] for view in response["profile"]["dimensions"].values() if view["summary"]]
    assert response["profile"]["dimensions"]["context"]["summary"].startswith(f"Montant à investir{NBSP}: de 10 000 $")
    assert not any(re.search(f"[^{NBSP}]:", summary) for summary in summaries)
    body = okf.parse(store.get(profile_key(client_id)).text).body
    assert f"- Complétude{NBSP}: " in body and f"- Tolérance au risque{NBSP}: " in body


def test_existing_portfolio_summary_follows_the_language():
    view = {
        "status": "draft",
        "exposures": {"total_value_cad": 1342.0, "flags": []},
        "fx": {"rate": 1.4255, "date": "2026-11-12", "source": "starter:fx_usdcad_daily.csv"},
        "positions": [],
        "unresolved": [{"raw": "XYZ fund", "reason": "not found"}],
    }
    english = render_portfolio_body(view, "en")
    assert (
        "- Status: `draft`" in english and "- Total value: 1342.0 CAD" in english and "- XYZ fund: not found" in english
    )
    assert " :" not in english
    french = render_portfolio_body(view, "fr")
    assert f"- Statut{NBSP}: `draft`" in french and f"- XYZ fund{NBSP}: not found" in french
