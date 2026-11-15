"""Aiguillage des actions ``evolution.*`` dans le runtime portfolio (sans moteur : actions remplacées par des stubs).

Le CI ne contient pas le groupe ``finance`` : on ne charge ni numpy ni le moteur ; seul le routage, la tâche
asynchrone et le marqueur d'erreur sont vérifiés.
"""
from __future__ import annotations

import sys
import types

import pytest

from .test_portfolio_service import FakeEngine, portfolio_settings, service_with  # noqa: F401


class FakeApp:
    def __init__(self) -> None:
        self.added: list[str] = []
        self.completed: list[int] = []

    def add_async_task(self, name, meta=None):
        self.added.append(name)
        return len(self.added)

    def complete_async_task(self, task_id):
        self.completed.append(task_id)


@pytest.fixture
def fake_actions(monkeypatch):
    """Module ``alphaforge.finance.evolution.actions`` factice (le vrai importe le moteur)."""
    calls: list[tuple[str, dict]] = []
    mod = types.ModuleType("alphaforge.finance.evolution.actions")

    def handler(name):
        def fn(payload, *, store=None, **_):
            calls.append((name, dict(payload)))
            return {"ok": True, "run_id": payload.get("run_id")}
        return fn

    mod.handle_tick = handler("tick")
    mod.handle_replay = handler("replay")
    mod.handle_replay_summary = lambda payload, *, store=None: {"ok": True, "versions": 0}
    mod.write_error_marker = lambda *a, **k: calls.append(("error_marker", {}))
    pkg = types.ModuleType("alphaforge.finance.evolution")
    pkg.actions = mod
    monkeypatch.setitem(sys.modules, "alphaforge.finance.evolution", pkg)
    monkeypatch.setitem(sys.modules, "alphaforge.finance.evolution.actions", mod)
    return calls


def _service(portfolio_settings, store, app=None):  # noqa: F811
    from alphaforge.portfolio_service import PortfolioService

    return PortfolioService(portfolio_settings, store, app, engine=FakeEngine().load)


def test_replay_is_accepted_then_runs_in_background(portfolio_settings, store, fake_actions):  # noqa: F811
    app = FakeApp()
    svc = _service(portfolio_settings, store, app)
    out = svc.handle({"action": "evolution.replay", "client_id": "demo-amira", "run_id": "r1"})
    assert out["ok"] and out["accepted"] and out["simulation_only"] and out["run_id"] == "r1"
    svc.wait_evolution("r1", timeout=10)
    assert fake_actions == [("replay", {"action": "evolution.replay", "client_id": "demo-amira", "run_id": "r1"})]
    assert app.added == ["portfolio:evolution.replay:r1"] and app.completed == [1]


def test_tick_uses_the_tick_handler(portfolio_settings, store, fake_actions):  # noqa: F811
    svc = _service(portfolio_settings, store)
    out = svc.handle({"action": "evolution.tick", "client_id": "c1", "run_id": "t1", "month": "2026-10"})
    svc.wait_evolution("t1", timeout=10)
    assert out["accepted"] and fake_actions[0][0] == "tick"


def test_summary_answers_synchronously(portfolio_settings, store, fake_actions):  # noqa: F811
    out = _service(portfolio_settings, store).handle({"action": "evolution.replay_summary", "client_id": "c1"})
    assert out["ok"] and out["versions"] == 0 and "release" in out


def test_missing_run_id_is_refused(portfolio_settings, store, fake_actions):  # noqa: F811
    out = _service(portfolio_settings, store).handle({"action": "evolution.replay", "client_id": "c1"})
    assert not out["ok"] and out["error"]["code"] == "bad_request" and fake_actions == []


def test_engine_failure_writes_an_error_marker(portfolio_settings, store, fake_actions):  # noqa: F811
    from alphaforge.portfolio_service import PortfolioService

    def broken():
        raise RuntimeError("moteur absent")

    app = FakeApp()
    svc = PortfolioService(portfolio_settings, store, app, engine=broken)
    svc.handle({"action": "evolution.replay", "client_id": "c1", "run_id": "r2"})
    svc.wait_evolution("r2", timeout=10)
    assert ("error_marker", {}) in fake_actions and app.completed == [1]


def test_unknown_action_lists_evolution_actions(portfolio_settings, store):  # noqa: F811
    out = _service(portfolio_settings, store).handle({"action": "nope"})
    assert out["error"]["code"] == "unknown_action"
    assert "evolution.replay" in out["error"]["details"]["expected"]
