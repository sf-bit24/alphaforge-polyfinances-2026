"""Registre des chiffres (Fact) et des étapes (TraceEvent) d'une décision.

Tout nombre montré à un LLM ou à l'utilisateur passe par ``FactBook.add`` : il reçoit un ``fact_id``,
une source et le ``trace_id`` de l'étape qui l'a produit. C'est ce qui rend l'explication vérifiable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any

from alphaforge.finance.contracts.decision import Fact, Source, TraceEvent


def _now() -> datetime:
    return datetime.now(UTC)


def fmt(value: Any, unit: str) -> str:
    """Format affiché (et vérifié) d'un chiffre : 12,3 % ; 31 300 $ ; 4,2 mois."""
    if value is None:
        return "n.d."
    if isinstance(value, str):
        return value
    return _fmt_number(value, unit)


def _fmt_number(value: Any, unit: str) -> str:
    """Nombre à la française selon son unité : virgule décimale, espace entre les milliers."""
    if unit == "%":
        return f"{value * 100:.1f}".replace(".", ",") + " %"
    if unit == "CAD":
        return f"{value:,.0f}".replace(",", " ") + " $"
    if unit in ("mois", "années", "ans"):
        return f"{value:.1f}".replace(".", ",") + f" {unit}"
    if isinstance(value, float):
        return f"{value:.3f}".replace(".", ",")
    return str(value)


class FactBook:
    def __init__(self, decision_id: str, data_version: str | None = None, code_version: str | None = None):
        self.decision_id = decision_id
        self.data_version = data_version
        self.code_version = code_version
        self.facts: dict[str, Fact] = {}
        self.trace: list[TraceEvent] = []
        self._stack: list[str] = []
        self._n = 0

    # --------------------------------------------------------------------- trace
    @contextmanager
    def step(
        self, agent: str, tool: str | None = None, inputs: dict | None = None, model_id: str | None = None
    ) -> Iterator[TraceEvent]:
        self._n += 1
        tid = f"{self.decision_id}:t{self._n:03d}:{agent}" + (f":{tool}" if tool else "")
        ev = TraceEvent(
            trace_id=tid,
            parent_id=self._stack[-1] if self._stack else None,
            agent=agent,
            tool=tool,
            inputs=_jsonable(inputs or {}),
            started_utc=_now(),
            data_version=self.data_version,
            code_version=self.code_version,
            model_id=model_id,
        )
        self.trace.append(ev)
        self._stack.append(tid)
        try:
            yield ev
            ev.status = ev.status or "ok"
        except Exception as exc:  # la trace garde l'échec, puis on relève
            ev.status = "erreur"
            ev.message = f"{type(exc).__name__}: {exc}"[:500]
            raise
        finally:
            ev.ended_utc = _now()
            self._stack.pop()

    @property
    def current(self) -> str:
        if not self._stack:
            raise RuntimeError("FactBook.add hors d'une étape tracée")
        return self._stack[-1]

    # --------------------------------------------------------------------- facts
    def add(  # noqa: PLR0913 - un Fact et sa source : les champs facultatifs sont passés par mot-clé
        self,
        key: str,
        label_fr: str,
        value,
        unit: str,
        *,
        dataset: str,
        processing: str | None = None,
        status: str = "FAIT",
        as_of: date | None = None,
        published: date | None = None,
        currency: str | None = None,
        url: str | None = None,
        licence: str | None = None,
        trace_id: str | None = None,
    ) -> str:
        fid = key if key not in self.facts else f"{key}#{len(self.facts)}"
        tid = trace_id or self.current
        f = Fact(
            fact_id=fid,
            label_fr=label_fr,
            value=_scalar(value),
            unit=unit,
            currency=currency,
            as_of=as_of,
            published=published,
            status=status,
            trace_id=tid,
            sources=[Source(dataset=dataset, url=url, licence=licence, processing=processing)],
        )
        self.facts[fid] = f
        for ev in self.trace:
            if ev.trace_id == tid:
                ev.fact_ids.append(fid)
        return fid

    def absorb(self, facts, trace_event: TraceEvent | None = None) -> list[str]:
        """Intègre des Facts produits ailleurs (ex. le Judge F4) avec leur TraceEvent."""
        if trace_event is not None and all(t.trace_id != trace_event.trace_id for t in self.trace):
            trace_event = trace_event.model_copy()
            trace_event.parent_id = trace_event.parent_id or (self._stack[-1] if self._stack else None)
            self.trace.append(trace_event)
        ids = []
        for f in facts:
            if f.fact_id in self.facts:
                f = f.model_copy(update={"fact_id": f"{f.fact_id}#{len(self.facts)}"})
            self.facts[f.fact_id] = f
            ids.append(f.fact_id)
        return ids

    def absorb_report(self, rep) -> list[str]:
        """Intègre un ``JudgeReport`` : sa trace, puis ses traces enfants (outil scenario_risk de PROB_LOSS), puis ses
        Facts. Sans trace enfant, identique à ``absorb(rep.facts, rep.trace)``."""
        children = tuple(getattr(rep, "child_traces", ()) or ())
        if not children:
            return self.absorb(rep.facts, rep.trace)
        self.absorb([], rep.trace)
        for ev in children:
            self.absorb([], ev)
        return self.absorb(rep.facts)

    def show(self, fact_ids) -> list[dict]:
        """Vue compacte pour un prompt : id, libellé, valeur formatée, statut."""
        out = []
        for fid in fact_ids:
            f = self.facts.get(fid)
            if f is not None:
                out.append({"fact_id": fid, "label": f.label_fr, "value": fmt(f.value, f.unit), "status": f.status})
        return out


def _scalar(v):
    if v is None or isinstance(v, (str, int)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def _jsonable(d: dict) -> dict:
    return json.loads(json.dumps(d, default=str))


def sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()
