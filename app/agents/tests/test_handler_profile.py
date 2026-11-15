"""Parcours de bout en bout des actions déterministes du runtime profile, sur le magasin local."""

import json
import uuid

import pytest

from alphaforge import okf
from alphaforge.profile.state import journal_key, portfolio_key, profile_key

from .conftest import BASE_ANSWERS, answer_base, make_service

QUESTION_KEYS = {"id", "source", "dimension", "kind", "prompt", "help", "options", "min", "max", "unit", "required"}
STATE_KEYS = {
    "ok",
    "release",
    "client_id",
    "locale",
    "stage",
    "message",
    "questions",
    "profile",
    "completeness",
    "portfolio",
    "trace",
}
TRACE_KEYS = {"id", "at", "kind", "actor", "title", "detail", "inputs", "outputs", "sources", "duration_ms"}


@pytest.fixture
def service(settings, store):
    return make_service(settings, store)


def start(service, locale="fr", **extra):
    response = service.handle({"action": "session.start", "locale": locale, **extra})
    assert response["ok"], response
    return response


def test_health_and_unknown_actions(service):
    assert service.handle({"action": "health"}) == {"ok": True, "release": "test1234", "role": "profile", "env": "test"}
    unknown = service.handle({"action": "nope"})
    assert unknown["ok"] is False and unknown["error"]["code"] == "unknown_action"
    assert service.handle({})["error"]["code"] == "bad_request"
    assert service.handle(["not", "an", "object"])["error"]["code"] == "bad_request"


def test_session_start_creates_the_client_base(service, store):
    response = start(service)
    assert set(response) == STATE_KEYS
    assert response["stage"] == "base_questions" and response["locale"] == "fr"
    assert len(response["questions"]) == 1
    question = response["questions"][0]
    assert QUESTION_KEYS <= set(question) and question["id"] == "q_kn_invest_freq"
    assert question["source"] == "deterministic" and question["dimension"] == "knowledge"
    assert response["completeness"]["score"] == 0 and response["completeness"]["threshold"] == 0.7
    assert response["portfolio"] is None and response["message"] is None
    for step in response["trace"]:
        assert set(step) == TRACE_KEYS
    client_id = response["client_id"]
    assert uuid.UUID(client_id).version == 4
    for key in (profile_key(client_id), journal_key(client_id), f"clients/{client_id}/index.md"):
        doc = okf.parse(store.get(key).text)
        assert okf.validate(doc) == [], key
        assert doc.frontmatter["sensitivity"] == "client"
    traces = store.list(f"clients/{client_id}/traces/")
    assert len(traces) == 1 and traces[0].key.endswith("-session.start.json")
    journal = okf.parse(store.get(journal_key(client_id)).text).data["entries"]
    assert journal == [
        {
            "at": journal[0]["at"],
            "kind": "stage",
            "provenance": "settings",
            "value": "base_questions",
            "previous": None,
            "note": "base du client créée",
        }
    ]


def test_session_start_with_existing_client_changes_nothing(service, store):
    client_id = start(service)["client_id"]
    before = store.get(profile_key(client_id)).etag
    again = start(service, locale="en", client_id=client_id)
    assert again["client_id"] == client_id and again["locale"] == "en"
    assert again["questions"][0]["prompt"].startswith("Over the last three years")
    assert store.get(profile_key(client_id)).etag == before


def test_session_start_with_new_client_id_and_bad_inputs(service):
    client_id = str(uuid.uuid4())
    assert start(service, client_id=client_id)["client_id"] == client_id
    assert service.handle({"action": "session.start", "locale": "de"})["error"]["code"] == "bad_request"
    assert service.handle({"action": "session.start", "client_id": "123"})["error"]["code"] == "bad_request"


def test_base_answers_through_to_followups(service, store):
    client_id = start(service)["client_id"]
    seen = []
    response = service.handle({"action": "session.resume", "client_id": client_id})
    while response["stage"] == "base_questions":
        question = response["questions"][0]
        seen.append(question["id"])
        response = service.handle(
            {
                "action": "base.answer",
                "client_id": client_id,
                "question_id": question["id"],
                "value": BASE_ANSWERS[question["id"]],
            }
        )
        assert response["ok"], response
        assert response["message"] is None
    assert seen[:4] == ["q_kn_invest_freq", "q_kn_news", "q_kn_products", "q_kn_self"]
    assert seen[-1] == "q_existing_portfolio"
    assert "q_exclusions" in seen  # q_esg = 4 ouvre la branche des exclusions
    assert "q_project_type" not in seen and "q_withdrawal_pct" not in seen
    assert response["stage"] == "followups" and response["questions"] == []
    profile = response["profile"]
    assert profile["knowledge_level"] == "intermediate"
    assert profile["effective_risk"] == "medium_high"
    assert profile["dimensions"]["horizon"] == {
        "status": "partial",
        "summary": "10 ans et plus",
        "fields": {"horizon_band": "gt10"},
    }
    assert profile["dimensions"]["risk_tolerance"]["summary"] == "Moyenne à élevée"
    fact = next(f for f in profile["facts"] if f["field"] == "horizon.horizon_band")
    assert fact["provenance"] == "base:q_horizon" and fact["value"] == "gt10"
    completeness = response["completeness"]
    assert 0.6 < completeness["score"] < 0.7 and completeness["ready"] is False
    assert completeness["displayed"] == completeness["score"]
    assert {"dimension": "risk_capacity", "field": "max_loss_cad", "label": "Perte admissible"} in completeness[
        "missing"
    ]
    titles = [step["title"] for step in response["trace"]]
    assert "Changement d'étape" in titles and "Risque effectif calculé : min(tolérance, capacité)" in titles
    entries = okf.parse(store.get(journal_key(client_id)).text).data["entries"]
    answers = [e for e in entries if e["kind"] == "answer"]
    assert len(answers) == len(seen)
    assert all(set(e) >= {"at", "kind", "provenance", "field", "value", "question_id"} for e in answers)
    stage = [e for e in entries if e["kind"] == "stage"][-1]
    assert stage["value"] == "followups" and stage["previous"] == "base_questions"
    assert stage["provenance"] == "base:q_existing_portfolio"


def test_existing_portfolio_branch_and_skip(service):
    client_id = start(service)["client_id"]
    response = answer_base(service, client_id, {"q_existing_portfolio": True})
    assert response["stage"] == "existing_portfolio" and response["questions"] == []
    skipped = service.handle({"action": "portfolio.skip", "client_id": client_id})
    assert skipped["ok"] and skipped["stage"] == "followups" and skipped["portfolio"] is None
    again = service.handle({"action": "portfolio.skip", "client_id": client_id})
    assert again["error"]["code"] == "conflict"


def test_invalid_answers_are_rejected_with_reasons(service):
    client_id = start(service)["client_id"]
    wrong = service.handle(
        {"action": "base.answer", "client_id": client_id, "question_id": "q_kn_invest_freq", "value": "often"}
    )
    assert wrong["error"]["code"] == "invalid_answer"
    assert wrong["error"]["details"]["reason"] == "not_in_options"
    unknown = service.handle({"action": "base.answer", "client_id": client_id, "question_id": "q_nope", "value": 1})
    assert unknown["error"]["code"] == "invalid_answer"
    not_applicable = service.handle(
        {"action": "base.answer", "client_id": client_id, "question_id": "q_project_type", "value": "home"}
    )
    assert not_applicable["error"]["code"] == "invalid_answer"
    missing_value = service.handle({"action": "base.answer", "client_id": client_id, "question_id": "q_kn_news"})
    assert missing_value["error"]["code"] == "bad_request"
    missing_client = service.handle(
        {"action": "base.answer", "client_id": str(uuid.uuid4()), "question_id": "q_kn_news", "value": "daily"}
    )
    assert missing_client["error"]["code"] == "not_found"


def test_correcting_an_answer_prunes_an_abandoned_branch(service):
    client_id = start(service)["client_id"]
    for question_id, value in [
        ("q_kn_invest_freq", "never"),
        ("q_kn_news", "rarely"),
        ("q_kn_products", ["none"]),
        ("q_kn_self", "beginner"),
        ("q_goal", "project"),
        ("q_project_type", "home"),
    ]:
        assert service.handle(
            {"action": "base.answer", "client_id": client_id, "question_id": question_id, "value": value}
        )["ok"]
    response = service.handle(
        {"action": "base.answer", "client_id": client_id, "question_id": "q_goal", "value": "growth"}
    )
    fields = {f["field"] for f in response["profile"]["facts"]}
    assert "objective.project_type" not in fields
    assert response["questions"][0]["id"] == "q_horizon"


def test_followup_reply_requires_followups_stage(service):
    client_id = start(service)["client_id"]
    response = service.handle({"action": "followup.reply", "client_id": client_id, "message": "bonjour"})
    assert response["error"]["code"] == "conflict"
    submit = service.handle({"action": "portfolio.submit", "client_id": client_id, "text": "100 RY"})
    assert submit["error"]["code"] == "conflict"


def test_stop_is_refused_below_the_threshold(service):
    client_id = start(service)["client_id"]
    answer_base(service, client_id)
    response = service.handle({"action": "followup.reply", "client_id": client_id, "stop": True})
    assert response["error"]["code"] == "conflict"
    assert response["error"]["details"]["threshold"] == 0.7


def test_settings_update_language_and_knowledge_level(service, store):
    client_id = start(service)["client_id"]
    answer_base(service, client_id)
    response = service.handle(
        {"action": "settings.update", "client_id": client_id, "locale": "en", "knowledge_level": "advanced"}
    )
    assert response["ok"] and response["locale"] == "en"
    assert response["profile"]["knowledge_level"] == "advanced"
    assert response["profile"]["dimensions"]["horizon"]["summary"] == "10 years or more"
    fact = next(f for f in response["profile"]["facts"] if f["field"] == "knowledge.level")
    assert fact["provenance"] == "settings"
    cleared = service.handle({"action": "settings.update", "client_id": client_id, "knowledge_level": None})
    assert cleared["profile"]["knowledge_level"] == "intermediate"
    bad = service.handle({"action": "settings.update", "client_id": client_id, "knowledge_level": "expert"})
    assert bad["error"]["code"] == "bad_request"
    empty = service.handle({"action": "settings.update", "client_id": client_id})
    assert empty["error"]["code"] == "bad_request"


def test_resume_and_profile_get_do_not_write(service, store):
    client_id = start(service)["client_id"]
    answer_base(service, client_id)
    etag = store.get(profile_key(client_id)).etag
    traces = len(store.list(f"clients/{client_id}/traces/"))
    resumed = service.handle({"action": "session.resume", "client_id": client_id, "locale": "en"})
    assert resumed["ok"] and resumed["locale"] == "en" and resumed["profile"]["documents"] == []
    full = service.handle({"action": "profile.get", "client_id": client_id})
    keys = {doc["key"] for doc in full["profile"]["documents"]}
    assert {profile_key(client_id), journal_key(client_id), f"clients/{client_id}/index.md"} <= keys
    assert all(doc["title"] for doc in full["profile"]["documents"])
    assert store.get(profile_key(client_id)).etag == etag
    assert len(store.list(f"clients/{client_id}/traces/")) == traces


def test_kb_list_and_get(service, store):
    store.put_text(
        "general/methodologie/test.md",
        okf.render(
            okf.new_doc(
                type="Methodology",
                title="Test",
                description="Doc de test",
                tags=["t"],
                owners=["x"],
                sensitivity="public",
                generated_by="human",
                at="2026-11-14T00:00:00Z",
            )
        ),
    )
    client_id = start(service)["client_id"]
    general = service.handle({"action": "kb.list", "prefix": "general/"})
    assert general["ok"] and general["items"][0]["key"] == "general/methodologie/test.md"
    assert set(general["items"][0]) == {"key", "title", "type", "description", "updated_at"}
    mine = service.handle({"action": "kb.list", "prefix": f"clients/{client_id}/"})
    assert {item["type"] for item in mine["items"]} == {"Investor Profile", "Profile Journal", "Index"}
    assert service.handle({"action": "kb.list", "prefix": "staging/"})["error"]["code"] == "bad_request"
    assert service.handle({"action": "kb.list", "prefix": "clients/abc/"})["error"]["code"] == "bad_request"
    doc = service.handle({"action": "kb.get", "key": "general/methodologie/test.md"})
    assert doc["ok"] and doc["content"].startswith("---\ntype: Methodology")
    key = profile_key(client_id)
    assert service.handle({"action": "kb.get", "key": key})["error"]["code"] == "bad_request"
    other = str(uuid.uuid4())
    assert service.handle({"action": "kb.get", "key": key, "client_id": other})["error"]["code"] == "not_found"
    own = service.handle({"action": "kb.get", "key": key, "client_id": client_id})
    assert own["ok"] and "Investor Profile" in own["content"]
    trace = store.list(f"clients/{client_id}/traces/")[0].key
    assert json.loads(service.handle({"action": "kb.get", "key": trace, "client_id": client_id})["content"])
    assert service.handle({"action": "kb.get", "key": "runtime/agents-x.zip"})["error"]["code"] == "bad_request"
    assert service.handle({"action": "kb.get", "key": "general/missing.md"})["error"]["code"] == "not_found"


def test_streamed_deterministic_reply_ends_with_one_result(service, store):
    client_id = start(service)["client_id"]
    answer_base(service, client_id)
    profile = okf.parse(store.get(profile_key(client_id)).text)
    profile.data["facts"]["horizon.horizon_years"] = {"value": 20, "provenance": "a1:1", "at": "2026-11-14T00:00:00Z"}
    profile.data["facts"]["risk_capacity.max_loss_cad"] = {
        "value": 5000,
        "provenance": "a1:1",
        "at": "2026-11-14T00:00:00Z",
    }
    store.put_text(profile_key(client_id), okf.render(profile))
    events = list(service.handle({"action": "followup.reply", "client_id": client_id, "stop": True, "stream": True}))
    assert [e["type"] for e in events][-1] == "result"
    assert all(e["type"] == "trace" for e in events[:-1])
    result = events[-1]["result"]
    assert result["ok"] and result["stage"] == "complete"
    assert result == {**result, "release": "test1234"}
    errors = list(service.handle({"action": "followup.reply", "client_id": str(uuid.uuid4()), "stream": True}))
    assert len(errors) == 1 and errors[0]["type"] == "error" and errors[0]["error"]["code"] == "not_found"


def test_portfolio_doc_is_not_written_without_a_portfolio(service, store):
    client_id = start(service)["client_id"]
    answer_base(service, client_id)
    assert store.get(portfolio_key(client_id)) is None
