"""Runtime portfolio en production : personas FICTION de démo, données longues téléchargées, audit optionnel."""

import json
import os

import pytest

from alphaforge.errors import AppError
from alphaforge.portfolio_service import MARKET_FILES, ensure_market_data

from .test_portfolio_service import FakeEngine, portfolio_settings, service_with  # noqa: F401


@pytest.fixture
def store(portfolio_settings):  # noqa: F811
    from alphaforge.store import make_store

    return make_store(portfolio_settings)


def test_persona_build_is_fiction_and_carries_the_demo_request(portfolio_settings, store):  # noqa: F811
    engine = FakeEngine()
    res = service_with(portfolio_settings, store, engine).handle({"action": "build", "persona": "robert"})
    assert res["ok"] is True, res
    assert res["fiction"] is True and res["persona"] == "robert" and res["client_id"] == "demo-robert"
    call = engine.calls[0]
    assert call["profile"].profile_id == "demo-robert"
    assert call["request"].ticker == "TSLA"
    assert call["style_inputs"].goal == "preservation"
    assert engine.views == []  # aucun profil client lu pour un persona


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "build", "persona": "zorro"},
        {"action": "build", "persona": "amira", "client_id": "8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90"},
    ],
)
def test_persona_misuse_is_refused(portfolio_settings, store, payload):  # noqa: F811
    res = service_with(portfolio_settings, store, FakeEngine()).handle(payload)
    assert res["ok"] is False and res["error"]["code"] == "bad_request"


def test_persona_without_strategy_has_no_style_inputs(portfolio_settings, store):  # noqa: F811
    engine = FakeEngine()
    service_with(portfolio_settings, store, engine).handle({"action": "build", "persona": "amira", "strategy": False})
    assert engine.calls[0]["style_inputs"] is None and engine.calls[0]["strategy"] is False


def test_audit_is_skipped_without_terraform_variables(portfolio_settings, store, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ALPHAFORGE_DECISIONS_TABLE", raising=False)
    monkeypatch.delenv("ALPHAFORGE_TRACE_BUCKET", raising=False)
    res = service_with(portfolio_settings, store, FakeEngine()).handle({"action": "build", "persona": "mateo"})
    assert res["audit"] is None


def _seed(store, prefix, sha):
    for name in MARKET_FILES:
        body = json.dumps({"data_sha256": sha}).encode() if name == "data_version.json" else b"x"
        store.put(f"{prefix}/{name}", body)


def test_market_data_is_copied_once_and_exported(store, tmp_path, monkeypatch):
    monkeypatch.delenv("ALPHAFORGE_BT_DATA", raising=False)
    monkeypatch.setenv("ALPHAFORGE_MARKET_PREFIX", "runtime/market/long/008f122d5da4f8f7")
    _seed(store, "runtime/market/long/008f122d5da4f8f7", "008f122d5da4f8f7")
    dest = ensure_market_data(store, root=str(tmp_path / "long"))
    assert os.environ["ALPHAFORGE_BT_DATA"] == dest and sorted(os.listdir(dest)) == sorted(MARKET_FILES)


def test_market_data_with_another_fingerprint_is_refused(store, tmp_path, monkeypatch):
    monkeypatch.delenv("ALPHAFORGE_BT_DATA", raising=False)
    monkeypatch.setenv("ALPHAFORGE_MARKET_PREFIX", "runtime/market/long/008f122d5da4f8f7")
    _seed(store, "runtime/market/long/008f122d5da4f8f7", "ffffffffffffffff")
    with pytest.raises(AppError):
        ensure_market_data(store, root=str(tmp_path / "long"))


def test_market_data_noop_locally(store, monkeypatch):
    monkeypatch.delenv("ALPHAFORGE_MARKET_PREFIX", raising=False)
    monkeypatch.delenv("ALPHAFORGE_BT_DATA", raising=False)
    assert ensure_market_data(store) is None
