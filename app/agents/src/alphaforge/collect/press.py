"""A4, ``PressSpecialist`` : collecte des actualités datées depuis des sources publiques sans clé.

L'agent appelle des outils déterministes (manchettes Yahoo Finance par titre, recherche Google Actualités, GDELT),
choisit les éléments pertinents et rédige un résumé neutre fondé sur le titre et l'extrait seulement. Le code
recopie l'adresse, la source et les dates depuis la réponse de la source : le modèle n'en invente aucune.
Bornes d'un passage : 30 éléments, 6 recherches, 31 titres, délai global (4 minutes par défaut).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from strands import tool

from .. import clock
from ..agentkit import AgentSpec, ModelFactory, run_agent, tool_result
from ..store import Store
from ..trace import Trace
from . import fetchers, staging

MAX_ITEMS = 30
MAX_SEARCHES = 6
MAX_TICKERS_PER_CALL = 12

SYSTEM_PROMPT = """You are A4, the PressSpecialist of AlphaForge AI, a simulation-only decision-support prototype. You \
collect recent, factual, finance-relevant news for a general knowledge base used to explain investment context to \
Canadian retail investors. You have deterministic fetch tools; you never browse freely and never invent a URL, a \
source or a date.

Steps:
1. Call fetch_ticker_headlines for the run's tickers (batches of at most 12).
2. Run 2 to 4 searches with search_news on the market context: Bank of Canada and interest rates, inflation in \
Canada or the United States, trade and tariffs, the TSX and US markets; use google_news (language fr or en) and \
optionally gdelt.
3. Call stage_news with the best items, at most {max_items} in total: factual news about companies, sectors, \
markets or economic policy, from credible sources, published inside the run window. Skip duplicates (the same event \
from several sources: keep one), opinion pieces, promotional content, price-prediction articles and listicles.
4. For each staged item write `summary`: one or two neutral sentences in French based only on the title and \
snippet you were given. No advice, no prediction, no number that is not in the title or snippet.
5. Call finish with a one-sentence note.

Run window: news published on or after {since}. Tickers: {tickers}.
"""


@dataclass
class PressRun:
    run_id: str
    since: str
    tickers: list[str]
    store: Store
    deadline: float
    candidates: dict[str, fetchers.NewsCandidate] = field(default_factory=dict)
    staged: dict[str, str] = field(default_factory=dict)
    searches: int = 0
    warnings: list[str] = field(default_factory=list)
    finished: bool = False

    def _expired(self) -> bool:
        return time.monotonic() > self.deadline

    def _since_dt(self) -> datetime:
        return datetime.fromisoformat(self.since).replace(tzinfo=UTC)

    def _keep(self, candidate: fetchers.NewsCandidate) -> bool:
        published = clock.parse_datetime(candidate.published_at)
        return published is not None and published >= self._since_dt()

    def _add(self, items: list[fetchers.NewsCandidate]) -> list[dict[str, Any]]:
        out = []
        for candidate in items:
            if not self._keep(candidate):
                continue
            cid = "c" + staging.short_hash(staging.normalize_url(candidate.url), 10)
            existing = self.candidates.get(cid)
            if existing is not None:
                for ticker in candidate.tickers:
                    if ticker not in existing.tickers:
                        existing.tickers.append(ticker)
                continue
            self.candidates[cid] = candidate
            out.append(
                {
                    "cid": cid,
                    "title": candidate.title,
                    "source": candidate.source,
                    "published_at": candidate.published_at,
                    "tickers": candidate.tickers,
                    "snippet": candidate.snippet[:240],
                    "language": candidate.language,
                }
            )
        out.sort(key=lambda item: item["published_at"], reverse=True)
        return out

    def tools(self) -> list[Any]:
        run = self

        @tool(
            name="fetch_ticker_headlines",
            description="Fetch recent Yahoo Finance headlines for up to 12 tickers of the run. Returns candidates.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "tickers": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_TICKERS_PER_CALL}
                    },
                    "required": ["tickers"],
                }
            },
        )
        def fetch_ticker_headlines(tickers: list[str]) -> str:
            if run._expired():
                return tool_result({"status": "error", "reason": "time budget exhausted; call finish"})
            wanted = [t for t in tickers if t in run.tickers][:MAX_TICKERS_PER_CALL]
            if not wanted:
                return tool_result({"status": "error", "reason": f"tickers must be among {run.tickers}"})
            results: list[fetchers.NewsCandidate] = []
            errors = []

            def one(symbol: str) -> tuple[str, list[fetchers.NewsCandidate] | None]:
                try:
                    return symbol, fetchers.fetch_yahoo_headlines(symbol)
                except fetchers.FetchError:
                    return symbol, None

            with ThreadPoolExecutor(max_workers=6) as pool:
                for symbol, items in pool.map(one, wanted):
                    if items is None:
                        errors.append(symbol)
                    else:
                        results.extend(items)
            fresh = run._add(results)
            return tool_result(
                {
                    "status": "ok",
                    "candidates": fresh[:60],
                    "failed_tickers": errors,
                    "total_candidates": len(run.candidates),
                }
            )

        @tool(
            name="search_news",
            description=(
                "Search news. provider: google_news (language fr or en) or gdelt. Returns candidates "
                "published inside the run window."
            ),
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "provider": {"type": "string", "enum": ["google_news", "gdelt"]},
                        "language": {"type": "string", "enum": ["fr", "en"]},
                    },
                    "required": ["query", "provider"],
                }
            },
        )
        def search_news(query: str, provider: str, language: str = "fr") -> str:
            if run._expired():
                return tool_result({"status": "error", "reason": "time budget exhausted; call finish"})
            if run.searches >= MAX_SEARCHES:
                return tool_result({"status": "error", "reason": f"at most {MAX_SEARCHES} searches per run"})
            query = " ".join(str(query).split())[:120]
            if len(query) < 3:
                return tool_result({"status": "error", "reason": "query too short"})
            run.searches += 1
            days = max(1, (clock.today() - datetime.fromisoformat(run.since).date()).days + 1)
            try:
                if provider == "gdelt":
                    items = fetchers.fetch_gdelt(query, run._since_dt())
                else:
                    items = fetchers.fetch_google_news(query, days=days, language=language)
            except fetchers.FetchError as exc:
                run.warnings.append(f"{provider}: {exc}")
                return tool_result({"status": "error", "reason": str(exc)})
            fresh = run._add(items)
            return tool_result({"status": "ok", "candidates": fresh[:40], "total_candidates": len(run.candidates)})

        @tool(
            name="stage_news",
            description=(
                "Stage selected candidates for the supervisor. Each item: cid, summary (French, 1-2 "
                "neutral sentences from the title and snippet), optional tickers."
            ),
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "cid": {"type": "string"},
                                    "summary": {"type": "string"},
                                    "tickers": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["cid", "summary"],
                            },
                        }
                    },
                    "required": ["items"],
                }
            },
        )
        def stage_news(items: list[dict[str, Any]]) -> str:
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

        return [fetch_ticker_headlines, search_news, stage_news, finish]

    def _stage(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        results = []
        for entry in items:
            if len(self.staged) >= MAX_ITEMS:
                results.append({"cid": entry.get("cid"), "status": "error", "reason": f"at most {MAX_ITEMS} items"})
                continue
            cid = entry.get("cid") if isinstance(entry, dict) else None
            candidate = self.candidates.get(cid) if isinstance(cid, str) else None
            if candidate is None:
                results.append({"cid": cid, "status": "error", "reason": "unknown cid"})
                continue
            summary = " ".join(str(entry.get("summary") or "").split())[:500]
            if len(summary) < 10:
                results.append({"cid": cid, "status": "error", "reason": "summary too short"})
                continue
            tickers = [t for t in (entry.get("tickers") or candidate.tickers) if t in self.tickers][:8]
            item_id = staging.news_item_id(candidate.url)
            if item_id in self.staged:
                results.append({"cid": cid, "status": "ok", "duplicate": True})
                continue
            item = staging.new_item(
                item_id=item_id,
                kind="news",
                title=candidate.title,
                url=candidate.url,
                source=candidate.source,
                published_at=candidate.published_at,
                observed_at=None,
                retrieved_at=clock.iso(),
                language=candidate.language or "en",
                tickers=tickers,
                summary=summary,
                data={
                    "provider": candidate.provider,
                    "snippet": candidate.snippet,
                    "published_at_basis": candidate.published_at_basis,
                    "summary_by": "agent:A4",
                    "collected_by": "A4",
                    "run_id": self.run_id,
                },
            )
            key = staging.item_key(self.run_id, "press", item_id)
            self.store.put_json(key, item)
            self.staged[item_id] = key
            results.append({"cid": cid, "status": "ok", "id": item_id})
        return {"results": results, "staged": len(self.staged)}


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
    run = PressRun(run_id=run_id, since=since, tickers=tickers, store=store, deadline=time.monotonic() + budget_seconds)
    spec = AgentSpec(
        actor="A4",
        name="PressSpecialist",
        effort="low",
        system_prompt=SYSTEM_PROMPT.replace("{max_items}", str(MAX_ITEMS))
        .replace("{since}", since)
        .replace("{tickers}", ", ".join(tickers)),
        tools=run.tools(),
        max_turns=12,
        max_tokens=8000,
        tool_summaries={"stage_news": lambda i: {"items": len(i.get("items") or [])}},
    )
    run_agent(spec, f"Run {run_id}: collect the news now.", model_factory=model_factory, model_id=model_id, trace=trace)
    if not run.finished:
        run.warnings.append("A4 n'a pas appelé finish (limite de tours ou de temps atteinte)")
    return {"items": len(run.staged), "keys": sorted(run.staged.values()), "warnings": run.warnings}
