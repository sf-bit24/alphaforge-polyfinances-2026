"""Suite de l'issue #77 : un refus ne rouvre pas un profil complet.

Un message bloqué (ou un modèle indisponible) sur un profil complet faisait passer l'étape de ``complete`` à
``followups``, et cette étape était enregistrée (``service._ask_followups``). Sans réponse validée, rien n'est
enregistré, étape comprise; avec des réponses validées, elles restent gardées
(``test_agents_stub.test_guardrail_block_keeps_answers_but_not_the_message``).
"""

import pytest

from alphaforge.config import Settings
from alphaforge.profile.state import journal_key, profile_key

from .conftest import ScriptedFactory, ScriptedModel, answer_base, make_service
from .test_agents_stub import HORIZON_QUESTION, LOSS_QUESTION, finish

SIN = "046454286"


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


def _client(service) -> str:
    client_id = service.handle({"action": "session.start", "locale": "fr"})["client_id"]
    answer_base(service, client_id)
    return client_id


def _complete_profile(service, factory) -> str:
    client_id = _client(service)
    factory.scripts.append([[finish("Deux questions.", [HORIZON_QUESTION, LOSS_QUESTION])]])
    assert service.handle({"action": "followup.reply", "client_id": client_id})["ok"]
    factory.scripts.append([[finish("Le profil est complet.", complete=True)]])
    answers = [{"question_id": "a1_1_1", "value": "10to15"}, {"question_id": "a1_1_2", "value": "10to20pct"}]
    done = service.handle({"action": "followup.reply", "client_id": client_id, "answers": answers})
    assert done["ok"] and done["stage"] == "complete", done
    return client_id


def _documents(store, client_id) -> tuple[str, str]:
    return store.get(profile_key(client_id)).text, store.get(journal_key(client_id)).text


class _UnavailableModel(ScriptedModel):
    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        raise RuntimeError("Bedrock indisponible")
        yield  # pragma: no cover


@pytest.mark.parametrize(
    ("message", "code"),
    [(f"Mon NAS est {SIN}", "guardrail_blocked"), ("Mon NAS est 046 454 286", "guardrail_blocked")],
)
def test_a_blocked_message_leaves_a_complete_profile_as_it_was(guarded_settings, store, message, code):
    factory = ScriptedFactory()
    service = make_service(guarded_settings, store, factory)
    client_id = _complete_profile(service, factory)
    before = _documents(store, client_id)
    response = service.handle({"action": "followup.reply", "client_id": client_id, "message": message})
    assert response["error"]["code"] == code
    assert _documents(store, client_id) == before
    assert service.handle({"action": "session.resume", "client_id": client_id})["stage"] == "complete"


def test_an_unavailable_model_leaves_a_complete_profile_as_it_was(guarded_settings, store):
    factory = ScriptedFactory()
    service = make_service(guarded_settings, store, factory)
    client_id = _complete_profile(service, factory)
    before = _documents(store, client_id)

    def unavailable(**kwargs):
        factory.requests.append(kwargs)
        return _UnavailableModel([])

    service.model_factory = unavailable
    response = service.handle({"action": "followup.reply", "client_id": client_id, "message": "J'ai changé d'emploi."})
    assert response["error"]["code"] == "model_error"
    assert _documents(store, client_id) == before
    assert service.handle({"action": "session.resume", "client_id": client_id})["stage"] == "complete"
