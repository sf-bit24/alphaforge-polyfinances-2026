"""Instrumentation ADOT des runtimes (alphaforge/otel.py) : seulement sur drapeau, avant l'application."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from alphaforge import otel

AGENTS_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(otel, "state", {"active": False})
    for name in ("AGENT_OBSERVABILITY_ENABLED", "OTEL_PYTHON_DISTRO", "OTEL_PYTHON_CONFIGURATOR"):
        monkeypatch.delenv(name, raising=False)
    calls = []
    import opentelemetry.instrumentation.auto_instrumentation as auto

    monkeypatch.setattr(auto, "initialize", lambda **kwargs: calls.append(kwargs))
    return calls


def test_start_does_nothing_without_the_flag(fresh, monkeypatch):
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")
    assert otel.start() is False
    assert fresh == [] and "OTEL_PYTHON_DISTRO" not in os.environ


def test_start_picks_the_aws_distro_once(fresh, monkeypatch):
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "True")
    monkeypatch.setenv("OTEL_PYTHON_CONFIGURATOR", "custom")
    assert otel.start() is True
    assert otel.start() is True
    assert fresh == [{"swallow_exceptions": True}]
    assert os.environ["OTEL_PYTHON_DISTRO"] == "aws_distro"
    assert os.environ["OTEL_PYTHON_CONFIGURATOR"] == "custom"


def test_main_instruments_the_app_and_strands(tmp_path):
    """main.py avec le drapeau, dans un processus à part (le TracerProvider global ne se pose qu'une fois)."""
    script = textwrap.dedent(
        """
        import sys
        import main
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        from starlette.testclient import TestClient
        from strands import Agent

        from alphaforge.finance.observability import telemetry
        from tests.conftest import ScriptedModel

        provider = trace.get_tracer_provider()
        assert isinstance(provider, TracerProvider), type(provider)
        memory = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(memory))
        assert TestClient(main.app).post("/invocations", json={"action": "health"}).json()["ok"]
        Agent(model=ScriptedModel([[("text", "bonjour", None)]]), callback_handler=None)("salut")
        assert telemetry.setup() is provider
        spans = {span.name: dict(span.attributes or {}) for span in memory.get_finished_spans()}
        assert "POST /invocations" in spans, sorted(spans)
        assert spans["chat"]["gen_ai.usage.total_tokens"] == 15, spans["chat"]
        sys.stderr.write("instrumented\\n")
        """
    )
    env = {
        **os.environ,
        "AGENT_OBSERVABILITY_ENABLED": "true",
        "AWS_REGION": "us-east-1",
        "OTEL_TRACES_EXPORTER": "none",
        "OTEL_LOGS_EXPORTER": "none",
        "OTEL_METRICS_EXPORTER": "none",
        "AGENT_ROLE": "profile",
        "ALPHAFORGE_STORE": "local",
        "ALPHAFORGE_LOCAL_DIR": str(tmp_path / "kb"),
    }
    result = subprocess.run(  # noqa: S603 (interpréteur courant, script fixe)
        [sys.executable, "-c", script], cwd=AGENTS_DIR, env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert "instrumented" in result.stderr
    assert "otel=on" in result.stderr
