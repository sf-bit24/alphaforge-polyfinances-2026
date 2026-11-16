"""Knowledge Base de chaque client (profile/client_kb.py), sans AWS : faux clients bedrock-agent et s3vectors."""

import json
from datetime import timedelta

import pytest
from botocore.exceptions import ClientError

from alphaforge import clock, okf
from alphaforge.config import Settings
from alphaforge.portfolio_service import PortfolioService
from alphaforge.profile import brain
from alphaforge.profile.client_kb import (
    AwsClients,
    ClientKbConfig,
    ClientKnowledgeBases,
    IndexingStore,
    indexed_client,
    state_key,
)
from alphaforge.profile.service import ProfileService
from alphaforge.profile.state import index_key, journal_key, profile_key

from .conftest import BASE_ANSWERS, ScriptedFactory, answer_base, make_service
from .test_agents_stub import finish
from .test_portfolio_service import CLIENT_ID, FakeEngine

CONFIG = ClientKbConfig(
    region="us-east-1",
    prefix="alphaforge-test",
    vector_bucket="alphaforge-test-client-vectors",
    role_arn="arn:aws:iam::123456789012:role/alphaforge-test-client-knowledge-base",
    embedding_model_arn="arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
    dimensions=1024,
)


def client_error(code, operation="Operation"):
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **_):
        return iter(self.pages)


class FakeAgent:
    """bedrock-agent : idempotence par clientToken, statut de création réglable, documents par Knowledge Base."""

    def __init__(self, kb_status="CREATING"):
        self.kb_status = kb_status
        self.kbs = {}
        self.tokens = {}
        self.calls = []
        self.documents = {}
        self.fail = {}  # opération -> codes d'erreur à lever, un par appel

    def _maybe_fail(self, operation):
        codes = self.fail.get(operation) or []
        if codes:
            raise client_error(codes.pop(0), operation)

    def create_knowledge_base(self, **params):
        self.calls.append(("create_knowledge_base", params))
        self._maybe_fail("create_knowledge_base")
        token = params["clientToken"]
        if token not in self.tokens:
            kb_id = f"KB{len(self.tokens) + 1:08d}"
            self.tokens[token] = kb_id
            self.kbs[kb_id] = {
                "knowledgeBaseId": kb_id,
                "knowledgeBaseArn": f"arn:aws:bedrock:us-east-1:123456789012:knowledge-base/{kb_id}",
                "name": params["name"],
                "status": self.kb_status,
                "tags": params["tags"],
            }
        return {"knowledgeBase": dict(self.kbs[self.tokens[token]])}

    def get_knowledge_base(self, knowledgeBaseId):
        self.calls.append(("get_knowledge_base", knowledgeBaseId))
        return {"knowledgeBase": {**self.kbs[knowledgeBaseId], "status": self.kb_status}}

    def create_data_source(self, **params):
        self.calls.append(("create_data_source", params))
        return {"dataSource": {"dataSourceId": f"DS-{params['knowledgeBaseId']}", "status": "AVAILABLE"}}

    def ingest_knowledge_base_documents(self, **params):
        self.calls.append(("ingest", params))
        self._maybe_fail("ingest")
        assert len(params["documents"]) <= 10  # borne du modèle botocore
        docs = self.documents.setdefault(params["knowledgeBaseId"], {})
        details = []
        for item in params["documents"]:
            key = item["content"]["custom"]["customDocumentIdentifier"]["id"]
            docs[key] = item
            details.append({"identifier": {"dataSourceType": "CUSTOM", "custom": {"id": key}}, "status": "STARTING"})
        return {"documentDetails": details}

    def delete_knowledge_base_documents(self, **params):
        self.calls.append(("delete", params))
        for identifier in params["documentIdentifiers"]:
            self.documents.get(params["knowledgeBaseId"], {}).pop(identifier["custom"]["id"], None)
        return {"documentDetails": []}

    def get_paginator(self, name):
        if name == "list_knowledge_bases":
            return FakePaginator([{"knowledgeBaseSummaries": list(self.kbs.values())}])
        return FakePaginator([{"dataSourceSummaries": []}])

    def operations(self):
        return [name for name, _ in self.calls]


class FakeVectors:
    def __init__(self):
        self.indexes = {}
        self.calls = []

    def create_index(self, **params):
        self.calls.append(("create_index", params))
        name = params["indexName"]
        if name in self.indexes:
            raise client_error("ConflictException", "CreateIndex")
        self.indexes[name] = (
            f"arn:aws:s3vectors:us-east-1:123456789012:bucket/{params['vectorBucketName']}/index/{name}"
        )
        return {"indexArn": self.indexes[name]}

    def get_index(self, vectorBucketName, indexName):
        self.calls.append(("get_index", indexName))
        return {"index": {"indexArn": self.indexes[indexName]}}


class FakeRuntime:
    def __init__(self):
        self.calls = []
        self.results = []

    def retrieve(self, **params):
        self.calls.append(params)
        return {"retrievalResults": self.results}


@pytest.fixture
def aws():
    return AwsClients(agent=FakeAgent(), runtime=FakeRuntime(), vectors=FakeVectors())


@pytest.fixture
def kbs(store, aws):
    return ClientKnowledgeBases(CONFIG, store, can_create=True, clients=aws)


@pytest.fixture
def service(settings, store, kbs):
    def no_model(**_):
        raise AssertionError("a deterministic action must not create a model")

    return ProfileService(
        settings, store, model_factory=no_model, quote_fetcher=None, write_client_brain=False, client_kb=kbs
    )


def start(service):
    response = service.handle({"action": "session.start", "locale": "fr"})
    assert response["ok"], response
    return response


def kb_state(store, client_id):
    return json.loads(store.get(state_key(client_id)).text)


def titles(response):
    return [step["title"] for step in response["trace"]]


def note(title, body="Une note du client.", **data):
    return okf.render(
        okf.new_doc(
            type="Profile Note",
            title=title,
            description="Note de test.",
            tags=["profil-investisseur"],
            owners=["alphaforge-a1"],
            sensitivity="client",
            generated_by="agent:A1",
            at=clock.iso(),
            status="stable",
            sources=[],
            data=data,
            body=body,
        )
    )


def answer_first(service, client_id):
    """Répond à la question de base en attente avec la réponse de conftest.BASE_ANSWERS."""
    pending = service.handle({"action": "session.resume", "client_id": client_id})["questions"][0]
    response = service.handle(
        {
            "action": "base.answer",
            "client_id": client_id,
            "question_id": pending["id"],
            "value": BASE_ANSWERS[pending["id"]],
        }
    )
    assert response["ok"], response
    return response


def activate(service, aws, client_id):
    aws.agent.kb_status = "ACTIVE"
    response = service.handle({"action": "session.resume", "client_id": client_id})
    assert response["ok"] and response["client_kb"]["status"] == "active", response
    return response


def test_indexed_keys_are_the_client_markdown_documents():
    client = "8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90"
    assert indexed_client(f"clients/{client}/profil.md") == client
    assert indexed_client(f"clients/{client}/decisions/dec-1.md") == client
    assert indexed_client(f"clients/{client}/traces/20261115T000000.000Z-session.start.json") is None
    assert indexed_client(f"clients/{client}/traces/x.md") is None
    assert indexed_client(f"clients/{client}/decisions/dec-1.json") is None
    assert indexed_client(f"clients/{client}/kb.json") is None
    assert indexed_client("general/index.md") is None
    assert indexed_client("clients/not-a-uuid/profil.md") is None


def test_session_start_creates_the_index_then_the_knowledge_base(service, store, aws):
    response = start(service)
    client_id = response["client_id"]
    assert response["client_kb"] == {
        "status": "creating",
        "knowledge_base_id": "KB00000001",
        "documents": 0,
        "pending": 3,
    }
    [(_, index)] = aws.vectors.calls
    assert index["indexName"] == f"client-{client_id}" and index["vectorBucketName"] == CONFIG.vector_bucket
    assert index["dimension"] == 1024 and index["distanceMetric"] == "cosine"
    assert index["metadataConfiguration"] == {
        "nonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
    }
    [(_, params)] = aws.agent.calls
    assert params["name"] == f"alphaforge-test-client-{client_id}"
    assert params["clientToken"] == f"alphaforge-test-kb-{client_id}"
    assert params["tags"] == {
        "alphaforge:scope": "client",
        "alphaforge:client_id": client_id,
        "alphaforge:prefix": "alphaforge-test",
    }
    assert params["storageConfiguration"]["s3VectorsConfiguration"]["indexArn"].endswith(f"/index/client-{client_id}")
    embedding = params["knowledgeBaseConfiguration"]["vectorKnowledgeBaseConfiguration"]
    assert embedding["embeddingModelConfiguration"]["bedrockEmbeddingModelConfiguration"]["dimensions"] == 1024
    state = kb_state(store, client_id)
    assert state["status"] == "creating" and state["data_source_id"] is None
    assert state["pending"] == sorted([profile_key(client_id), journal_key(client_id), index_key(client_id)])
    assert "Knowledge Base du client créée" in titles(response)
    # La trace enregistrée de l'action montre aussi la création.
    [saved] = store.list(f"clients/{client_id}/traces/")
    steps = json.loads(store.get(saved.key).text)["steps"]
    assert "Knowledge Base du client créée" in [step["title"] for step in steps]


def test_active_base_receives_the_pending_documents_then_costs_nothing(service, store, aws):
    client_id = start(service)["client_id"]
    aws.agent.kb_status = "ACTIVE"
    response = service.handle({"action": "session.resume", "client_id": client_id})
    assert response["client_kb"] == {
        "status": "active",
        "knowledge_base_id": "KB00000001",
        "documents": 3,
        "pending": 0,
    }
    assert aws.agent.operations() == ["create_knowledge_base", "get_knowledge_base", "create_data_source", "ingest"]
    source = aws.agent.calls[2][1]
    assert source["dataSourceConfiguration"] == {"type": "CUSTOM"} and source["dataDeletionPolicy"] == "RETAIN"
    assert source["clientToken"] == f"alphaforge-test-ds-{client_id}"
    ingested = aws.agent.documents["KB00000001"]
    assert set(ingested) == {profile_key(client_id), journal_key(client_id), index_key(client_id)}
    profile_doc = ingested[profile_key(client_id)]
    assert profile_doc["content"]["custom"]["sourceType"] == "IN_LINE"
    assert profile_doc["content"]["custom"]["inlineContent"]["textContent"]["data"].startswith("Profil investisseur")
    attributes = {item["key"]: item["value"]["stringValue"] for item in profile_doc["metadata"]["inlineAttributes"]}
    assert attributes["type"] == "Investor Profile" and attributes["client_id"] == client_id
    assert attributes["updated_at"]
    assert "Knowledge Base du client active" in titles(response)
    assert "Documents indexés dans la Knowledge Base du client" in titles(response)
    # Base active, rien en attente : un rapprochement ne fait aucun appel AWS et ne réécrit pas l'état.
    etag = store.get(state_key(client_id)).etag
    calls = len(aws.agent.calls)
    again = service.handle({"action": "profile.get", "client_id": client_id})
    assert again["client_kb"]["status"] == "active" and len(aws.agent.calls) == calls
    assert store.get(state_key(client_id)).etag == etag


def test_documents_written_while_creating_wait_then_go_in_batches(service, store, aws):
    client_id = start(service)["client_id"]
    answer = answer_first(service, client_id)
    assert answer["client_kb"]["status"] == "creating"
    assert "Documents en attente de la Knowledge Base" in titles(answer)
    for number in range(12):
        service.store.put_text(f"clients/{client_id}/notes/note-{number:02d}.md", note(f"Note {number}"))
    assert kb_state(store, client_id)["pending"] == sorted(
        [profile_key(client_id), journal_key(client_id), index_key(client_id)]
    )
    response = activate(service, aws, client_id)
    assert response["client_kb"]["documents"] == 15 and response["client_kb"]["pending"] == 0
    batches = [len(params["documents"]) for name, params in aws.agent.calls if name == "ingest"]
    assert batches == [10, 5]


def test_throttled_ingestion_keeps_the_keys_pending(service, store, aws):
    client_id = start(service)["client_id"]
    aws.agent.fail["ingest"] = ["ThrottlingException"]
    response = activate(service, aws, client_id)
    assert response["client_kb"]["pending"] == 3 and response["client_kb"]["documents"] == 0
    assert kb_state(store, client_id)["error"]["code"] == "ThrottlingException"
    later = service.handle({"action": "session.resume", "client_id": client_id})
    assert later["client_kb"] == {"status": "active", "knowledge_base_id": "KB00000001", "documents": 3, "pending": 0}


def test_retired_note_leaves_the_knowledge_base(service, store, aws):
    client_id = start(service)["client_id"]
    activate(service, aws, client_id)
    key = f"clients/{client_id}/dimensions/horizon.md"
    service.store.put_text(key, note("Horizon", "Horizon de plus de dix ans."))
    service.handle({"action": "session.resume", "client_id": client_id})
    assert key in aws.agent.documents["KB00000001"] and key in kb_state(store, client_id)["indexed"]
    service.store.put_text(key, okf.render(brain.retired_doc("client-brain-update", "v1")))
    response = service.handle({"action": "session.resume", "client_id": client_id})
    [delete] = [params for name, params in aws.agent.calls if name == "delete"]
    assert delete["documentIdentifiers"] == [{"dataSourceType": "CUSTOM", "custom": {"id": key}}]
    assert key not in aws.agent.documents["KB00000001"]
    assert key not in kb_state(store, client_id)["indexed"] and response["client_kb"]["documents"] == 3


def test_traces_and_json_are_never_ingested(service, store, aws):
    client_id = start(service)["client_id"]
    activate(service, aws, client_id)
    service.store.put_json(f"clients/{client_id}/decisions/dec-1.json", {"decision_id": "dec-1"})
    answer_first(service, client_id)
    keys = set(aws.agent.documents["KB00000001"])
    assert keys and all(key.endswith(".md") and "/traces/" not in key for key in keys)


def test_quota_reached_keeps_the_questionnaire_going(service, store, aws, monkeypatch):
    aws.agent.fail["create_knowledge_base"] = ["ServiceQuotaExceededException"]
    response = start(service)
    client_id = response["client_id"]
    assert response["ok"] and response["client_kb"]["status"] == "quota" and response["stage"] == "base_questions"
    assert "Quota de Knowledge Bases atteint" in titles(response)
    state = kb_state(store, client_id)
    assert state["error"]["code"] == "ServiceQuotaExceededException" and state["retry_at"]
    answer = answer_first(service, client_id)
    assert answer["client_kb"]["status"] == "quota"
    assert aws.agent.operations() == ["create_knowledge_base"]  # pas de nouvel essai avant retry_at
    later = clock.utcnow() + timedelta(hours=2)
    monkeypatch.setattr(clock, "utcnow", lambda: later)
    retried = service.handle({"action": "session.resume", "client_id": client_id})
    assert retried["client_kb"]["status"] == "creating" and aws.agent.operations().count("create_knowledge_base") == 2


def test_unexpected_errors_never_fail_the_investor(service, store, aws, monkeypatch):
    def broken(*_, **__):
        raise RuntimeError("boom")

    monkeypatch.setattr(aws.vectors, "create_index", broken)
    response = start(service)
    assert response["ok"] and response["client_kb"]["status"] == "failed"
    assert "Knowledge Base du client en échec" in titles(response)


def test_concurrent_creation_gives_one_knowledge_base(store, aws):
    """Deux microVM créent la base du même client : même clientToken, même index, un seul kb.json."""
    client_id = "8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90"
    store.put_text(profile_key(client_id), note("Profil"))
    first = ClientKnowledgeBases(CONFIG, store, can_create=True, clients=aws)

    class StaleStore(IndexingStore):
        """Lecture périmée, une fois : la seconde requête ne voit pas encore kb.json écrit par la première."""

        stale = True

        def get(self, key):
            if key == state_key(client_id) and self.stale:
                self.stale = False
                return None
            return self.inner.get(key)

    second = ClientKnowledgeBases(CONFIG, store, can_create=True, clients=aws)
    second.store = StaleStore(store, second)
    assert first.sync(client_id, None, create=True)["status"] == "creating"
    view = second.sync(client_id, None, create=True)
    assert view == {"status": "creating", "knowledge_base_id": "KB00000001", "documents": 0, "pending": 1}
    assert len(aws.agent.kbs) == 1 and aws.agent.operations().count("create_knowledge_base") == 2
    assert [name for name, _ in aws.vectors.calls] == ["create_index", "create_index", "get_index"]
    assert kb_state(store, client_id)["knowledge_base_id"] == "KB00000001"


def test_search_is_bound_to_the_knowledge_base_of_the_session(service, store, aws):
    client_id = start(service)["client_id"]
    assert service.client_kb.search(client_id, "décision")["status"] == "creating"
    activate(service, aws, client_id)
    other = "0b1d7c52-3a6e-4f1b-8c2d-9e8f7a6b5c4d"
    aws.runtime.results = [
        {
            "content": {"text": "Décision de portefeuille dec-1 : allocation prudente."},
            "location": {"type": "CUSTOM", "customDocumentLocation": {"id": f"clients/{client_id}/decisions/dec-1.md"}},
            "score": 0.71,
        },
        {
            "content": {"text": "Une autre base."},
            "location": {"type": "CUSTOM", "customDocumentLocation": {"id": f"clients/{other}/profil.md"}},
            "score": 0.9,
        },
    ]
    found = service.client_kb.searcher(client_id)("décision passée")
    assert found["status"] == "active"
    assert found["results"] == [
        {
            "key": f"clients/{client_id}/decisions/dec-1.md",
            "score": 0.71,
            "excerpt": "Décision de portefeuille dec-1 : allocation prudente.",
        }
    ]
    [call] = aws.runtime.calls
    assert call["knowledgeBaseId"] == kb_state(store, client_id)["knowledge_base_id"]


def test_a1_searches_the_client_knowledge_base_of_its_session(settings, store, aws, kbs):
    script = [
        [("tool", "search_client_knowledge", {"query": "décision passée"})],
        [finish("Merci, continuons.")],
    ]
    factory = ScriptedFactory(script)
    service = ProfileService(
        settings, store, model_factory=factory, quote_fetcher=None, write_client_brain=False, client_kb=kbs
    )
    client_id = start(service)["client_id"]
    aws.agent.kb_status = "ACTIVE"
    answer_base(service, client_id)
    response = service.handle({"action": "followup.reply", "client_id": client_id, "message": "Bonjour."})
    assert response["ok"], response
    model = factory.models[0]
    assert model.calls[0]["tools"] == [
        "update_profile",
        "check_completeness",
        "search_general_knowledge",
        "search_client_knowledge",
        "finish_turn",
    ]
    assert "search_client_knowledge" in model.calls[0]["system_prompt"]
    [call] = aws.runtime.calls
    assert call["knowledgeBaseId"] == "KB00000001" and call["retrievalQuery"] == {"text": "décision passée"}
    tool_steps = [step for step in response["trace"] if step["title"] == "Outil search_client_knowledge"]
    assert tool_steps and tool_steps[0]["kind"] == "tool"


def test_disabled_mode_changes_nothing(settings, store):
    service = make_service(settings, store)
    assert not isinstance(service.store, IndexingStore) and not service.client_kb.enabled
    response = service.handle({"action": "session.start", "locale": "fr"})
    client_id = response["client_id"]
    assert response["client_kb"] == {"status": "disabled", "knowledge_base_id": None, "documents": 0, "pending": 0}
    assert store.get(state_key(client_id)) is None
    assert not any("Knowledge Base" in title for title in titles(response))
    assert service.client_kb.searcher(client_id) is None
    resumed = service.handle({"action": "session.resume", "client_id": client_id})
    assert resumed["client_kb"]["status"] == "disabled"


def test_configuration_needs_s3_and_every_variable(tmp_path):
    env = {
        "ALPHAFORGE_STORE": "s3",
        "ALPHAFORGE_BUCKET": "bucket",
        "ALPHAFORGE_CLIENT_KB_VECTOR_BUCKET": "alphaforge-test-client-vectors",
        "ALPHAFORGE_CLIENT_KB_ROLE_ARN": CONFIG.role_arn,
        "ALPHAFORGE_CLIENT_KB_PREFIX": "alphaforge-test",
        "ALPHAFORGE_CLIENT_KB_EMBEDDING_MODEL_ARN": CONFIG.embedding_model_arn,
        "ALPHAFORGE_CLIENT_KB_EMBEDDING_DIMENSIONS": "1024",
    }
    assert ClientKbConfig.from_settings(Settings.from_env(env)) == CONFIG
    assert ClientKbConfig.from_settings(Settings.from_env({**env, "ALPHAFORGE_STORE": "local"})) is None
    assert ClientKbConfig.from_settings(Settings.from_env({**env, "ALPHAFORGE_CLIENT_KB_ROLE_ARN": ""})) is None


class WritingEngine(FakeEngine):
    """Moteur factice dont la décision est écrite dans le magasin du service, comme okf_bridge.save_decision."""

    def load(self):
        loaded = super().load()
        base = loaded["okf_bridge"].OkfClientStore

        class ClientStore(base):
            def __init__(self, store, questionnaire=None, locale="fr"):
                super().__init__(store, questionnaire, locale)
                self.store = store

            def save_decision(self, decision, policy=None):
                key = super().save_decision(decision, policy)
                self.store.put_json(key.removesuffix(".md") + ".json", {"decision_id": decision.decision_id})
                self.store.put_text(key, note("Décision de portefeuille dec-1", "Allocation prudente."))
                return key

        loaded["okf_bridge"].OkfClientStore = ClientStore
        return loaded


def portfolio(store, aws, tmp_path):
    settings = Settings.from_env({"AGENT_ROLE": "portfolio", "ALPHAFORGE_STORE": "local", "ALPHAFORGE_RELEASE": "t"})
    kbs = ClientKnowledgeBases(CONFIG, store, can_create=False, clients=aws)
    return PortfolioService(settings, store, engine=WritingEngine().load, client_kb=kbs)


def build(service):
    response = service.handle({"action": "build", "client_id": CLIENT_ID, "mode": "rules"})
    assert response["ok"], response
    return response


def test_portfolio_never_creates_a_knowledge_base(store, aws, tmp_path):
    response = build(portfolio(store, aws, tmp_path))
    assert response["client_kb"] is None
    assert aws.agent.calls == [] and aws.vectors.calls == [] and store.get(state_key(CLIENT_ID)) is None


def test_portfolio_decision_waits_then_is_ingested(store, aws, tmp_path):
    profile_kbs = ClientKnowledgeBases(CONFIG, store, can_create=True, clients=aws)
    store.put_text(profile_key(CLIENT_ID), note("Profil"))
    profile_kbs.sync(CLIENT_ID, None, create=True)
    service = portfolio(store, aws, tmp_path)
    decision = f"clients/{CLIENT_ID}/decisions/dec-1.md"
    response = build(service)
    assert response["client_kb"]["status"] == "creating" and decision in kb_state(store, CLIENT_ID)["pending"]
    calls = aws.agent.operations()
    assert "get_knowledge_base" not in calls  # portfolio ne fait jamais avancer la création
    aws.agent.kb_status = "ACTIVE"
    assert profile_kbs.sync(CLIENT_ID, None, create=True)["status"] == "active"
    assert decision in aws.agent.documents["KB00000001"]
    again = build(service)
    assert again["client_kb"]["status"] == "active" and again["client_kb"]["pending"] == 0
    ingested = [params for name, params in aws.agent.calls if name == "ingest"][-1]["documents"]
    assert [item["content"]["custom"]["customDocumentIdentifier"]["id"] for item in ingested] == [decision]
