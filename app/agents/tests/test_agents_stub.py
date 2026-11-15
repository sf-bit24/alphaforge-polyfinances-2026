"""Chemins qui dépendent du modèle (A1, A2), avec un modèle scripté : la vraie boucle Strands, sans Bedrock."""

import base64

import pytest

from alphaforge import okf
from alphaforge.errors import AppError
from alphaforge.profile import a2 as a2_agent
from alphaforge.profile.questionnaire import default_questionnaire, numeric_choices
from alphaforge.profile.state import journal_key, portfolio_key, profile_key

from .conftest import ScriptedFactory, answer_base, make_service


def started(service, **overrides):
    client_id = service.handle({"action": "session.start", "locale": "fr"})["client_id"]
    answer_base(service, client_id, overrides)
    return client_id


def finish(message, questions=(), complete=False):
    return ("tool", "finish_turn", {"message": message, "questions": list(questions), "profile_complete": complete})


# Valeurs confirmées après les réponses de base de conftest.BASE_ANSWERS : bande gt10, montant 10 000 $.
BASE_VALUES = {"horizon.horizon_band": "gt10", "context.amount_cad": 10000}


def tranches(field, values=None, locale="fr"):
    return [
        {"value": t["value"], "label": t["label"]}
        for t in numeric_choices(default_questionnaire(), field, values or BASE_VALUES, locale)
    ]


HORIZON_QUESTION = {
    "field": "horizon.horizon_years",
    "kind": "single_choice",
    "prompt": "Dans combien d'années prévoyez-vous le premier retrait important ?",
    "options": tranches("horizon.horizon_years"),
}
LOSS_QUESTION = {
    "field": "risk_capacity.max_loss_cad",
    "kind": "single_choice",
    "prompt": "Quelle perte en dollars pourriez-vous absorber sans changer vos projets ?",
    "options": tranches("risk_capacity.max_loss_cad"),
}
APPROACH_QUESTION = {
    "field": "preferences.approach",
    "kind": "single_choice",
    "prompt": "Comment préférez-vous investir ?",
    "options": [{"value": "passive_funds", "label": "Surtout des FNB"}, {"value": "mixed", "label": "Un mélange"}],
}


def test_a1_first_turn_records_facts_and_asks_questions(settings, store):
    factory = ScriptedFactory(
        [
            [
                (
                    "tool",
                    "update_profile",
                    {
                        "updates": [
                            {
                                "field": "objective.goal_detail",
                                "value": "Une mise de fonds dans 12 ans",
                                "evidence": "mise de fonds",
                            },
                            {"field": "context.has_existing_portfolio", "value": True, "evidence": "x"},
                            {"field": "horizon.horizon_years", "value": "beaucoup", "evidence": "x"},
                        ]
                    },
                )
            ],
            [("tool", "check_completeness", {})],
            # Trois questions refusées : la confirmation de goal_detail occupe une des trois places du tour.
            [finish("Trois questions.", [HORIZON_QUESTION, LOSS_QUESTION, APPROACH_QUESTION])],
            [
                finish(
                    "Merci. Quelques précisions sur votre horizon et votre capacité.",
                    [HORIZON_QUESTION, LOSS_QUESTION],
                )
            ],
        ]
    )
    service = make_service(settings, store, factory)
    client_id = started(service)
    before = service.handle({"action": "session.resume", "client_id": client_id})["completeness"]["score"]
    response = service.handle(
        {"action": "followup.reply", "client_id": client_id, "message": "Je veux une mise de fonds dans 12 ans."}
    )
    assert response["ok"], response
    assert response["stage"] == "followups"
    assert response["message"].startswith("Merci.")
    assert [q["id"] for q in response["questions"]] == ["cf_1_1", "a1_1_1", "a1_1_2"]
    confirm = response["questions"][0]
    assert confirm["source"] == "deterministic" and confirm["kind"] == "boolean" and confirm["field"] is None
    assert confirm["prompt"] == (
        "J'ai compris : Précision de l'objectif = Une mise de fonds dans 12 ans. C'est bien ça ?"
    )
    assert confirm["dimension"] == "objective"
    assert all(q["source"] == "a1" for q in response["questions"][1:])
    tool_results = [s["outputs"]["result"] for s in response["trace"] if s["kind"] == "tool"]
    assert "at most 2 questions this turn" in tool_results[2]["reason"]
    horizon, loss = response["questions"][1], response["questions"][2]
    assert horizon["kind"] == loss["kind"] == "single_choice"
    assert [o["value"] for o in horizon["options"]] == ["10to15", "15to20", "20to30", "30plus"]
    assert loss["options"][1] == {"value": "2_5to5pct", "label": "De 250 $ à moins de 500 $ (2,5 à 5 %)"}
    assert (horizon["min"], horizon["unit"]) == (None, None)
    # La table des tranches reste hors de la question envoyée.
    stored = okf.parse(store.get(profile_key(client_id)).text).data
    assert stored["pending_choices"]["a1_1_2"]["2_5to5pct"] == 250
    assert all(set(o) == {"value", "label"} for q in stored["pending_questions"] for o in q["options"])
    assert stored["pending_confirmations"] == {"cf_1_1": "objective.goal_detail"}
    # La valeur tirée du message attend sa confirmation : hors de ProfileView et de la complétude.
    assert stored["facts"]["objective.goal_detail"] == {
        "value": "Une mise de fonds dans 12 ans",
        "provenance": "a1:1",
        "at": stored["facts"]["objective.goal_detail"]["at"],
        "confirmed": False,
    }
    assert not any(f["field"] == "objective.goal_detail" for f in response["profile"]["facts"])
    assert response["completeness"]["score"] == before
    assert {"dimension": "objective", "field": "goal_detail", "label": "Précision de l'objectif"} in response[
        "completeness"
    ]["missing"]
    assert not any(f["field"] == "horizon.horizon_years" for f in response["profile"]["facts"])
    rejected = tool_results[0]["results"]
    assert rejected[0]["status"] == "ok" and rejected[0]["to_confirm"] is True
    assert [r["status"] for r in rejected[1:]] == ["error", "error"]
    assert factory.requests == [{"effort": "low", "guardrail": False, "max_tokens": 8000}]
    model = factory.models[0]
    assert model.calls[0]["tools"] == [
        "update_profile",
        "check_completeness",
        "search_general_knowledge",
        "finish_turn",
    ]
    assert "<investor_message>" in model.calls[0]["messages"][0]["content"][0]["text"]
    assert len(model.calls) == 4  # l'outil finish_turn accepté arrête la boucle sans nouvel appel du modèle
    kinds = [s["kind"] for s in response["trace"]]
    assert "model" in kinds and "tool" in kinds and "agent" in kinds
    entries = okf.parse(store.get(journal_key(client_id)).text).data["entries"]
    message = [e for e in entries if e["kind"] == "message"]
    assert message == [
        {
            "at": message[0]["at"],
            "kind": "message",
            "provenance": "a1:1",
            "text": "Je veux une mise de fonds dans 12 ans.",
            "locale": "fr",
        }
    ]

    # Réponses aux questions d'A1 : validées par le code et écrites avec la provenance du tour qui les a posées.
    # « Oui » confirme la valeur tirée du message.
    factory.scripts.append([[finish("Le profil est complet.", complete=True)]])
    answered = service.handle(
        {
            "action": "followup.reply",
            "client_id": client_id,
            "answers": [
                {"question_id": "cf_1_1", "value": True},
                {"question_id": "a1_1_1", "value": "10to15"},
                {"question_id": "a1_1_2", "value": "10to20pct"},
            ],
        }
    )
    assert answered["ok"], answered
    assert answered["stage"] == "complete" and answered["questions"] == []
    assert answered["completeness"]["ready"] is True
    provenances = {f["field"]: f["provenance"] for f in answered["profile"]["facts"]}
    assert provenances["horizon.horizon_years"] == "a1:1" and provenances["objective.goal_detail"] == "a1:1"
    values = {f["field"]: f["value"] for f in answered["profile"]["facts"]}
    assert values["horizon.horizon_years"] == 10 and values["risk_capacity.max_loss_cad"] == 1000
    entries = okf.parse(store.get(journal_key(client_id)).text).data["entries"]
    loss_entry = next(e for e in entries if e.get("question_id") == "a1_1_2")
    assert loss_entry["value"] == 1000 and loss_entry["option"] == "10to20pct"
    confirmed = next(e for e in entries if e.get("question_id") == "cf_1_1")
    assert confirmed["field"] == "objective.goal_detail" and confirmed["value"] == "Une mise de fonds dans 12 ans"
    stored = okf.parse(store.get(profile_key(client_id)).text).data
    assert "confirmed" not in stored["facts"]["objective.goal_detail"]
    assert stored["pending_confirmations"] == {}
    assert okf.parse(store.get(profile_key(client_id)).text).data["pending_choices"] == {}
    context = factory.models[1].calls[0]["messages"][0]["content"][0]["text"]
    assert '"new_answers_this_turn"' in context and "a1_1_2" in context


def test_a1_answers_are_validated_against_the_pending_question(settings, store):
    factory = ScriptedFactory([[finish("Question.", [HORIZON_QUESTION])]])
    service = make_service(settings, store, factory)
    client_id = started(service)
    assert service.handle({"action": "followup.reply", "client_id": client_id})["ok"]
    wrong = service.handle(
        {"action": "followup.reply", "client_id": client_id, "answers": [{"question_id": "a1_1_1", "value": "3to5"}]}
    )
    assert wrong["error"]["code"] == "invalid_answer" and wrong["error"]["details"]["reason"] == "not_in_options"
    number = service.handle(
        {"action": "followup.reply", "client_id": client_id, "answers": [{"question_id": "a1_1_1", "value": 12}]}
    )
    assert number["error"]["details"]["reason"] == "not_a_string"
    unknown = service.handle(
        {"action": "followup.reply", "client_id": client_id, "answers": [{"question_id": "a1_9_9", "value": 1}]}
    )
    assert unknown["error"]["code"] == "invalid_answer"


def test_a1_invalid_questions_are_sent_back_to_the_model(settings, store):
    free_number = {"field": "horizon.horizon_years", "kind": "number", "prompt": "Combien d'années ?"}
    invented = {
        "field": "risk_capacity.max_loss_cad",
        "kind": "single_choice",
        "prompt": "Quelle perte ?",
        "options": [{"value": "lt2_5pct", "label": "Moins de 250 $"}, {"value": "lt7k", "label": "Moins de 7 000 $"}],
    }
    factory = ScriptedFactory([[finish("x", [free_number, invented])], [finish("Merci.", [HORIZON_QUESTION])]])
    service = make_service(settings, store, factory)
    client_id = started(service)
    response = service.handle({"action": "followup.reply", "client_id": client_id})
    assert response["ok"] and response["questions"][0]["kind"] == "single_choice"
    tool_steps = [s for s in response["trace"] if s["kind"] == "tool"]
    refused = tool_steps[0]["outputs"]["result"]
    assert refused["status"] == "error" and [e["question"] for e in refused["errors"]] == [1, 2]
    assert "kind number is not allowed" in refused["errors"][0]["reason"]
    assert "'lt7k' is not a tranche" in refused["errors"][1]["reason"]


def update(field, value, evidence):
    return ("tool", "update_profile", {"updates": [{"field": field, "value": value, "evidence": evidence}]})


MONTHLY = "constraints.monthly_contribution_cad"


def test_free_text_value_is_kept_only_after_yes(settings, store):
    factory = ScriptedFactory(
        [[update(MONTHLY, 3000, "3 000 $ par mois")], [finish("Merci.", [APPROACH_QUESTION])]],
        [[update(MONTHLY, 500, "500 $")], [finish("Noté.", [LOSS_QUESTION])]],
        [[finish("Merci.", [HORIZON_QUESTION])]],
    )
    service = make_service(settings, store, factory)
    client_id = started(service)
    first = service.handle(
        {"action": "followup.reply", "client_id": client_id, "message": "Je compte ajouter 3 000 $ par mois."}
    )
    assert [q["id"] for q in first["questions"]] == ["cf_1_1", "a1_1_1"]
    assert first["questions"][0]["prompt"] == "J'ai compris : Ajout mensuel prévu = 3\u202f000 $. C'est bien ça ?"
    assert MONTHLY not in first["profile"]["dimensions"]["constraints"]["fields"]

    # « Non » : la valeur est retirée, le champ redevient manquant et le journal garde la valeur précédente.
    second = service.handle(
        {
            "action": "followup.reply",
            "client_id": client_id,
            "message": "Plutôt 500 $.",
            "answers": [{"question_id": "cf_1_1", "value": False}],
        }
    )
    assert second["ok"], second
    entries = okf.parse(store.get(journal_key(client_id)).text).data["entries"]
    removed = next(e for e in entries if e.get("question_id") == "cf_1_1")
    assert removed == {**removed, "field": MONTHLY, "value": None, "previous": 3000, "provenance": "a1:1"}
    stored = okf.parse(store.get(profile_key(client_id)).text).data
    assert stored["facts"][MONTHLY] == {**stored["facts"][MONTHLY], "value": 500, "confirmed": False}
    assert [q["id"] for q in second["questions"]] == ["cf_2_1", "a1_2_1"]
    context = factory.models[1].calls[0]["messages"][0]["content"][0]["text"]
    assert '"kind": "confirmation"' in context

    # « Oui » : la valeur entre dans le profil, sans écrire le booléen dans le champ.
    third = service.handle(
        {"action": "followup.reply", "client_id": client_id, "answers": [{"question_id": "cf_2_1", "value": True}]}
    )
    facts = {f["field"]: f for f in third["profile"]["facts"]}
    assert facts[MONTHLY]["value"] == 500 and facts[MONTHLY]["provenance"] == "a1:2"
    assert third["profile"]["dimensions"]["constraints"]["fields"]["monthly_contribution_cad"] == 500
    assert [q["id"] for q in third["questions"]] == ["a1_3_1"]


def test_third_open_question_of_the_session_is_refused(settings, store):
    goal = {"field": "objective.goal_detail", "kind": "text", "prompt": "Que voulez-vous accomplir ?"}
    explore = {"kind": "text", "prompt": "Qu'aimeriez-vous ajouter ?", "dimension": "context"}
    factory = ScriptedFactory(
        [[finish("Deux questions ouvertes.", [goal, explore])]],
        [[finish("Encore une ?", [explore])], [finish("Plutôt un choix.", [APPROACH_QUESTION])]],
    )
    service = make_service(settings, store, factory)
    client_id = started(service)
    first = service.handle({"action": "followup.reply", "client_id": client_id})
    assert [q["kind"] for q in first["questions"]] == ["text", "text"]
    second = service.handle({"action": "followup.reply", "client_id": client_id})
    assert second["ok"] and [q["kind"] for q in second["questions"]] == ["single_choice"]
    refused = [s for s in second["trace"] if s["kind"] == "tool"][0]["outputs"]["result"]
    assert "maximum is 2" in refused["errors"][0]["reason"]
    counts = okf.parse(store.get(profile_key(client_id)).text).data["followup_counts"]
    assert counts == {"generated": 3, "open": 2}


def test_a1_cannot_declare_completion_below_the_threshold(settings, store):
    factory = ScriptedFactory([[finish("Fini.", complete=True)], [finish("Encore une question.", [LOSS_QUESTION])]])
    service = make_service(settings, store, factory)
    client_id = started(service)
    response = service.handle({"action": "followup.reply", "client_id": client_id})
    assert response["ok"] and response["stage"] == "followups" and len(response["questions"]) == 1


def test_a1_fallback_when_finish_turn_is_never_called(settings, store):
    factory = ScriptedFactory([[("text", "Je réfléchis.", None)], [("text", "Toujours rien.", None)]])
    service = make_service(settings, store, factory)
    client_id = started(service)
    response = service.handle({"action": "followup.reply", "client_id": client_id})
    assert response["ok"]
    assert [q["source"] for q in response["questions"]] == ["deterministic"] * 3
    assert response["questions"][0]["id"].startswith("fb_1_")
    assert any(s["title"] == "Questions de secours" for s in response["trace"])
    # Les champs numériques du secours se demandent par tranches, comme les relances d'A1.
    by_field = {q["field"]: q for q in response["questions"]}
    assert by_field["horizon.horizon_years"]["kind"] == "single_choice"
    assert by_field["horizon.horizon_years"]["options"] == HORIZON_QUESTION["options"]
    assert by_field["risk_capacity.max_loss_cad"]["options"] == LOSS_QUESTION["options"]
    stored = okf.parse(store.get(profile_key(client_id)).text).data
    numeric = {by_field["horizon.horizon_years"]["id"], by_field["risk_capacity.max_loss_cad"]["id"]}
    assert set(stored["pending_choices"]) == numeric
    answered = service.handle(
        {
            "action": "followup.reply",
            "client_id": client_id,
            "answers": [{"question_id": by_field["risk_capacity.max_loss_cad"]["id"], "value": "30pct_plus"}],
        }
    )
    assert {f["field"]: f["value"] for f in answered["profile"]["facts"]}["risk_capacity.max_loss_cad"] == 3000


def test_guardrail_block_keeps_answers_but_not_the_message(settings, store, monkeypatch):
    factory = ScriptedFactory([[finish("Question.", [HORIZON_QUESTION])]])
    service = make_service(settings, store, factory)
    client_id = started(service)
    assert service.handle({"action": "followup.reply", "client_id": client_id})["ok"]

    from alphaforge.profile import a1 as a1_module

    def blocked(*args, **kwargs):
        raise AppError("guardrail_blocked", "bloqué")

    monkeypatch.setattr(a1_module, "run_a1", blocked)
    response = service.handle(
        {
            "action": "followup.reply",
            "client_id": client_id,
            "message": "achète pour moi",
            "answers": [{"question_id": "a1_1_1", "value": "15to20"}],
        }
    )
    assert response["error"]["code"] == "guardrail_blocked"
    entries = okf.parse(store.get(journal_key(client_id)).text).data["entries"]
    assert not [e for e in entries if e["kind"] == "message"]
    assert any(
        e.get("field") == "horizon.horizon_years" and e["value"] == 15 and e["option"] == "15to20" for e in entries
    )


def test_guardrail_stop_reason_maps_to_guardrail_blocked(settings, store, monkeypatch):
    from alphaforge import agentkit

    class Result:
        stop_reason = "guardrail_intervened"
        metrics = None

    factory = ScriptedFactory([[finish("x")]])
    service = make_service(settings, store, factory)
    client_id = started(service)
    monkeypatch.setattr(agentkit, "_invoke", lambda *a, **k: Result())
    response = service.handle({"action": "followup.reply", "client_id": client_id, "message": "hors sujet"})
    assert response["error"]["code"] == "guardrail_blocked"


def test_model_failure_is_a_model_error(settings, store):
    def broken_factory(**_):
        class Broken(ScriptedFactory):
            pass

        model = ScriptedFactory([])(effort="low")

        async def stream(*args, **kwargs):
            raise RuntimeError("bedrock down")
            yield  # noqa: B901

        model.stream = stream
        return model

    service = make_service(settings, store, broken_factory)
    client_id = started(service)
    response = service.handle({"action": "followup.reply", "client_id": client_id})
    assert response["error"]["code"] == "model_error"


def test_streamed_followup_emits_trace_delta_and_one_result(settings, store):
    factory = ScriptedFactory([[finish("Bonjour, deux questions.", [HORIZON_QUESTION, LOSS_QUESTION])]])
    service = make_service(settings, store, factory)
    client_id = started(service)
    events = list(service.handle({"action": "followup.reply", "client_id": client_id, "stream": True}))
    types = [e["type"] for e in events]
    assert types.count("result") == 1 and types[-1] == "result" and "error" not in types
    assert {"type": "delta", "text": "Bonjour, deux questions."} in events
    assert types.index("delta") < types.index("result")
    assert sum(t == "trace" for t in types) == len(events[-1]["result"]["trace"])


# ---------------------------------------------------------------------- A2
def test_a2_submit_then_confirm(settings, store):
    record = (
        "tool",
        "record_positions",
        {
            "positions": [
                {"raw": "100 RY.TO CELI", "ticker": "RY.TO", "quantity": 100, "account_type": "tfsa"},
                {"raw": "10 AAPL REER", "ticker": "AAPL", "quantity": 10, "account_type": "rrsp"},
            ],
            "unparsed": [{"raw": "fonds maison XYZ", "reason": "titre introuvable"}],
        },
    )
    factory = ScriptedFactory([[record], [("tool", "finish_turn", {"message": "J'ai reconnu 2 positions."})]])
    service = make_service(settings, store, factory)
    client_id = started(service, q_existing_portfolio=True, q_accounts=["unknown"])
    csv_file = base64.b64encode(b"ticker,qty\nRY.TO,100\nAAPL,10\n").decode()
    response = service.handle(
        {
            "action": "portfolio.submit",
            "client_id": client_id,
            "text": "Voir fichier",
            "files": [{"name": "mon portefeuille.csv", "media_type": "text/csv", "data_base64": csv_file}],
        }
    )
    assert response["ok"], response
    assert response["stage"] == "portfolio_review" and response["questions"] == []
    assert response["message"] == "J'ai reconnu 2 positions."
    view = response["portfolio"]
    assert view["status"] == "draft" and len(view["positions"]) == 2
    assert view["unresolved"] == [{"raw": "fonds maison XYZ", "reason": "titre introuvable"}]
    assert "unvalued_positions" in view["exposures"]["flags"]
    assert factory.requests[0]["effort"] == "medium"
    blocks = factory.models[0].calls[0]["messages"][0]["content"]
    document = next(b for b in blocks if "document" in b)["document"]
    assert document["format"] == "csv" and document["name"] == "mon portefeuille"
    assert okf.parse(store.get(portfolio_key(client_id)).text).frontmatter["status"] == "draft"

    corrected = [dict(p) for p in view["positions"]]
    corrected[0]["quantity"] = 50
    confirmed = service.handle({"action": "portfolio.confirm", "client_id": client_id, "positions": corrected})
    assert confirmed["ok"], confirmed
    assert confirmed["stage"] == "followups"
    assert confirmed["portfolio"]["status"] == "confirmed"
    assert confirmed["portfolio"]["positions"][0]["quantity"] == 50
    facts = {f["field"]: f for f in confirmed["profile"]["facts"]}
    assert facts["context.existing_portfolio_value_cad"]["provenance"] == "a2:1"
    assert (
        facts["context.existing_portfolio_value_cad"]["value"] == confirmed["portfolio"]["exposures"]["total_value_cad"]
    )
    assert facts["constraints.account_types"]["value"] == ["unknown"]  # la réponse de base n'est pas écrasée
    doc = okf.parse(store.get(portfolio_key(client_id)).text)
    assert doc.frontmatter["status"] == "stable" and okf.validate(doc) == []
    assert (
        service.handle({"action": "portfolio.confirm", "client_id": client_id, "positions": corrected})["error"]["code"]
        == "conflict"
    )


def test_a2_requires_record_positions(settings, store):
    factory = ScriptedFactory([[("text", "rien", None)], [("text", "toujours rien", None)]])
    service = make_service(settings, store, factory)
    client_id = started(service, q_existing_portfolio=True)
    response = service.handle({"action": "portfolio.submit", "client_id": client_id, "text": "100 RY"})
    assert response["error"]["code"] == "model_error"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_prepare_input_formats_and_limits():
    pdf = {"name": "relevé (nov).pdf", "media_type": "application/pdf", "data_base64": b64(b"%PDF-1.7 test")}
    png = {"name": "capture.png", "media_type": "image/png", "data_base64": b64(b"\x89PNG\r\n\x1a\n" + b"0" * 10)}
    js = {"name": "positions.json", "media_type": "application/json", "data_base64": b64(b'{"RY": 100}')}
    xlsx = {"name": "p.xlsx", "media_type": "application/octet-stream", "data_base64": b64(b"PK\x03\x04data")}
    prepared = a2_agent.prepare_input("100 RY", [pdf, png, js, xlsx], "fr")
    kinds = [next(iter(block)) for block in prepared.blocks]
    assert kinds == ["document", "image", "document", "text"]
    assert prepared.blocks[0]["document"]["name"] == "relev (nov)"
    assert prepared.blocks[2]["document"]["format"] == "xlsx"
    assert '<file name="positions.json">' in prepared.blocks[3]["text"]
    assert "<pasted_text>" in prepared.blocks[3]["text"]
    assert [f["passed_as"] for f in prepared.files] == ["document/pdf", "image/png", "text", "document/xlsx"]


@pytest.mark.parametrize(
    ("text", "files", "code"),
    [
        (None, None, "invalid_answer"),
        ("", [], "invalid_answer"),
        (None, [{"name": "a"}], "bad_request"),
        (None, [{"name": "a", "media_type": "text/plain", "data_base64": "%%%"}], "bad_request"),
        (
            None,
            [{"name": f"f{i}", "media_type": "text/plain", "data_base64": "YQ=="} for i in range(6)],
            "invalid_answer",
        ),
        (
            None,
            [
                {
                    "name": "big.png",
                    "media_type": "image/png",
                    "data_base64": b64(b"\x89PNG\r\n\x1a\n" + b"0" * (4 * 1024 * 1024)),
                }
            ],
            "invalid_answer",
        ),
        (
            None,
            [{"name": "bin.dat", "media_type": "application/octet-stream", "data_base64": b64(bytes(range(256)))}],
            "invalid_answer",
        ),
    ],
)
def test_prepare_input_rejections(text, files, code):
    with pytest.raises(AppError) as exc:
        a2_agent.prepare_input(text, files, "fr")
    assert exc.value.code == code


def test_document_names_are_sanitized_and_unique():
    used = set()
    assert a2_agent.sanitize_document_name("état_2026.pdf", used, 1) == "tat 2026"
    assert a2_agent.sanitize_document_name("état_2026.csv", used, 2) == "tat 2026 2"
    assert a2_agent.sanitize_document_name("", used, 3) == "document 3"
    assert a2_agent.sanitize_document_name("a  b--(c)[d].md", used, 4) == "a b--(c)[d]"
