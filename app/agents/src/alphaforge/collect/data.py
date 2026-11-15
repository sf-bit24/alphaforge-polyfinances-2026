"""A5, ``DataSpecialist`` : séries macroéconomiques et cotations depuis des sources publiques sans clé.

Outils déterministes : API Valet de la Banque du Canada, ``fredgraph.csv`` de FRED, graphique JSON de Yahoo Finance.
Le titre et le résumé de chaque élément sont écrits par le code à partir des valeurs reçues; l'agent ne rédige
qu'une note de pertinence, sans chiffre.

Dates : ``observed_at`` est la date de la dernière observation (le mois de référence pour un IPC). Ces API ne
donnent pas la date de publication d'une valeur : ``published_at`` vaut alors l'horodatage de récupération, qui en
est une borne supérieure sûre (``data.published_at_basis = "retrieved_at_upper_bound"``). Pour une cotation,
``published_at`` est l'heure du dernier cours (``regularMarketTime``) donnée par Yahoo Finance.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from strands import tool

from .. import clock
from ..agentkit import AgentSpec, ModelFactory, run_agent, tool_result
from ..store import Store
from ..trace import Trace
from . import fetchers, staging

UNITS_FR = {"percent": "%", "CAD per USD": "CAD pour 1 USD", "index": "points d'indice"}
PROVIDER_NAMES = {
    "boc": "Banque du Canada (API Valet)",
    "fred": "FRED, Federal Reserve Bank of St. Louis",
    "yahoo": "Yahoo Finance",
}
MAX_OBSERVATIONS = 30

SYSTEM_PROMPT = """You are A5, the DataSpecialist of AlphaForge AI, a simulation-only decision-support prototype. You \
collect dated macroeconomic series and market quotes for a general knowledge base that explains investment context \
to Canadian retail investors. You only use the deterministic fetch tools; you never invent a value or a date.

Steps:
1. Fetch the Bank of Canada series (policy rate V39079, Government of Canada 2-year and 10-year yields, Canada CPI \
STATIC_TOTALCPICHANGE, USD/CAD FXUSDCAD) and the FRED series (DFF, DGS2, DGS10, CPIAUCSL, UNRATE).
2. Fetch the last closes of the run's tickers with fetch_quotes (batches of at most 16).
3. Call stage_data for every fetched series or quote that has observations, with a one-sentence neutral French \
note on what it measures and why it gives context to investors. The note contains no number and no forecast.
4. Call finish with a one-sentence note.

Run window starts {since}. Tickers: {tickers}.
"""


@dataclass
class DataRun:
    run_id: str
    since: str
    tickers: list[str]
    store: Store
    deadline: float
    fetched: dict[str, Any] = field(default_factory=dict)
    staged: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    finished: bool = False

    def _expired(self) -> bool:
        return time.monotonic() > self.deadline

    def _start(self) -> str:
        # Fenêtre élargie pour que les séries mensuelles aient au moins quelques observations.
        return (date.fromisoformat(self.since) - timedelta(days=120)).isoformat()

    def _series_brief(self, data: fetchers.SeriesData) -> dict[str, Any]:
        fid = f"s:{data.provider}:{data.series_id}"
        self.fetched[fid] = data
        recent = [o for o in data.observations if o["date"] >= self.since]
        return {
            "fetch_id": fid,
            "series_id": data.series_id,
            "label": data.label,
            "unit": data.unit,
            "frequency": data.frequency,
            "observations": len(data.observations),
            "in_window": len(recent),
            "latest": data.latest,
        }

    def tools(self) -> list[Any]:
        run = self

        @tool(
            name="fetch_boc_series",
            description="Fetch Bank of Canada Valet series. Allowed: " + ", ".join(fetchers.BOC_SERIES),
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "series_ids": {"type": "array", "items": {"type": "string", "enum": list(fetchers.BOC_SERIES)}}
                    },
                    "required": ["series_ids"],
                }
            },
        )
        def fetch_boc_series(series_ids: list[str]) -> str:
            if run._expired():
                return tool_result({"status": "error", "reason": "time budget exhausted; call finish"})
            wanted = [s for s in dict.fromkeys(series_ids) if s in fetchers.BOC_SERIES]
            if not wanted:
                return tool_result({"status": "error", "reason": "no allowed series"})
            try:
                result = fetchers.fetch_boc(wanted, run._start())
            except (fetchers.FetchError, ValueError) as exc:
                run.warnings.append(f"boc: {exc}")
                return tool_result({"status": "error", "reason": str(exc)})
            return tool_result({"status": "ok", "series": [run._series_brief(d) for d in result.values()]})

        @tool(
            name="fetch_fred_series",
            description="Fetch FRED series (fredgraph.csv). Allowed: " + ", ".join(fetchers.FRED_SERIES),
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "series_ids": {"type": "array", "items": {"type": "string", "enum": list(fetchers.FRED_SERIES)}}
                    },
                    "required": ["series_ids"],
                }
            },
        )
        def fetch_fred_series(series_ids: list[str]) -> str:
            if run._expired():
                return tool_result({"status": "error", "reason": "time budget exhausted; call finish"})
            wanted = [s for s in dict.fromkeys(series_ids) if s in fetchers.FRED_SERIES]
            out, errors = [], []
            for series_id in wanted:
                try:
                    out.append(run._series_brief(fetchers.fetch_fred(series_id, run._start())))
                except (fetchers.FetchError, ValueError) as exc:
                    errors.append({"series_id": series_id, "error": str(exc)})
                    run.warnings.append(f"fred {series_id}: {exc}")
            return tool_result({"status": "ok", "series": out, "errors": errors})

        @tool(
            name="fetch_quotes",
            description="Fetch the last daily closes of up to 16 tickers of the run from Yahoo Finance.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {"tickers": {"type": "array", "items": {"type": "string"}, "maxItems": 16}},
                    "required": ["tickers"],
                }
            },
        )
        def fetch_quotes(tickers: list[str]) -> str:
            if run._expired():
                return tool_result({"status": "error", "reason": "time budget exhausted; call finish"})
            wanted = [t for t in dict.fromkeys(tickers) if t in run.tickers][:16]

            def one(symbol: str) -> tuple[str, Any]:
                try:
                    return symbol, fetchers.fetch_yahoo_chart(symbol)
                except fetchers.FetchError as exc:
                    return symbol, exc

            out, errors = [], []
            with ThreadPoolExecutor(max_workers=6) as pool:
                for symbol, quote in pool.map(one, wanted):
                    if isinstance(quote, Exception):
                        errors.append(symbol)
                        continue
                    fid = f"q:{quote.symbol}"
                    run.fetched[fid] = quote
                    out.append(
                        {
                            "fetch_id": fid,
                            "symbol": quote.symbol,
                            "currency": quote.currency,
                            "last_close": quote.last_close,
                            "last_date": quote.last_date,
                        }
                    )
            return tool_result({"status": "ok", "quotes": out, "failed": errors})

        @tool(
            name="stage_data",
            description=(
                "Stage fetched series or quotes. Each item: fetch_id and a neutral French note without numbers."
            ),
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"fetch_id": {"type": "string"}, "note": {"type": "string"}},
                                "required": ["fetch_id", "note"],
                            },
                        }
                    },
                    "required": ["items"],
                }
            },
        )
        def stage_data(items: list[dict[str, Any]]) -> str:
            return tool_result(run._stage(items))

        @tool(
            name="finish",
            description="End the collection with a one-sentence note.",
            inputSchema={"json": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}},
            context=True,
        )
        def finish(note: str, tool_context) -> str:
            run.finished = True
            tool_context.agent.cancel(after_current_tools=True)
            return tool_result({"status": "ok", "staged": len(run.staged)})

        return [fetch_boc_series, fetch_fred_series, fetch_quotes, stage_data, finish]

    def _stage(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        results = []
        for entry in items:
            fid = entry.get("fetch_id") if isinstance(entry, dict) else None
            fetched = self.fetched.get(fid) if isinstance(fid, str) else None
            if fetched is None:
                results.append({"fetch_id": fid, "status": "error", "reason": "unknown fetch_id"})
                continue
            note = " ".join(str(entry.get("note") or "").split())[:300]
            item = (
                series_item(fetched, note, self.run_id)
                if isinstance(fetched, fetchers.SeriesData)
                else quote_item(fetched, note, self.run_id)
            )
            if item is None:
                results.append({"fetch_id": fid, "status": "error", "reason": "no observation"})
                continue
            key = staging.item_key(self.run_id, "data", item["id"])
            self.store.put_json(key, item)
            self.staged[item["id"]] = key
            results.append({"fetch_id": fid, "status": "ok", "id": item["id"]})
        return {"results": results, "staged": len(self.staged)}


def _number_fr(value: float) -> str:
    text = f"{value:,.4f}".rstrip("0").rstrip(".")
    return text.replace(",", " ").replace(".", ",")


def series_item(data: fetchers.SeriesData, note: str, run_id: str) -> dict[str, Any] | None:
    latest = data.latest
    if latest is None:
        return None
    retrieved = clock.iso()
    unit = UNITS_FR.get(data.unit, data.unit)
    value = _number_fr(latest["value"])
    observations = data.observations[-MAX_OBSERVATIONS:]
    reference = "mois de référence" if data.frequency == "monthly" else "observation"
    summary = (
        f"Dernière valeur : {value} {unit} ({reference} {latest['date']}), source {PROVIDER_NAMES[data.provider]}. "
        f"{len(observations)} observations retenues. Date de publication exacte non fournie par la source : "
        "la date de récupération en est la borne supérieure."
    )
    if note:
        summary += f" Pertinence (A5) : {note}"
    return staging.new_item(
        item_id=f"series-{staging.series_slug(data.series_id)}-{latest['date']}",
        kind="series",
        title=f"{data.label} : {value} {unit} au {latest['date']}",
        url=data.url,
        source=PROVIDER_NAMES[data.provider],
        published_at=retrieved,
        observed_at=latest["date"],
        retrieved_at=retrieved,
        language="fr",
        tickers=[],
        summary=summary,
        data={
            "series_id": data.series_id,
            "provider": data.provider,
            "label": data.label,
            "unit": data.unit,
            "frequency": data.frequency,
            "observations": observations,
            "latest": latest,
            "published_at_basis": "retrieved_at_upper_bound",
            "note": note,
            "collected_by": "A5",
            "run_id": run_id,
        },
    )


def quote_item(quote: fetchers.Quote, note: str, run_id: str) -> dict[str, Any] | None:
    if quote.last_close is None or quote.last_date is None:
        return None
    retrieved = clock.iso()
    published = quote.market_time or retrieved
    if published > retrieved:
        published = retrieved
    closes = quote.closes[-22:]
    value = _number_fr(quote.last_close)
    summary = (
        f"Dernière clôture : {value} {quote.currency or ''} le {quote.last_date} "
        f"({quote.exchange or 'bourse non précisée'}), source Yahoo Finance; {len(closes)} clôtures quotidiennes."
    )
    if note:
        summary += f" Pertinence (A5) : {note}"
    return staging.new_item(
        item_id=f"quote-{staging.series_slug(quote.symbol)}-{quote.last_date}",
        kind="quote",
        title=f"Clôture de {quote.symbol} : {value} {quote.currency or ''} au {quote.last_date}".strip(),
        url=quote.url,
        source=PROVIDER_NAMES["yahoo"],
        published_at=published,
        observed_at=quote.last_date,
        retrieved_at=retrieved,
        language="fr",
        tickers=[quote.symbol],
        summary=summary,
        data={
            "symbol": quote.symbol,
            "provider": "yahoo",
            "currency": quote.currency,
            "exchange": quote.exchange,
            "name": quote.name,
            "closes": closes,
            "latest": {"date": quote.last_date, "value": quote.last_close},
            "published_at_basis": "regular_market_time" if quote.market_time else "retrieved_at_upper_bound",
            "note": note,
            "collected_by": "A5",
            "run_id": run_id,
        },
    )


def collect(
    *,
    run_id: str,
    since: str,
    tickers: list[str],
    store: Store,
    trace: Trace,
    model_factory: ModelFactory,
    model_id: str,
    budget_seconds: float = 240,
) -> dict[str, Any]:
    run = DataRun(run_id=run_id, since=since, tickers=tickers, store=store, deadline=time.monotonic() + budget_seconds)
    spec = AgentSpec(
        actor="A5",
        name="DataSpecialist",
        effort="low",
        system_prompt=SYSTEM_PROMPT.replace("{since}", since).replace("{tickers}", ", ".join(tickers)),
        tools=run.tools(),
        max_turns=10,
        max_tokens=8000,
        tool_summaries={"stage_data": lambda i: {"items": len(i.get("items") or [])}},
    )
    run_agent(spec, f"Run {run_id}: collect the data now.", model_factory=model_factory, model_id=model_id, trace=trace)
    if not run.finished:
        run.warnings.append("A5 n'a pas appelé finish (limite de tours ou de temps atteinte)")
    return {"items": len(run.staged), "keys": sorted(run.staged.values()), "warnings": run.warnings}
