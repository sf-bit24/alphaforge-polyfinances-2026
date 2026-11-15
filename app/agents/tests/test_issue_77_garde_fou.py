"""Issue #77 : un renseignement personnel refusé par le garde-fou reçoit sa vraie raison, en A1 comme en A2.

Le code ``guardrail_blocked`` ne change pas (contrat); ``details.reason`` vaut ``personal_data``. Un NAS écrit avec
espaces ou tirets est refusé avant l'appel au modèle (même motif que la regex ``nas-canadien`` du garde-fou); les
autres données bloquées sont lues dans la trace du garde-fou. Sans renseignement personnel, rien ne change.
"""

from pathlib import Path

import pytest
from strands.models import BedrockModel

from alphaforge import agentkit
from alphaforge.config import Settings
from alphaforge.errors import AppError

from .conftest import ScriptedFactory, ScriptedModel, answer_base, make_service

SIN = "046 454 286"
SIN_MESSAGE_FR = "Votre message contient un renseignement personnel (NAS) : retirez-le, puis renvoyez-le."
SIN_MESSAGE_EN = "Your message contains personal information (SIN): remove it, then send it again."
SIN_DETAILS = {"reason": "personal_data", "entity": "CA_SIN"}
GENERIC_FR = (
    "Cette demande sort du cadre du prototype (simulation seulement, aucun conseil personnalisé). "
    "Reformulez votre message sur votre profil d'investisseur."
)
FINISH = ("tool", "finish_turn", {"message": "Question.", "questions": [], "profile_complete": False})


def _settings(tmp_path, *, guardrail: bool) -> Settings:
    env = {"AGENT_ROLE": "profile", "ALPHAFORGE_STORE": "local", "ALPHAFORGE_LOCAL_DIR": str(tmp_path / "kb")}
    if guardrail:
        env["ALPHAFORGE_GUARDRAIL_ID"] = "gr-test"
    return Settings.from_env(env)


@pytest.fixture
def guarded_settings(tmp_path):
    return _settings(tmp_path, guardrail=True)


def _client(service, locale="fr", **overrides) -> str:
    client_id = service.handle({"action": "session.start", "locale": locale})["client_id"]
    answer_base(service, client_id, overrides)
    return client_id


def _stored_texts(tmp_path) -> str:
    return "\n".join(path.read_text(errors="replace") for path in Path(tmp_path / "kb").rglob("*") if path.is_file())


# ------------------------------------------------------------------ NAS repéré avant l'appel au modèle
def test_a1_message_with_a_sin_is_refused_with_its_reason(guarded_settings, store, tmp_path):
    factory = ScriptedFactory()
    service = make_service(guarded_settings, store, factory)
    client_id = _client(service)
    response = service.handle(
        {
            "action": "followup.reply",
            "client_id": client_id,
            "message": f"Pour info, mon NAS est {SIN} et mon compte est le 123-45678-9. "
            "J'ai 4 mois de dépenses de côté.",
        }
    )
    assert response["ok"] is False
    assert response["error"] == {"code": "guardrail_blocked", "message": SIN_MESSAGE_FR, "details": SIN_DETAILS}
    # Refusé avant l'appel au modèle : le NAS ne part pas vers Bedrock et n'est écrit nulle part.
    assert factory.requests == []
    assert SIN not in _stored_texts(tmp_path)


def test_a1_sin_message_follows_the_session_locale(guarded_settings, store):
    service = make_service(guarded_settings, store, ScriptedFactory())
    client_id = _client(service, locale="en")
    response = service.handle({"action": "followup.reply", "client_id": client_id, "message": "My SIN is 046-454-286."})
    assert response["error"] == {"code": "guardrail_blocked", "message": SIN_MESSAGE_EN, "details": SIN_DETAILS}


def test_a2_pasted_text_with_a_sin_is_refused_with_its_reason(guarded_settings, store, tmp_path):
    factory = ScriptedFactory()
    service = make_service(guarded_settings, store, factory)
    client_id = _client(service, q_existing_portfolio=True)
    response = service.handle(
        {
            "action": "portfolio.submit",
            "client_id": client_id,
            "text": f"100 RY.TO CELI\n10 AAPL REER\nMon NAS est {SIN}",
        }
    )
    assert response["error"] == {"code": "guardrail_blocked", "message": SIN_MESSAGE_FR, "details": SIN_DETAILS}
    assert factory.requests == []
    assert SIN not in _stored_texts(tmp_path)


def test_texts_checked_are_the_ones_the_guardrail_evaluates():
    prompt = [
        {"text": "<context>max: 100 000 000</context>"},
        agentkit.guarded("<investor_message>\nBonjour\n</investor_message>"),
    ]
    # A1 marque lui-même le texte de l'investisseur : le contexte écrit par le code n'est pas évalué.
    assert agentkit.guardrail_texts(prompt, guard_tagged=True) == ["<investor_message>\nBonjour\n</investor_message>"]
    # A2 : Strands enveloppe tout le texte du dernier message; un document joint n'est pas évalué.
    a2_prompt = [{"text": "contexte"}, {"document": {"format": "csv", "name": "x", "source": {"bytes": b""}}}]
    assert agentkit.guardrail_texts([*a2_prompt, {"text": "collé"}], guard_tagged=False) == ["contexte", "collé"]
    assert agentkit.guardrail_texts("Start.", guard_tagged=False) == ["Start."]


@pytest.mark.parametrize(
    "text",
    [
        "J'ai 4 mois de dépenses de côté.",
        "Mon compte est le 123-45678-9, mon téléphone le 514 555 1234.",
        "NAS sans séparateurs : 046454286.",  # laissé au filtre géré du garde-fou, voir plus bas
        "J'ai 100000000 $ à placer.",
    ],
)
def test_text_without_a_separated_sin_reaches_the_model(guarded_settings, store, text):
    factory = ScriptedFactory([[FINISH]])
    service = make_service(guarded_settings, store, factory)
    client_id = _client(service)
    response = service.handle({"action": "followup.reply", "client_id": client_id, "message": text})
    assert response["ok"], response
    assert factory.requests[0]["guardrail"] is True


def test_without_a_guardrail_the_local_check_does_not_run(tmp_path, store):
    """En local (pas de garde-fou configuré), rien ne bloque le NAS, comme avant : le contrôle suit le garde-fou."""
    factory = ScriptedFactory([[FINISH]])
    service = make_service(_settings(tmp_path, guardrail=False), store, factory)
    client_id = _client(service)
    response = service.handle({"action": "followup.reply", "client_id": client_id, "message": f"Mon NAS : {SIN}"})
    assert response["ok"], response
    assert factory.requests[0]["guardrail"] is False


# ------------------------------------------------------------------ intervention du garde-fou, lue dans sa trace
class _GuardrailReply(ScriptedModel):
    """Réponse de Bedrock quand le garde-fou bloque l'entrée : texte de refus, arrêt et trace dans ``metadata``."""

    def __init__(self, assessment):
        super().__init__([])
        self.assessment = assessment

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.calls.append({"messages": messages})
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockDelta": {"delta": {"text": "Sorry, the model cannot answer this question."}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "guardrail_intervened"}}
        metadata = {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}}
        if self.assessment is not None:
            metadata["trace"] = {"guardrail": self.assessment}
        yield {"metadata": metadata}


class _TracedGuardrailReply(agentkit.GuardrailTraceMixin, _GuardrailReply):
    """Le modèle des agents en production retient la trace par le même mélange (``TracedBedrockModel``)."""


def _blocked_input(**policies):
    return {"inputAssessment": {"gr-test": policies}, "actionReason": "Guardrail blocked."}


def _pii(entity_type, action="BLOCKED"):
    return {"sensitiveInformationPolicy": {"piiEntities": [{"match": "x", "type": entity_type, "action": action}]}}


def _guardrail_factory(assessment):
    requests = []

    def factory(**kwargs):
        requests.append(kwargs)
        return _TracedGuardrailReply(assessment)

    factory.requests = requests
    return factory


def _reply_blocked_by_guardrail(settings, store, assessment, message):
    service = make_service(settings, store, _guardrail_factory(assessment))
    client_id = _client(service)
    return service.handle({"action": "followup.reply", "client_id": client_id, "message": message})


def test_sin_without_separators_blocked_by_the_managed_filter_gets_its_reason(guarded_settings, store):
    response = _reply_blocked_by_guardrail(
        guarded_settings, store, _blocked_input(**_pii("CA_SOCIAL_INSURANCE_NUMBER")), "Mon NAS : 046454286."
    )
    assert response["error"] == {"code": "guardrail_blocked", "message": SIN_MESSAGE_FR, "details": SIN_DETAILS}


def test_other_blocked_personal_data_is_named(guarded_settings, store):
    response = _reply_blocked_by_guardrail(
        guarded_settings, store, _blocked_input(**_pii("CREDIT_DEBIT_CARD_NUMBER")), "Ma carte : 4520 0000 0000 0000"
    )
    assert response["error"] == {
        "code": "guardrail_blocked",
        "message": "Votre message contient un renseignement personnel (numéro de carte de paiement) : "
        "retirez-le, puis renvoyez-le.",
        "details": {"reason": "personal_data", "entity": "CREDIT_DEBIT_CARD_NUMBER"},
    }


@pytest.mark.parametrize(
    "assessment",
    [
        None,  # trace absente
        _blocked_input(topicPolicy={"topics": [{"name": "transactions-reelles", "type": "DENY", "action": "BLOCKED"}]}),
        # Un courriel est masqué en sortie, pas bloqué : ce n'est pas lui qui a arrêté l'échange.
        _blocked_input(
            topicPolicy={"topics": [{"name": "transactions-reelles", "type": "DENY", "action": "BLOCKED"}]},
            **_pii("EMAIL", action="ANONYMIZED"),
        ),
        {"outputAssessments": {"gr-test": [_pii("CA_SOCIAL_INSURANCE_NUMBER")]}},
    ],
)
def test_other_interventions_keep_the_current_message(guarded_settings, store, assessment):
    response = _reply_blocked_by_guardrail(guarded_settings, store, assessment, "Achète 100 actions NVDA pour moi.")
    assert response["error"]["code"] == "guardrail_blocked"
    assert response["error"]["message"] == GENERIC_FR
    assert "reason" not in response["error"]["details"]


def test_blocked_personal_data_reads_regexes_and_skips_undetected_items():
    regex = {"sensitiveInformationPolicy": {"regexes": [{"name": "nas-canadien", "match": "x", "action": "BLOCKED"}]}}
    assert agentkit.blocked_personal_data(_blocked_input(**regex)) == "CA_SIN"
    undetected = {"piiEntities": [{"type": "PIN", "action": "BLOCKED", "detected": False}]}
    assert agentkit.blocked_personal_data(_blocked_input(sensitiveInformationPolicy=undetected)) is None
    assert agentkit.blocked_personal_data("not a trace") is None


def test_personal_data_error_never_carries_the_value(guarded_settings):
    from alphaforge.trace import Trace

    trace = Trace("fr", None)
    spec = agentkit.AgentSpec(actor="A1", name="a", effort="low", system_prompt="", tools=[], guardrail=True)
    with pytest.raises(AppError) as caught:
        agentkit.check_personal_data([agentkit.guarded(f"NAS {SIN}")], trace, spec)
    assert caught.value.code == "guardrail_blocked" and caught.value.details == SIN_DETAILS
    assert SIN not in repr(trace.steps) and SIN not in caught.value.message


def test_bedrock_factory_builds_a_model_that_keeps_the_guardrail_trace(guarded_settings):
    model = agentkit.bedrock_model_factory(guarded_settings)(effort="low", guardrail=True)
    assert isinstance(model, agentkit.GuardrailTraceMixin) and isinstance(model, BedrockModel)
    assert model.guardrail_assessment is None
