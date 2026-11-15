"""L'application BedrockAgentCoreApp : /invocations en JSON et en SSE, /ping."""

import json

from starlette.testclient import TestClient

from alphaforge.config import Settings
from alphaforge.server import create_app

from .conftest import answer_base, make_service


def test_invocations_json_and_ping(settings, store):
    service = make_service(settings, store)
    client = TestClient(create_app(settings, service=service))
    assert client.get("/ping").json()["status"] == "Healthy"
    response = client.post("/invocations", json={"action": "health"})
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"ok": True, "release": "test1234", "role": "profile", "env": "test"}
    started = client.post("/invocations", json={"action": "session.start", "locale": "en"}).json()
    assert started["ok"] and started["questions"][0]["prompt"].startswith("Over the last three years")


def test_invocations_stream_as_server_sent_events(settings, store):
    service = make_service(settings, store)
    client = TestClient(create_app(settings, service=service))
    client_id = client.post("/invocations", json={"action": "session.start"}).json()["client_id"]
    answer_base(service, client_id)
    with client.stream(
        "POST", "/invocations", json={"action": "followup.reply", "client_id": client_id, "stop": True, "stream": True}
    ) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in response.iter_lines() if line.startswith("data: ")]
    events = [json.loads(line[len("data: ") :]) for line in lines]
    assert events[-1]["type"] == "error" and events[-1]["error"]["code"] == "conflict"
    assert sum(e["type"] in ("result", "error") for e in events) == 1


def test_collector_app_reports_busy_while_a_task_runs(tmp_path):
    settings = Settings.from_env(
        {"AGENT_ROLE": "supervisor", "ALPHAFORGE_STORE": "local", "ALPHAFORGE_LOCAL_DIR": str(tmp_path / "kb")}
    )
    app = create_app(settings)
    task = app.add_async_task("supervisor:x")
    client = TestClient(app)
    assert client.get("/ping").json()["status"] == "HealthyBusy"
    app.complete_async_task(task)
    assert client.get("/ping").json()["status"] == "Healthy"
    assert (
        client.post("/invocations", json={"action": "curate", "run_id": "bad id"}).json()["error"]["code"]
        == "bad_request"
    )


def test_local_store_is_seeded_with_the_versioned_general_documents(tmp_path):
    from alphaforge.server import _local_seed_dir, seed_local_general
    from alphaforge.store.local import LocalStore

    seed = _local_seed_dir()
    assert seed is not None and seed.name == "general"
    store = LocalStore(tmp_path / "kb")
    assert seed_local_general(store, seed) >= 5
    assert store.exists("general/methodologie/horizon-de-placement.md")
    assert seed_local_general(store, seed) == 0
