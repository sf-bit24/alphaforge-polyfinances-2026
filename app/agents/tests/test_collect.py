"""Runtimes de collecte : acceptation immédiate, tâche asynchrone, marqueur, validation de run_id."""

import pytest

from alphaforge.collect import fetchers, staging
from alphaforge.collect.service import CollectorService
from alphaforge.config import Settings

from .conftest import ScriptedFactory


class FakeApp:
    def __init__(self):
        self.started, self.completed = [], []

    def add_async_task(self, name, metadata=None):
        self.started.append(name)
        return len(self.started)

    def complete_async_task(self, task_id):
        self.completed.append(task_id)
        return True


def service_for(role, store, tmp_path, factory=None):
    settings = Settings.from_env(
        {
            "AGENT_ROLE": role,
            "ALPHAFORGE_STORE": "local",
            "ALPHAFORGE_LOCAL_DIR": str(tmp_path / "kb"),
            "ALPHAFORGE_RELEASE": "r1",
        }
    )
    app = FakeApp()
    return CollectorService(settings, store, app, model_factory=factory or ScriptedFactory()), app


@pytest.mark.parametrize("run_id", [None, "", "a/b", "../x", "a" * 65, "run id", "é", 12])
def test_bad_run_id_is_rejected_before_accepting(store, tmp_path, run_id):
    for role, action in (("press", "collect"), ("data", "collect"), ("supervisor", "curate")):
        service, app = service_for(role, store, tmp_path)
        response = service.handle({"action": action, "run_id": run_id})
        assert response["ok"] is False and response["error"]["code"] == "bad_request", role
        assert app.started == []


def test_other_bad_requests(store, tmp_path):
    service, _ = service_for("press", store, tmp_path)
    assert (
        service.handle({"action": "collect", "run_id": "r1", "since": "2026/11/01"})["error"]["code"] == "bad_request"
    )
    assert (
        service.handle({"action": "collect", "run_id": "r1", "since": "2099-01-01"})["error"]["code"] == "bad_request"
    )
    assert (
        service.handle({"action": "collect", "run_id": "r1", "tickers": ["rm -rf"]})["error"]["code"] == "bad_request"
    )
    assert service.handle({"action": "curate", "run_id": "r1"})["error"]["code"] == "unknown_action"
    assert service.handle({"action": "health"}) == {"ok": True, "release": "r1", "role": "press", "env": "local"}


def test_press_collect_runs_in_the_background_and_writes_its_marker(store, tmp_path, monkeypatch):
    candidate = fetchers.NewsCandidate(
        title="RBC reports fourth quarter results",
        url="https://www.newswire.ca/news-releases/rbc-1.html",
        source="Newswire.ca (Cision)",
        published_at="2099-11-13T14:00:00Z",
        snippet="Royal Bank of Canada (TSX: RY) reported results.",
        language="en",
        provider="newswire_ca_financial",
        tickers=["RY.TO"],
        issuer="Royal Bank of Canada",
    )
    monkeypatch.setattr(
        fetchers, "fetch_press_releases", lambda provider: [candidate] if provider == "newswire_ca_financial" else []
    )
    factory = ScriptedFactory(
        [
            [("tool", "fetch_press_releases", {})],
            [
                (
                    "tool",
                    "stage_news",
                    {
                        "items": [
                            {
                                "cid": "c" + staging.short_hash(staging.normalize_url(candidate.url), 10),
                                "summary": "RBC a publié des résultats supérieurs aux attentes.",
                            }
                        ]
                    },
                )
            ],
            [("tool", "finish", {"note": "ok"})],
        ]
    )
    service, app = service_for("press", store, tmp_path, factory)
    response = service.handle({"action": "collect", "run_id": "exec-1-press", "tickers": ["RY.TO", "TD.TO"]})
    assert response == {
        "ok": True,
        "release": "r1",
        "accepted": True,
        "run_id": "exec-1-press",
        "marker": "staging/exec-1-press/press/_done.json",
    }
    service.wait("exec-1-press", timeout=30)
    marker = store.get_json("staging/exec-1-press/press/_done.json")
    assert marker["status"] == "ok" and marker["role"] == "press" and marker["run_id"] == "exec-1-press"
    assert marker["items"] == 1 and marker["error"] is None
    assert marker["keys"] == [f"staging/exec-1-press/press/{staging.news_item_id(candidate.url)}.json"]
    assert marker["started_at"] <= marker["finished_at"]
    item = store.get_json(marker["keys"][0])
    assert item["kind"] == "news" and item["url"] == candidate.url and item["published_at"] == candidate.published_at
    assert item["summary"].startswith("RBC a publié")
    assert item["tickers"] == ["RY.TO"] and item["data"]["issuer"] == "Royal Bank of Canada"
    assert "snippet" not in item["data"] and "reported results" not in str(item)
    assert app.started == ["press:exec-1-press"] and app.completed == [1]
    again = service.handle({"action": "collect", "run_id": "exec-1-press"})
    assert again["already_done"] is True and len(app.started) == 1


def test_data_collect_stages_series_with_both_dates(store, tmp_path, monkeypatch):
    data = fetchers.SeriesData(
        series_id="V39079",
        provider="boc",
        label="Taux cible",
        unit="percent",
        frequency="daily",
        url="https://www.bankofcanada.ca/valet/observations/V39079/json",
        observations=[{"date": "2026-11-12", "value": 2.25}],
    )
    monkeypatch.setattr(fetchers, "fetch_boc", lambda ids, start: {"V39079": data})
    factory = ScriptedFactory(
        [
            [("tool", "fetch_boc_series", {"series_ids": ["V39079"]})],
            [("tool", "stage_data", {"items": [{"fetch_id": "s:boc:V39079", "note": "Taux directeur."}]})],
            [("tool", "finish", {"note": "ok"})],
        ]
    )
    service, _ = service_for("data", store, tmp_path, factory)
    assert service.handle({"action": "collect", "run_id": "exec-2"})["accepted"]
    service.wait("exec-2", timeout=30)
    marker = store.get_json("staging/exec-2/data/_done.json")
    assert marker["status"] == "ok" and marker["items"] == 1
    item = store.get_json(marker["keys"][0])
    assert item["kind"] == "series" and item["observed_at"] == "2026-11-12"
    assert item["published_at"] == item["retrieved_at"]
    assert item["data"]["published_at_basis"] == "retrieved_at_upper_bound"
    assert "2,25 %" in item["title"]


def test_collector_failure_still_writes_an_error_marker(store, tmp_path):
    def broken(**_):
        raise RuntimeError("no model")

    service, app = service_for("press", store, tmp_path, broken)
    service.handle({"action": "collect", "run_id": "exec-3"})
    service.wait("exec-3", timeout=30)
    marker = store.get_json("staging/exec-3/press/_done.json")
    assert marker["status"] == "error" and marker["items"] == 0 and marker["keys"] == []
    assert "RuntimeError" in marker["error"] and app.completed == [1]


def test_supervisor_marker_is_ok_even_when_nothing_arrived(store, tmp_path):
    service, _ = service_for("supervisor", store, tmp_path)
    store.put_json("staging/exec-4/press/_done.json", {"status": "error", "error": "timeout"})
    assert service.handle({"action": "curate", "run_id": "exec-4"})["marker"] == "staging/exec-4/supervisor/_done.json"
    service.wait("exec-4", timeout=30)
    marker = store.get_json("staging/exec-4/supervisor/_done.json")
    assert marker["status"] == "ok" and marker["written"] == [] and marker["rejected"] == []
    assert any("marqueur press en erreur" in w for w in marker["warnings"])
