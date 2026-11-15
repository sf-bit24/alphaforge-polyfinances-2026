"""Issue #80, point 3 : les notes des positions d'A2 sont écrites dans la langue de la session.

Les notes viennent de deux endroits : le code (``profile/portfolio.py``) et le modèle (champ ``notes`` de
``record_positions``). Le code écrit les siennes dans la langue de la session; pour le modèle, la consigne d'A2
demande la langue donnée par ``language`` et le contexte du tour transmet cette langue.
"""

import json

import pytest

from alphaforge.profile import a2 as a2_agent
from alphaforge.profile.portfolio import RawPosition, build_view, positions_to_raws

from .conftest import ScriptedFactory, answer_base, make_service

# Un fonds absent de l'univers, valeur fournie sans devise : le code ajoute deux notes.
HOUSE_FUND = RawPosition(raw="Fonds maison ABC 5 000", ticker="ZZQX", name="Fonds maison ABC", market_value=5000)
# Un titre introuvable et sans valeur : le code donne la raison.
NO_VALUE = RawPosition(raw="fonds maison XYZ", name="fonds maison XYZ")

NOTES = {
    "fr": "devise supposée CAD (non précisée); titre non identifié; valeur fournie par l'investisseur",
    "en": "currency assumed to be CAD (not stated); security not identified; value given by the investor",
}
REASONS = {"fr": "titre introuvable et aucune valeur fournie", "en": "security not found and no value given"}


@pytest.mark.parametrize("locale", ["fr", "en"])
def test_code_notes_and_reasons_follow_the_session_language(locale):
    view = build_view([HOUSE_FUND, NO_VALUE], status="draft", locale=locale)
    assert view["positions"][0]["notes"] == NOTES[locale]
    assert view["unresolved"] == [{"raw": "fonds maison XYZ", "reason": REASONS[locale], "position_id": "p2"}]


def test_code_notes_default_to_french():
    view = build_view([HOUSE_FUND], status="draft")
    assert view["positions"][0]["notes"] == NOTES["fr"]


@pytest.mark.parametrize("confirm_locale", ["fr", "en"])
def test_confirming_keeps_one_copy_of_each_code_note(confirm_locale):
    """La confirmation relit les notes des positions : le code n'en ajoute pas une seconde copie, même dans
    l'autre langue (``portfolio.confirm`` ne transmet pas encore la langue de la session)."""
    draft = build_view([HOUSE_FUND], status="draft", locale="en")
    confirmed = build_view(positions_to_raws(draft["positions"]), status="confirmed", locale=confirm_locale)
    assert confirmed["positions"][0]["notes"] == NOTES["en"]


NOTES_INSTRUCTION = "Write every `notes` and every `unparsed` reason in the language given by `language`"


def test_a2_instructions_ask_for_notes_in_the_session_language():
    assert NOTES_INSTRUCTION in " ".join(a2_agent.SYSTEM_PROMPT.split())
    position_schema = a2_agent.RECORD_POSITIONS_SCHEMA["json"]["properties"]["positions"]["items"]
    assert "`language`" in position_schema["properties"]["notes"]["description"]
    unparsed_schema = a2_agent.RECORD_POSITIONS_SCHEMA["json"]["properties"]["unparsed"]["items"]
    assert "`language`" in unparsed_schema["properties"]["reason"]["description"]


def _context(model_call) -> dict:
    text = model_call["messages"][0]["content"][0]["text"]
    return json.loads(text.split("<context>\n", 1)[1].split("\n</context>", 1)[0])


@pytest.mark.parametrize(("locale", "language"), [("fr", "French (Canada)"), ("en", "English")])
def test_a2_turn_passes_the_session_language_to_the_model_and_the_code(settings, store, locale, language):
    record = (
        "tool",
        "record_positions",
        {
            "positions": [
                {"raw": "100 RY.TO CELI", "ticker": "RY.TO", "quantity": 100, "account_type": "tfsa"},
                {"raw": "Fonds maison ABC 5 000", "ticker": "ZZQX", "name": "Fonds maison ABC", "market_value": 5000},
            ],
            "unparsed": [{"raw": "ligne illisible ###"}],
        },
    )
    factory = ScriptedFactory([[record], [("tool", "finish_turn", {"message": "2 positions."})]])
    service = make_service(settings, store, factory)
    client_id = service.handle({"action": "session.start", "locale": locale})["client_id"]
    answer_base(service, client_id, {"q_existing_portfolio": True})
    response = service.handle({"action": "portfolio.submit", "client_id": client_id, "text": "100 RY.TO CELI"})
    assert response["ok"], response

    first_call = factory.models[0].calls[0]
    assert _context(first_call)["language"] == language
    assert NOTES_INSTRUCTION in " ".join(first_call["system_prompt"].split())
    view = response["portfolio"]
    assert view["positions"][0]["notes"] is None
    assert view["positions"][1]["notes"] == NOTES[locale]
    fallback = {"fr": "illisible", "en": "unreadable"}[locale]
    assert {"raw": "ligne illisible ###", "reason": fallback} in view["unresolved"]
