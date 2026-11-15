"""Runtime portfolio en production : personas FICTION de démo et chaîne d'audit optionnelle."""

import pytest

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


# --------------------------------------------------------------------------- trace X-Ray de la décision

OTEL_ID = "6a1f0c3e9b2d4f7a8c5e1b3d7f9a2c4e"


class RootSpanTelemetry:
    """Télémétrie factice : enregistre ce qui se passe pendant le span racine."""

    def __init__(self, events):
        self.events = events
        self.open = False

    def span(self, name, **attrs):
        import contextlib

        @contextlib.contextmanager
        def cm():
            self.open = True
            self.events.append(("open", name, attrs))
            yield
            self.open = False
            self.events.append(("close", name))

        return cm()

    def current_ids(self):
        return (OTEL_ID, "1b2c3d4e5f6a7b8c") if self.open else (None, None)

    def flush(self):
        self.events.append(("flush", self.open))


def test_root_span_wraps_build_save_and_audit_then_flushes(portfolio_settings, store, monkeypatch):  # noqa: F811
    events = []
    telemetry = RootSpanTelemetry(events)
    engine = FakeEngine()
    loaded = engine.load()
    loaded["telemetry"] = telemetry
    build = loaded["pipeline"].build_portfolio

    def build_in_span(*args, **kwargs):
        events.append(("build", telemetry.open))
        return build(*args, **kwargs)

    loaded["pipeline"].build_portfolio = build_in_span
    from alphaforge import portfolio_service

    def fake_audit(self, decision):
        events.append(("audit", telemetry.open))
        return {"otel_trace_id": telemetry.current_ids()[0]}

    monkeypatch.setattr(portfolio_service.PortfolioService, "_audit", fake_audit)
    service = portfolio_service.PortfolioService(portfolio_settings, store, engine=lambda: loaded)
    res = service.handle({"action": "build", "persona": "amira", "mode": "rules"})
    assert res["ok"] is True, res
    assert events[0] == ("open", "portfolio.build", {"profile_id": "demo-amira", "persona": "amira", "mode": "rules"})
    assert events[1:] == [("build", True), ("audit", True), ("close", "portfolio.build"), ("flush", False)]
    assert res["audit"]["otel_trace_id"] == OTEL_ID
    assert res["xray_trace_id"] == "1-6a1f0c3e-9b2d4f7a8c5e1b3d7f9a2c4e"


def test_no_trace_id_without_a_tracer(portfolio_settings, store):  # noqa: F811
    res = service_with(portfolio_settings, store, FakeEngine()).handle({"action": "build", "persona": "mateo"})
    assert res["ok"] is True and res["xray_trace_id"] is None


@pytest.mark.parametrize(
    ("otel", "xray"),
    [
        (OTEL_ID, "1-6a1f0c3e-9b2d4f7a8c5e1b3d7f9a2c4e"),
        (None, None),
        ("", None),
        ("XYZ", None),
        (OTEL_ID.upper(), None),
    ],
)
def test_xray_trace_id_format(otel, xray):
    from alphaforge.portfolio_service import xray_trace_id

    assert xray_trace_id(otel) == xray


# Variables de style des personas (demo.yaml) → champ du profil court qu'elles reprennent.
STYLE_FIELDS = {
    "goal": "objective.goal",
    "approach": "preferences.approach",
    "interests": "preferences.interests",
    "exclusions": "preferences.exclusions",
    "exclusion_strictness": "preferences.exclusion_strictness",
    "esg_importance": "preferences.esg_importance",
    "knowledge_level": "knowledge.level",
    "employment_sector": "risk_capacity.employment_sector",
    "hype_reaction": "behavior.hype_reaction",
}


def test_demo_style_inputs_use_the_questionnaire_codes():
    """Un code inconnu passerait sans bruit (StyleInputs ne valide rien) et l'étape 0 l'ignorerait."""
    from alphaforge.finance.personas import catalog
    from alphaforge.profile.questionnaire import Questionnaire

    questionnaire = Questionnaire.load()
    for persona, spec in catalog().items():
        for key, value in spec["style_inputs"].items():
            assert key in STYLE_FIELDS, f"{persona}: {key} sans champ du questionnaire"
            assert questionnaire.validate_field_value(STYLE_FIELDS[key], value) == value, (persona, key)
