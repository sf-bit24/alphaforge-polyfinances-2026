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
from collections.abc import Iterable
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
# Environ un mois de séances.
MAX_CLOSES = 22
MAX_QUOTES_PER_CALL = 16
MAX_NOTE_CHARS = 300
QUOTE_WORKERS = 6
# Les séries mensuelles n'ont que quelques observations dans la fenêtre du passage : on lit plus loin en arrière.
WINDOW_MARGIN_DAYS = 120
BUDGET_EXHAUSTED = {"status": "error", "reason": "time budget exhausted; call finish"}


def _series_ids_schema(allowed: Iterable[str]) -> dict[str, Any]:
    return {
        "json": {
            "type": "object",
            "properties": {"series_ids": {"type": "array", "items": {"type": "string", "enum": list(allowed)}}},
            "required": ["series_ids"],
        }
    }


FETCH_QUOTES_SCHEMA = {
    "json": {
        "type": "object",
        "properties": {"tickers": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_QUOTES_PER_CALL}},
        "required": ["tickers"],
    }
}
STAGE_DATA_SCHEMA = {
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
}
FINISH_SCHEMA = {"json": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}}

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

    def _is_expired(self) -> bool:
        return time.monotonic() > self.deadline

    def _window_start(self) -> str:
        return (date.fromisoformat(self.since) - timedelta(days=WINDOW_MARGIN_DAYS)).isoformat()

    def _series_brief(self, data: fetchers.SeriesData) -> dict[str, Any]:
        fetch_id = f"s:{data.provider}:{data.series_id}"
        self.fetched[fetch_id] = data
        recent = [observation for observation in data.observations if observation["date"] >= self.since]
        return {
            "fetch_id": fetch_id,
            "series_id": data.series_id,
            "label": data.label,
            "unit": data.unit,
            "frequency": data.frequency,
            "observations": len(data.observations),
            "in_window": len(recent),
            "latest": data.latest,
        }

    def _quote_brief(self, quote: fetchers.Quote) -> dict[str, Any]:
        fetch_id = f"q:{quote.symbol}"
        self.fetched[fetch_id] = quote
        return {
            "fetch_id": fetch_id,
            "symbol": quote.symbol,
            "currency": quote.currency,
            "last_close": quote.last_close,
            "last_date": quote.last_date,
        }

    def tools(self) -> list[Any]:
        run = self

        @tool(
            name="fetch_boc_series",
            description="Fetch Bank of Canada Valet series. Allowed: " + ", ".join(fetchers.BOC_SERIES),
            inputSchema=_series_ids_schema(fetchers.BOC_SERIES),
        )
        def fetch_boc_series(series_ids: list[str]) -> str:
            return tool_result(run._fetch_boc_series(series_ids))

        @tool(
            name="fetch_fred_series",
            description="Fetch FRED series (fredgraph.csv). Allowed: " + ", ".join(fetchers.FRED_SERIES),
            inputSchema=_series_ids_schema(fetchers.FRED_SERIES),
        )
        def fetch_fred_series(series_ids: list[str]) -> str:
            return tool_result(run._fetch_fred_series(series_ids))

        @tool(
            name="fetch_quotes",
            description="Fetch the last daily closes of up to 16 tickers of the run from Yahoo Finance.",
            inputSchema=FETCH_QUOTES_SCHEMA,
        )
        def fetch_quotes(tickers: list[str]) -> str:
            return tool_result(run._fetch_quotes(tickers))

        @tool(
            name="stage_data",
            description=(
                "Stage fetched series or quotes. Each item: fetch_id and a neutral French note without numbers."
            ),
            inputSchema=STAGE_DATA_SCHEMA,
        )
        def stage_data(items: list[dict[str, Any]]) -> str:
            return tool_result(run._stage(items))

        @tool(
            name="finish",
            description="End the collection with a one-sentence note.",
            inputSchema=FINISH_SCHEMA,
            context=True,
        )
        def finish(note: str, tool_context) -> str:
            run.finished = True
            tool_context.agent.cancel(after_current_tools=True)
            return tool_result({"status": "ok", "staged": len(run.staged)})

        return [fetch_boc_series, fetch_fred_series, fetch_quotes, stage_data, finish]

    def _fetch_boc_series(self, series_ids: list[str]) -> dict[str, Any]:
        if self._is_expired():
            return BUDGET_EXHAUSTED
        wanted = [series_id for series_id in dict.fromkeys(series_ids) if series_id in fetchers.BOC_SERIES]
        if not wanted:
            return {"status": "error", "reason": "no allowed series"}
        try:
            fetched = fetchers.fetch_boc(wanted, self._window_start())
        except (fetchers.FetchError, ValueError) as exc:
            self.warnings.append(f"boc: {exc}")
            return {"status": "error", "reason": str(exc)}
        return {"status": "ok", "series": [self._series_brief(data) for data in fetched.values()]}

    def _fetch_fred_series(self, series_ids: list[str]) -> dict[str, Any]:
        if self._is_expired():
            return BUDGET_EXHAUSTED
        wanted = [series_id for series_id in dict.fromkeys(series_ids) if series_id in fetchers.FRED_SERIES]
        briefs, errors = [], []
        for series_id in wanted:
            try:
                briefs.append(self._series_brief(fetchers.fetch_fred(series_id, self._window_start())))
            except (fetchers.FetchError, ValueError) as exc:
                errors.append({"series_id": series_id, "error": str(exc)})
                self.warnings.append(f"fred {series_id}: {exc}")
        return {"status": "ok", "series": briefs, "errors": errors}

    def _fetch_quotes(self, tickers: list[str]) -> dict[str, Any]:
        if self._is_expired():
            return BUDGET_EXHAUSTED
        wanted = [ticker for ticker in dict.fromkeys(tickers) if ticker in self.tickers][:MAX_QUOTES_PER_CALL]
        briefs, failed = [], []
        with ThreadPoolExecutor(max_workers=QUOTE_WORKERS) as pool:
            for symbol, quote in pool.map(_quote_or_error, wanted):
                if isinstance(quote, Exception):
                    failed.append(symbol)
                else:
                    briefs.append(self._quote_brief(quote))
        return {"status": "ok", "quotes": briefs, "failed": failed}

    def _stage(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        results = []
        for entry in items:
            fetch_id = entry.get("fetch_id") if isinstance(entry, dict) else None
            fetched = self.fetched.get(fetch_id) if isinstance(fetch_id, str) else None
            if fetched is None:
                results.append({"fetch_id": fetch_id, "status": "error", "reason": "unknown fetch_id"})
                continue
            note = " ".join(str(entry.get("note") or "").split())[:MAX_NOTE_CHARS]
            item = (
                series_item(fetched, note, self.run_id)
                if isinstance(fetched, fetchers.SeriesData)
                else quote_item(fetched, note, self.run_id)
            )
            if item is None:
                results.append({"fetch_id": fetch_id, "status": "error", "reason": "no observation"})
                continue
            key = staging.item_key(self.run_id, "data", item["id"])
            self.store.put_json(key, item)
            self.staged[item["id"]] = key
            results.append({"fetch_id": fetch_id, "status": "ok", "id": item["id"]})
        return {"results": results, "staged": len(self.staged)}


def _quote_or_error(symbol: str) -> tuple[str, Any]:
    """Cotation du symbole, ou l'erreur de récupération : un échec n'interrompt pas les autres symboles."""
    try:
        return symbol, fetchers.fetch_yahoo_chart(symbol)
    except fetchers.FetchError as exc:
        return symbol, exc


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
    closes = quote.closes[-MAX_CLOSES:]
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


def collect(  # noqa: PLR0913 - même signature que press.collect : le service les appelle avec les mêmes arguments
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
