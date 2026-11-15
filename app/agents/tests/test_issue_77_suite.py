"""Suite de l'issue #77, après la vérification sur Bedrock réel : un NAS de 9 chiffres collés.

« Mon NAS est 046454286 » passait le garde-fou : le modèle le recevait et ``journal.md`` l'écrivait. Il est refusé
avant l'appel au modèle (``personal_data.contains_sin``), sans toucher aux données de portefeuille qu'A2 doit lire
(CUSIP numérique, quantité, montant, numéro de compte fictif). Le tableau de cas est partagé avec le simulateur.
"""

import json
from pathlib import Path

import pytest

from alphaforge.config import Settings
from alphaforge.personal_data import contains_sin, luhn_valid

from .conftest import ScriptedFactory, answer_base, make_service

CASES = json.loads((Path(__file__).parent / "fixtures" / "issue_77_sin_cases.json").read_text(encoding="utf-8"))
SIN = "046454286"
SIN_DETAILS = {"reason": "personal_data", "entity": "CA_SIN"}
SIN_MESSAGES = {
    "fr": "Votre message contient un renseignement personnel (NAS) : retirez-le, puis renvoyez-le.",
    "en": "Your message contains personal information (SIN): remove it, then send it again.",
}


@pytest.fixture
def guarded_settings(tmp_path):
    return Settings.from_env(
        {
            "AGENT_ROLE": "profile",
            "ALPHAFORGE_STORE": "local",
            "ALPHAFORGE_LOCAL_DIR": str(tmp_path / "kb"),
            "ALPHAFORGE_GUARDRAIL_ID": "gr-test",
        }
    )


def _client(service, locale="fr", **overrides) -> str:
    client_id = service.handle({"action": "session.start", "locale": locale})["client_id"]
    answer_base(service, client_id, overrides)
    return client_id


def _stored_texts(tmp_path) -> str:
    return "\n".join(path.read_text(errors="replace") for path in Path(tmp_path / "kb").rglob("*") if path.is_file())


# ------------------------------------------------------------------ 1. NAS de 9 chiffres collés
@pytest.mark.parametrize("case", CASES["cases"], ids=[case["text"][:40] for case in CASES["cases"]])
def test_contains_sin_follows_the_shared_case_table(case):
    assert contains_sin(case["text"]) is case["refused"], case["why"]


def test_luhn_key_of_the_sin():
    assert luhn_valid("046454286") and luhn_valid("037833100")  # un NAS fictif, le CUSIP d'Apple
    assert not luhn_valid("123456789") and not luhn_valid("046454287")


@pytest.mark.parametrize("locale", ["fr", "en"])
def test_a1_sin_without_separators_is_refused_before_the_model(guarded_settings, store, tmp_path, locale):
    """Le cas de la vérification sur Bedrock réel : le garde-fou laissait passer ce NAS, et journal.md l'écrivait."""
    factory = ScriptedFactory()
    service = make_service(guarded_settings, store, factory)
    client_id = _client(service, locale=locale)
    response = service.handle({"action": "followup.reply", "client_id": client_id, "message": f"Mon NAS est {SIN}"})
    assert response["error"] == {"code": "guardrail_blocked", "message": SIN_MESSAGES[locale], "details": SIN_DETAILS}
    assert factory.requests == []
    assert SIN not in _stored_texts(tmp_path)


def test_a2_sin_without_separators_is_refused(guarded_settings, store, tmp_path):
    factory = ScriptedFactory()
    service = make_service(guarded_settings, store, factory)
    client_id = _client(service, q_existing_portfolio=True)
    response = service.handle(
        {"action": "portfolio.submit", "client_id": client_id, "text": f"100 RY.TO CELI\nMon NAS est {SIN}"}
    )
    assert response["error"] == {"code": "guardrail_blocked", "message": SIN_MESSAGES["fr"], "details": SIN_DETAILS}
    assert factory.requests == []
    assert SIN not in _stored_texts(tmp_path)


@pytest.mark.parametrize(
    "text",
    [
        "AAPL 037833100 10 actions\nMSFT 594918104 5 actions",
        "Symbole,CUSIP,Quantité\nAAPL,037833100,10",
        "Compte 723100004 chez Disnat\n130692544 parts de XEQT, valeur 250000007 $",
    ],
)
def test_a2_reads_holdings_whose_numbers_pass_the_luhn_key(guarded_settings, store, text):
    """CUSIP numériques, quantités, montants et numéros de compte fictifs passent Luhn : A2 doit les lire."""
    record = ("tool", "record_positions", {"positions": [{"raw": "10 AAPL", "ticker": "AAPL", "quantity": 10}]})
    factory = ScriptedFactory([[record], [("tool", "finish_turn", {"message": "1 position."})]])
    service = make_service(guarded_settings, store, factory)
    client_id = _client(service, q_existing_portfolio=True)
    response = service.handle({"action": "portfolio.submit", "client_id": client_id, "text": text})
    assert response["ok"], response
    assert factory.requests[0]["guardrail"] is True
