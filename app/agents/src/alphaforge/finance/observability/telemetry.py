"""Télémétrie AlphaForge AI : traces OpenTelemetry (conventions GenAI) et journaux structurés.

Un seul TracerProvider global, partagé par Strands (qui émet déjà des spans ``gen_ai.*`` pour les
agents, les appels de modèle et les outils) et par notre code (outils F2-F4, llm_call, vérifications).

Destinations (cumulables) :
- fichier JSONL local (``ALPHAFORGE_TRACE_FILE``) : arbre de traces pour l'interface, et preuve
  conservée après la suppression du compte AWS ;
- AWS X-Ray / CloudWatch Transaction Search via OTLP HTTP signé SigV4 (``ALPHAFORGE_OTLP_XRAY=1``) ;
- console (``ALPHAFORGE_TRACE_CONSOLE=1``).
Journaux applicatifs structurés : ``log_event`` → JSONL local et CloudWatch Logs ``/alphaforge/app``.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

SERVICE = "alphaforge-finance"
REGION = os.environ.get("AWS_REGION", "us-east-1")
_LOCK = threading.Lock()
_PROVIDER: TracerProvider | None = None


def canonical_hash(obj: Any) -> str:
    """sha256 d'une forme canonique (clés triées) : empreinte des entrées et sorties d'une étape."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- exportateurs

class JsonlSpanExporter(SpanExporter):
    """Un span par ligne JSON (trace_id, span_id, parent, nom, durée, attributs, événements, statut)."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        with _LOCK, open(self.path, "a", encoding="utf-8") as f:
            for s in spans:
                ctx = s.get_span_context()
                f.write(json.dumps({
                    "trace_id": f"{ctx.trace_id:032x}", "span_id": f"{ctx.span_id:016x}",
                    "parent_id": f"{s.parent.span_id:016x}" if s.parent else None, "name": s.name,
                    "start_utc": datetime.fromtimestamp(s.start_time / 1e9, UTC).isoformat(),
                    "duration_ms": round((s.end_time - s.start_time) / 1e6, 2),
                    "status": s.status.status_code.name, "attributes": dict(s.attributes or {}),
                    "events": [{"name": e.name, "attributes": dict(e.attributes or {})} for e in s.events],
                }, ensure_ascii=False, default=str) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def _xray_exporter():
    """OTLP HTTP vers X-Ray, requêtes signées SigV4 (service « xray »)."""
    import boto3
    import requests
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    creds = boto3.Session().get_credentials()

    class SigV4Session(requests.Session):
        def request(self, method, url, data=None, headers=None, **kw):
            req = AWSRequest(method=method, url=url, data=data, headers=dict(headers or {}))
            SigV4Auth(creds.get_frozen_credentials(), "xray", REGION).add_auth(req)
            return super().request(method, url, data=data, headers=dict(req.headers), **kw)

    return OTLPSpanExporter(endpoint=f"https://xray.{REGION}.amazonaws.com/v1/traces", session=SigV4Session())


def setup(trace_file: str | None = None, xray: bool | None = None, console: bool | None = None,
          attributes: dict | None = None) -> TracerProvider:
    """Configure (une seule fois) le TracerProvider global. Idempotent."""
    global _PROVIDER
    if _PROVIDER is not None:
        return _PROVIDER
    trace_file = trace_file or os.environ.get("ALPHAFORGE_TRACE_FILE")
    xray = os.environ.get("ALPHAFORGE_OTLP_XRAY") == "1" if xray is None else xray
    console = os.environ.get("ALPHAFORGE_TRACE_CONSOLE") == "1" if console is None else console
    res = Resource.create({"service.name": SERVICE, "service.namespace": "alphaforge",
                           "deployment.environment": os.environ.get("ALPHAFORGE_ENV", "dev"),
                           **(attributes or {})})
    provider = TracerProvider(resource=res)
    if trace_file:
        provider.add_span_processor(SimpleSpanProcessor(JsonlSpanExporter(trace_file)))
    if xray:
        provider.add_span_processor(BatchSpanProcessor(_xray_exporter()))
    if console:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _PROVIDER = provider
    return provider


def flush() -> None:
    if _PROVIDER is not None:
        _PROVIDER.force_flush()


def tracer():
    return trace.get_tracer("alphaforge.finance")


def current_ids() -> tuple[str | None, str | None]:
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None, None
    return f"{ctx.trace_id:032x}", f"{ctx.span_id:016x}"


# --------------------------------------------------------------------------- outils tracés

def traced_tool(name: str, summarize: Callable[[Any], dict] | None = None):
    """Span par appel d'outil déterministe : empreinte des entrées et de la sortie, durée, erreur.
    ``summarize(result)`` ajoute des attributs lisibles (statut, verdict, nombre de faits…)."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            with tracer().start_as_current_span(f"tool {name}") as span:
                span.set_attribute("gen_ai.operation.name", "execute_tool")
                span.set_attribute("gen_ai.tool.name", name)
                span.set_attribute("alphaforge.tool.deterministic", True)
                span.set_attribute("alphaforge.input.sha256", canonical_hash(
                    {"args": [_jsonable(a) for a in args], "kwargs": {k: _jsonable(v) for k, v in kwargs.items()}}))
                t0 = time.perf_counter()
                try:
                    result = fn(*args, **kwargs)
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)[:200]))
                    raise
                span.set_attribute("alphaforge.output.sha256", canonical_hash(_jsonable(result)))
                span.set_attribute("alphaforge.duration_ms", round((time.perf_counter() - t0) * 1e3, 2))
                for k, v in (summarize(result) if summarize else {}).items():
                    span.set_attribute(f"alphaforge.{k}", v)
                return result
        return wrapper
    return deco


def _jsonable(x: Any) -> Any:
    if hasattr(x, "model_dump"):
        return x.model_dump(mode="json")
    if hasattr(x, "__dataclass_fields__"):
        from dataclasses import asdict
        try:
            return asdict(x)
        except TypeError:
            return repr(x)
    if hasattr(x, "to_dict"):
        try:
            return x.to_dict()
        except Exception:
            return repr(x)
    return x


# --------------------------------------------------------------------------- journaux structurés

class _CloudWatchSink:
    def __init__(self, group: str = "/alphaforge/app"):
        import boto3
        self.logs, self.group = boto3.client("logs", region_name=REGION), group
        self.stream = f"{SERVICE}-{datetime.now(UTC):%Y%m%dT%H%M%S}-{os.getpid()}"
        self.logs.create_log_stream(logGroupName=group, logStreamName=self.stream)

    def put(self, record: dict) -> None:
        self.logs.put_log_events(logGroupName=self.group, logStreamName=self.stream, logEvents=[
            {"timestamp": int(time.time() * 1000), "message": json.dumps(record, ensure_ascii=False, default=str)}])


_SINK = None


def log_event(event: str, **fields) -> dict:
    """Événement applicatif structuré, corrélé à la trace courante (JSONL + CloudWatch si activé)."""
    global _SINK
    tid, sid = current_ids()
    rec = {"ts_utc": datetime.now(UTC).isoformat(), "service": SERVICE, "event": event,
           "trace_id": tid, "span_id": sid, **fields}
    path = os.environ.get("ALPHAFORGE_LOG_FILE")
    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with _LOCK, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    if os.environ.get("ALPHAFORGE_CLOUDWATCH_LOGS") == "1":
        if _SINK is None:
            _SINK = _CloudWatchSink()
        _SINK.put(rec)
    span = trace.get_current_span()
    if span.get_span_context().is_valid:
        span.add_event(event, {k: v if isinstance(v, (str, int, float, bool)) else json.dumps(v, default=str)
                               for k, v in fields.items()})
    return rec


@contextmanager
def span(name: str, **attrs):
    with tracer().start_as_current_span(name) as s:
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(k if "." in k else f"alphaforge.{k}", v)
        yield s
