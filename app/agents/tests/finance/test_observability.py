"""Traçabilité : vérificateur numérique, journal chaîné, spans OpenTelemetry (sans réseau)."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from alphaforge.finance.contracts import Decision, Fact
from alphaforge.finance.observability import (
    extract_numbers,
    record_decision,
    verify_chain,
    verify_decision,
    verify_numbers,
)

NOW = datetime(2026, 11, 14, tzinfo=UTC)


def fact(fid, v, unit="fraction"):
    return Fact(fact_id=fid, label_fr=fid, value=v, unit=unit, sources=[{"dataset": "test"}], trace_id="t1")


FACTS = [fact("cvar", 0.034), fact("limite", 0.054), fact("perte2022", 41000.0, "CAD"), fact("mdd", 0.31)]


@pytest.mark.parametrize("text,ok", [
    ("La CVaR mensuelle est de 3,4 %, sous la limite de 5,4 %.", True),
    ("CVaR de 0,034 contre une limite de 0.054.", True),
    ("En 2022, la perte aurait été de 41 000 $.", True),
    ("Le drawdown maximal atteint -31 %.", True),
    ("La CVaR est de 9,1 %.", False),                         # chiffre inventé
    ("La perte serait de 45 000 $.", False),
    ("Selon judge-check:risk.cvar_m:max, la CVaR est de 3,4 % (données 2018-10 à 2026-09).", True),
])
def test_number_verifier(text, ok):
    assert verify_numbers(text, FACTS).ok is ok


def test_extract_ignores_years_and_dates():
    vals = [c.value for c in extract_numbers("Depuis 1971 et le 2022-08-22, la CVaR vaut 3,4 %.")]
    assert vals == [3.4]


def _decision(text, cited):
    st = [{"text_fr": text, "fact_ids": cited}]
    return Decision(decision_id="d1", profile_id="p1", profile_version=1, created_utc=NOW, kind="refus_encadre",
                    facts=FACTS, explanation={"data_used": st, "why": st, "limits": st, "what_would_change": st},
                    trace=[{"trace_id": "t1", "agent": "test", "started_utc": NOW}])


def test_decision_numbers_must_come_from_cited_facts():
    assert verify_decision(_decision("CVaR de 3,4 %.", ["cvar"])).ok
    # 3,4 % existe dans les faits mais la phrase ne cite pas ce fait : refusé
    assert not verify_decision(_decision("CVaR de 3,4 %.", ["limite"])).ok


def test_audit_chain_detects_tampering(tmp_path):
    for i in range(3):
        d = _decision("CVaR de 3,4 %.", ["cvar"]).model_copy(update={"decision_id": f"d{i}"})
        record_decision(d, str(tmp_path))
    assert verify_chain(str(tmp_path), "p1") == (True, None)
    path = tmp_path / "p1.jsonl"
    lines = path.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["decision"]["kind"] = "proposition"                    # falsification a posteriori
    lines[1] = json.dumps(rec)
    path.write_text("\n".join(lines) + "\n")
    assert verify_chain(str(tmp_path), "p1") == (False, 1)


def test_tool_spans_are_exported_with_hashes(tmp_path, monkeypatch):
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    from alphaforge.finance.observability.telemetry import JsonlSpanExporter, span, traced_tool

    out = tmp_path / "spans.jsonl"
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(JsonlSpanExporter(str(out))))
    monkeypatch.setattr(trace, "get_tracer", lambda *a, **k: provider.get_tracer("t"))

    @traced_tool("demo.add", lambda r: {"result": r})
    def add(a, b):
        return a + b

    with span("decision", decision_id="d1"):
        assert add(2, 3) == 5
    spans = [json.loads(line) for line in out.read_text().splitlines()]
    tool = next(s for s in spans if s["name"] == "tool demo.add")
    parent = next(s for s in spans if s["name"] == "decision")
    assert tool["parent_id"] == parent["span_id"] and tool["trace_id"] == parent["trace_id"]
    assert len(tool["attributes"]["alphaforge.input.sha256"]) == 64
    assert tool["attributes"]["alphaforge.result"] == 5
