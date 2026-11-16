"""Runtime ``portfolio`` : service mince, chargement paresseux du volet finance, validation des requêtes."""

import sys
from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from alphaforge.config import ROLES, Settings
from alphaforge.server import build_service, create_app

CLIENT_ID = "8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90"
HEAVY = ("numpy", "pandas", "scipy", "cvxpy", "clarabel", "pyarrow")


@pytest.fixture
def portfolio_settings(tmp_path):
    return Settings.from_env(
        {
            "AGENT_ROLE": "portfolio",
            "ALPHAFORGE_STORE": "local",
            "ALPHAFORGE_LOCAL_DIR": str(tmp_path / "kb"),
            "ALPHAFORGE_RELEASE": "test1234",
            "ALPHAFORGE_ENV": "test",
            "ALPHAFORGE_GUARDRAIL_ID": "gr1",
            "ALPHAFORGE_GUARDRAIL_VERSION": "3",
        }
    )


def test_portfolio_is_a_role():
    assert "portfolio" in ROLES


def test_build_service_does_not_import_the_finance_engine(portfolio_settings, store, monkeypatch):
    """Ni le service ni health ne chargent numpy, cvxpy ou le volet finance : les autres runtimes n'en ont pas."""
    for name in list(sys.modules):
        if name.split(".")[0] in HEAVY or name.startswith(("alphaforge.finance", "alphaforge.portfolio_service")):
            monkeypatch.delitem(sys.modules, name)
    for name in HEAVY:
        monkeypatch.setitem(sys.modules, name, None)  # un import lèverait ImportError
    service = build_service(portfolio_settings, app=None, store=store)
    assert type(service).__name__ == "PortfolioService"
    assert service.handle({"action": "health"}) == {
        "ok": True,
        "release": "test1234",
        "role": "portfolio",
        "env": "test",
    }
    assert not any(name.startswith("alphaforge.finance") for name in sys.modules)
    assert all(sys.modules.get(name) is None for name in HEAVY)


def test_build_without_the_finance_engine_reports_a_clear_error(portfolio_settings, store, monkeypatch):
    """Zip commun déployé par repli (agents-portfolio.zip absent) : health répond, build le dit clairement."""
    for name in list(sys.modules):
        if name.split(".")[0] in HEAVY or name.startswith(("alphaforge.finance", "alphaforge.portfolio_service")):
            monkeypatch.delitem(sys.modules, name)
    for name in HEAVY:
        monkeypatch.setitem(sys.modules, name, None)
    service = build_service(portfolio_settings, app=None, store=store)
    response = service.handle({"action": "build", "client_id": CLIENT_ID, "mode": "rules"})
    assert response["ok"] is False and response["error"]["code"] == "internal"
    assert response["error"]["details"]["expected_package"] == "agents-portfolio.zip"
    assert response["error"]["message"] == "Le simulateur ne répond pas pour l'instant : réessayez dans un instant."
    assert response["error"]["details"]["missing_module"] in HEAVY
    assert service.handle({"action": "health"})["ok"] is True


def test_portfolio_app_answers_health_over_http(portfolio_settings, store):
    client = TestClient(create_app(portfolio_settings, store=store))
    assert client.get("/ping").json()["status"] == "Healthy"
    assert client.post("/invocations", json={"action": "health"}).json()["role"] == "portfolio"


# --------------------------------------------------------------------------- moteur factice


@dataclass
class FakeRequest:
    ticker: str
    amount_cad: float | None = None
    weight: float | None = None


class Dumpable(SimpleNamespace):
    def model_dump(self, mode=None):
        return dict(vars(self))


class FakeStrategy:
    def summary(self):
        return {"style": "dynamique", "applied": True}


@dataclass
class FakeEngine:
    profiles: dict = field(default_factory=lambda: {CLIENT_ID: "profil"})
    calls: list = field(default_factory=list)
    saved: list = field(default_factory=list)
    views: list = field(default_factory=list)
    client_inputs: list = field(default_factory=list)
    flushed: int = 0

    def load(self):
        engine = self

        def build_portfolio(
            profile,
            as_of,
            *,
            request=None,
            mode="rules",
            evidence_fn=None,
            strategy=True,
            style_preference=None,
            style_inputs=None,
            **kwargs,
        ):
            engine.calls.append(
                {
                    "profile": profile,
                    "as_of": as_of,
                    "request": request,
                    "mode": mode,
                    "strategy": strategy,
                    "style_preference": style_preference,
                    "style_inputs": style_inputs,
                    **kwargs,
                }
            )
            assert evidence_fn("SHOP.TO", "esg", as_of) == []
            return SimpleNamespace(
                decision=Dumpable(decision_id="dec-1", profile_id=CLIENT_ID, kind="allocation"),
                policy=Dumpable(policy_id="pol-1"),
                rounds=[SimpleNamespace(round=1, verdicts={"risk": "support"}, decisions=[Dumpable(kind="flag_only")])],
                explanation_report=["ok"],
                grounding={"verified": True},
                strategy=FakeStrategy() if strategy else None,
            )

        class ClientStore:
            def __init__(self, store, questionnaire=None, locale="fr"):
                self.locale = locale
                self.inputs = {}

            def load_profile(self, client_id):
                if client_id not in engine.profiles:
                    raise KeyError(client_id)
                return engine.profiles[client_id]

            def view(self, client_id):
                engine.views.append(client_id)
                return {"facts": [{"field": "objective.goal", "value": "growth"}]}, {}, None

            def save_decision(self, decision, policy=None):
                engine.saved.append((decision.decision_id, policy.policy_id))
                return f"clients/{decision.profile_id}/decisions/{decision.decision_id}.md"

        class MarketStore:
            def __init__(self, store):
                pass

            def evidence(self, ticker, topic, as_of):
                return []

            def note_client_inputs(self, inputs):
                engine.client_inputs.append(dict(inputs))

            def methodology(self):
                return [("general/methodologie/m.md", "méthode")]

        def flush():
            engine.flushed += 1

        def style_inputs_from_view(view):
            return ("style-inputs", view["facts"][0]["value"])

        pipeline = SimpleNamespace(
            build_portfolio=build_portfolio, Request=FakeRequest, DEFAULT_AS_OF=date(2026, 9, 30)
        )
        bridge = SimpleNamespace(OkfClientStore=ClientStore, OkfMarketStore=MarketStore)
        return {
            "pipeline": pipeline,
            "okf_bridge": bridge,
            "telemetry": SimpleNamespace(flush=flush),
            "style_inputs_from_view": style_inputs_from_view,
            "styles": ("defensive", "dynamique", "offensive"),
        }


def service_with(portfolio_settings, store, engine):
    from alphaforge.portfolio_service import PortfolioService

    return PortfolioService(portfolio_settings, store, engine=engine.load)


def test_build_runs_the_engine_and_returns_the_decision(portfolio_settings, store):
    engine = FakeEngine()
    service = service_with(portfolio_settings, store, engine)
    response = service.handle(
        {
            "action": "build",
            "client_id": CLIENT_ID,
            "as_of": "2026-11-12",
            "request": {"ticker": "TSLA", "amount_cad": 50000},
            "mode": "rules",
        }
    )
    assert response["ok"], response
    assert response["decision_key"] == f"clients/{CLIENT_ID}/decisions/dec-1.md"
    assert response["simulation_only"] is True and response["as_of"] == "2026-11-12" and response["mode"] == "rules"
    assert response["decision"] == {"decision_id": "dec-1", "profile_id": CLIENT_ID, "kind": "allocation"}
    assert response["rounds"] == [{"round": 1, "verdicts": {"risk": "support"}, "amendments": [{"kind": "flag_only"}]}]
    assert response["strategy"] == {"style": "dynamique", "applied": True}
    [call] = engine.calls
    assert call["as_of"] == date(2026, 11, 12) and call["request"] == FakeRequest("TSLA", 50000)
    assert call["guardrail_id"] == "gr1" and call["guardrail_version"] == "3"
    assert call["grounding_docs"] == [("general/methodologie/m.md", "méthode")]  # source de l'ancrage
    # Étape 0 active par défaut : variables de style lues dans la vue du profil, comme finance/debate/app.py.
    assert call["strategy"] is True and call["style_preference"] is None
    assert call["style_inputs"] == ("style-inputs", "growth") and engine.views == [CLIENT_ID]
    # Documents du client lus avec le profil (portefeuille existant) : passés à la version des données.
    assert engine.client_inputs == [{}]
    assert engine.saved == [("dec-1", "pol-1")] and engine.flushed == 1


def test_build_defaults_to_llm_mode_and_the_engine_date(portfolio_settings, store):
    engine = FakeEngine()
    response = service_with(portfolio_settings, store, engine).handle({"action": "build", "client_id": CLIENT_ID})
    assert response["ok"] and response["as_of"] == "2026-09-30" and engine.calls[0]["mode"] == "llm"
    assert engine.calls[0]["request"] is None


def test_style_preference_reaches_the_engine(portfolio_settings, store):
    engine = FakeEngine()
    payload = {"action": "build", "client_id": CLIENT_ID, "style_preference": "offensive", "mode": "rules"}
    response = service_with(portfolio_settings, store, engine).handle(payload)
    assert response["ok"] and engine.calls[0]["style_preference"] == "offensive"


def test_strategy_false_skips_step_zero_and_the_profile_view(portfolio_settings, store):
    engine = FakeEngine()
    payload = {"action": "build", "client_id": CLIENT_ID, "strategy": False, "mode": "rules"}
    response = service_with(portfolio_settings, store, engine).handle(payload)
    assert response["ok"] and response["strategy"] is None
    assert engine.calls[0]["strategy"] is False and engine.calls[0]["style_inputs"] is None and engine.views == []


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ([], "bad_request"),
        ({}, "bad_request"),
        ({"action": "rebalance"}, "unknown_action"),
        ({"action": "build", "client_id": "pas-un-uuid"}, "bad_request"),
        ({"action": "build", "client_id": CLIENT_ID, "as_of": "30/09/2026"}, "bad_request"),
        ({"action": "build", "client_id": CLIENT_ID, "as_of": "2026-02-30"}, "bad_request"),
        ({"action": "build", "client_id": CLIENT_ID, "mode": "yolo"}, "bad_request"),
        ({"action": "build", "client_id": CLIENT_ID, "style_preference": "croissance"}, "bad_request"),
        ({"action": "build", "client_id": CLIENT_ID, "style_preference": 3}, "bad_request"),
        ({"action": "build", "client_id": CLIENT_ID, "strategy": "yes"}, "bad_request"),
        ({"action": "build", "client_id": CLIENT_ID, "request": {"amount_cad": 1}}, "bad_request"),
        ({"action": "build", "client_id": CLIENT_ID, "request": {"ticker": "TSLA", "qty": 1}}, "bad_request"),
        ({"action": "build", "client_id": CLIENT_ID, "request": {"ticker": "TSLA", "weight": "0.5"}}, "bad_request"),
        ({"action": "build", "client_id": "0b9a4c2e-1f3d-4a5b-8c7d-6e5f4a3b2c1d"}, "not_found"),
    ],
)
def test_invalid_builds_are_refused_before_the_engine_runs(portfolio_settings, store, payload, code):
    engine = FakeEngine()
    response = service_with(portfolio_settings, store, engine).handle(payload)
    assert response["ok"] is False and response["error"]["code"] == code, response
    assert engine.calls == []


def test_engine_failures_become_errors_of_the_envelope(portfolio_settings, store):
    engine = FakeEngine()
    loaded = engine.load()

    def boom(*args, **kwargs):
        raise RuntimeError("solver failed")

    loaded["pipeline"].build_portfolio = boom
    from alphaforge.portfolio_service import PortfolioService

    service = PortfolioService(portfolio_settings, store, engine=lambda: loaded)
    response = service.handle({"action": "build", "client_id": CLIENT_ID, "mode": "rules"})
    assert response["error"]["code"] == "internal" and engine.flushed == 1


def test_rules_build_end_to_end_with_the_real_engine(portfolio_settings, store):
    """Seulement avec le groupe finance installé (uv sync --group finance) : profil réel, mode rules, sans AWS."""
    pytest.importorskip("cvxpy")
    pytest.importorskip("pandas")
    from .conftest import answer_base, make_service

    profile_settings = Settings.from_env({"AGENT_ROLE": "profile", "ALPHAFORGE_STORE": "local"})
    profile = make_service(profile_settings, store)
    client_id = profile.handle({"action": "session.start", "locale": "fr"})["client_id"]
    answer_base(profile, client_id)
    response = build_service(portfolio_settings, app=None, store=store).handle(
        {"action": "build", "client_id": client_id, "mode": "rules"}
    )
    assert response["ok"], response
    assert store.exists(response["decision_key"])
    assert store.exists(response["decision_key"].removesuffix(".md") + ".json")
    assert "strategy" in response  # résumé de l'étape 0, ou null si elle ne s'est pas appliquée
