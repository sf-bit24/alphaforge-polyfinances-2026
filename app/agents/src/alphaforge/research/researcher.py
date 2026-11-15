"""Chercheur (sous-agent) : une mission, une session AgentCore, une microVM.

Il reçoit une mission d'un expert (objectif, preuves voulues, paquets de sources, titres, fenêtre, ``as_of``),
cherche dans les catalogues des sources de ses paquets, lit les réponses par aperçus paginés et consigne des
constats. Un constat est un pointeur : le modèle donne des localisateurs, le code lit les valeurs et les dates
dans la réponse archivée, ajoute la licence et l'attribution de l'hôte, et vérifie les nombres de la phrase.

Écrit ``staging/<run_id>/researchers/<sujet>-<rk>/findings.json``; le service écrit le marqueur ``_done.json``.
"""

from __future__ import annotations

import email.utils
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from strands import tool

from .. import clock
from ..agentkit import AgentSpec, ModelFactory, run_agent, tool_result
from ..errors import AppError
from ..store import Store
from ..trace import Trace
from . import documents, search
from .items import MARKET_HOSTS
from .packs import (
    HOSTS,
    RESEARCHER_BUDGET_S,
    RESEARCHER_MAX_BUDGET_S,
    RESEARCHER_MAX_TOOL_CALLS,
    SUBJECTS,
    pack_hosts,
    pack_sources,
)
from .web import ResearchWeb, WebError

MAX_FINDINGS = 30
MAX_SERIES_ROWS = 60
FINDING_KINDS = ("news", "fact", "signal", "filing", "quote")
REQUIRED_FIELDS = {
    "news": (("title",), ("link", "url")),
    "fact": (("value",),),
    "signal": (("value",),),
    "quote": (("value",),),
    "filing": (("form",), ("accession", "accessionNumber")),
}
RESEARCHER_ID = re.compile(r"^r\d{1,2}$")
_COORDINATE = re.compile(r"^\d{1,4}(\.\d{1,4}){9}$")

SYSTEM_PROMPT = """You are an AlphaForge AI research sub-agent, spawned by the {subject_name} expert ({subject}). \
AlphaForge is a simulation-only decision-support prototype for Canadian retail investors; your findings feed a \
shared general knowledge base after a supervisor checks them.

Mission ({researcher}): {objective}
Evidence wanted: {evidence}
Issuers: {issuers}. Themes: {themes}. Window starts {since}. {as_of_line}

How to research:
1. Discover with search_source (catalogues and search APIs of your packs), or start from a known endpoint below.
2. Read with fetch(url): you get a paged preview of the parsed response as `path = value` lines and a \
response_id. Use view(response_id, offset) for more lines. HTML pages, binary files and hosts outside your packs \
are refused by the code; a refused or blocked host means: use another source, never retry around it.
3. Record evidence with record_finding (one value, a news item, a filing) or record_series (a time series). You \
never type a value or a date: you give locators (paths from the preview, e.g. `observations[3].FXUSDCAD.v`, \
`rows[12].Value`, `items[0].title`) and the code reads them. Prefer a publication date from the source \
(publication_locator); otherwise the retrieval time is used as an upper bound.
4. `claim` is one neutral French sentence stating what the evidence says. Every number in it must appear in the \
values you point to (or their dates). No advice, no forecast, no opinion.
5. If you find a relevant host that is not in your packs, you may propose_host it (at most 2); the code checks its \
robots.txt and its findings stay in quarantine for human review.
6. Stop with finish(summary, gaps): gaps are the evidence you looked for and did not find, in French.

Budget: about {budget_s} seconds and {max_tool_calls} tool calls. Work fast: a few precise findings beat many \
weak ones.

{packs}
"""


class ResearchError(Exception):
    pass


@dataclass
class Brief:
    run_id: str
    subject: str
    researcher: str
    objective: str
    evidence_wanted: list[str]
    packs: list[str]
    issuers: list[str]
    themes: list[str]
    since: str
    as_of: str | None
    budget_s: float
    max_tool_calls: int

    @property
    def prefix(self) -> str:
        return f"staging/{self.run_id}/researchers/{self.subject}-{self.researcher}/"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "subject": self.subject,
            "researcher": self.researcher,
            "objective": self.objective,
            "evidence_wanted": self.evidence_wanted,
            "packs": self.packs,
            "issuers": self.issuers,
            "themes": self.themes,
            "since": self.since,
            "as_of": self.as_of,
            "budget_s": self.budget_s,
            "max_tool_calls": self.max_tool_calls,
        }


def _strings(value: Any, limit: int, size: int = 200) -> list[str]:
    if not isinstance(value, list):
        return []
    return [" ".join(str(v).split())[:size] for v in value if isinstance(v, str) and v.strip()][:limit]


def parse_brief(payload: dict[str, Any]) -> Brief:
    subject = payload.get("subject")
    if subject not in SUBJECTS:
        raise ResearchError(f"sujet inconnu : {subject!r}")
    researcher = payload.get("researcher")
    if not isinstance(researcher, str) or not RESEARCHER_ID.match(researcher):
        raise ResearchError("researcher doit suivre ^r[0-9]{1,2}$")
    objective = " ".join(str(payload.get("objective") or "").split())[:500]
    if not objective:
        raise ResearchError("objective est requis")
    packs = [p for p in payload.get("packs") or [] if isinstance(p, str)]
    if not packs or any(p not in SUBJECTS[subject].packs for p in packs):
        raise ResearchError(f"packs doit être une liste non vide parmi {list(SUBJECTS[subject].packs)}")
    since = payload.get("since") or (clock.today().replace(day=1)).isoformat()
    if not isinstance(since, str) or clock.parse_datetime(since) is None:
        raise ResearchError("since doit être une date AAAA-MM-JJ")
    as_of = payload.get("as_of")
    if as_of is not None and (not isinstance(as_of, str) or clock.parse_datetime(as_of) is None):
        raise ResearchError("as_of doit être une date ou un horodatage ISO")
    try:
        budget = float(payload.get("budget_s") or RESEARCHER_BUDGET_S)
        calls = int(payload.get("max_tool_calls") or RESEARCHER_MAX_TOOL_CALLS)
    except (TypeError, ValueError) as exc:
        raise ResearchError("budget_s et max_tool_calls doivent être des nombres") from exc
    return Brief(
        run_id=str(payload.get("run_id")),
        subject=subject,
        researcher=researcher,
        objective=objective,
        evidence_wanted=_strings(payload.get("evidence_wanted"), 8),
        packs=list(dict.fromkeys(packs)),
        issuers=_strings(payload.get("issuers"), 12, 20),
        themes=_strings(payload.get("themes"), 8, 40),
        since=since[:10],
        as_of=as_of,
        budget_s=max(30.0, min(budget, RESEARCHER_MAX_BUDGET_S)),
        max_tool_calls=max(4, min(calls, RESEARCHER_MAX_TOOL_CALLS)),
    )


# ----------------------------------------------------------------------------- dates
_QUARTER = re.compile(r"^(\d{4})[- ]?Q([1-4])$", re.I)
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:T?(\d{2})(\d{2})(\d{2})Z?)?$")


def parse_any_date(value: Any) -> str | None:
    """Date ou horodatage lu dans une source, rendu en ISO (``AAAA-MM-JJ`` ou ``…Z``); ``None`` si illisible."""
    if value is None:
        return None
    if isinstance(value, int | float) or (isinstance(value, str) and value.strip().isdigit() and len(value) >= 10):
        number = float(value)
        if number > 1e11:
            number /= 1000.0  # millisecondes
        if 6e8 < number < 5e9:
            return clock.iso(datetime.fromtimestamp(number, UTC))
    text = str(value).strip()
    if not text:
        return None
    parsed = clock.parse_datetime(text)
    if parsed is not None:
        return text[:10] if len(text) == 10 else clock.iso(parsed)
    match = _MONTH.match(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-01"
    match = _QUARTER.match(text)
    if match:
        return f"{match.group(1)}-{(int(match.group(2)) - 1) * 3 + 1:02d}-01"
    match = _COMPACT.match(text)
    if match:
        y, m, d, hh, mm, ss = match.groups()
        if hh:
            return f"{y}-{m}-{d}T{hh}:{mm}:{ss}Z"
        return f"{y}-{m}-{d}"
    try:
        rfc = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        rfc = None
    if rfc is not None:
        if rfc.tzinfo is None:
            rfc = rfc.replace(tzinfo=UTC)
        return clock.iso(rfc)
    return None


def _date_parts(iso: str | None) -> list[str]:
    if not iso:
        return []
    parts = re.findall(r"\d+", iso[:10])
    out = list(parts)
    if len(parts) >= 2:
        out.append(str(int(parts[1])))
    if len(parts) >= 3:
        out.append(str(int(parts[2])))
    return out


def _after(a: str, b: str) -> bool:
    da, db = clock.parse_datetime(a), clock.parse_datetime(b)
    return bool(da and db and da > db)


# ----------------------------------------------------------------------------- l'exécution
@dataclass
class ResearcherRun:
    brief: Brief
    store: Store
    web: ResearchWeb
    deadline: float
    findings: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: int = 0
    finished: bool = False
    summary: str = ""
    gaps: list[str] = field(default_factory=list)

    def _spend(self) -> str | None:
        self.tool_calls += 1
        if time.monotonic() > self.deadline:
            return "time budget exhausted: call finish now"
        if self.tool_calls > self.brief.max_tool_calls:
            return "tool-call budget exhausted: call finish now"
        return None

    def _licence(self, host: str, host_status: str) -> dict[str, Any]:
        info = HOSTS.get(host)
        if info is None or host_status == "quarantined":
            return {
                "licence": "non vérifiée : hôte en quarantaine, à approuver par un humain",
                "licence_url": None,
                "attribution_text": f"Source : {host}",
                "licence_note": "hôte proposé par un chercheur; hors de la base générale jusqu'à son approbation",
            }
        note = info.note or None
        return {
            "licence": info.licence,
            "licence_url": info.licence_url,
            "attribution_text": info.attribution,
            "licence_note": note,
        }

    def _dates(
        self,
        archived: Any,
        tree: Any,
        observation_locator: str | None,
        observation_date: str | None,
        publication_locator: str | None,
    ) -> tuple[str | None, str, str, str]:
        observation, obs_basis = None, "none"
        if observation_locator:
            observation = parse_any_date(documents.scalar(documents.resolve(tree, observation_locator)))
            if observation is None:
                raise ResearchError(f"date d'observation illisible à {observation_locator!r}")
            obs_basis = "source"
        elif observation_date:
            observation = parse_any_date(observation_date)
            if observation is None:
                raise ResearchError("observation_date illisible")
            obs_basis = "researcher"
        if publication_locator:
            publication = parse_any_date(documents.scalar(documents.resolve(tree, publication_locator)))
            if publication is None:
                raise ResearchError(f"date de publication illisible à {publication_locator!r}")
            pub_basis = "source"
        else:
            publication, pub_basis = archived.retrieved_at, "retrieved_at_upper_bound"
        if _after(publication, archived.retrieved_at):
            raise ResearchError("date de publication postérieure à la récupération : refusée")
        if observation and _after(observation[:10], publication[:10]) and pub_basis == "source":
            raise ResearchError("date d'observation postérieure à la publication")
        if self.brief.as_of and _after(publication, self.brief.as_of):
            raise ResearchError(f"publié après as_of ({self.brief.as_of}) : hors du point dans le temps demandé")
        return observation, obs_basis, publication, pub_basis

    def _ground(self, text: str, values: list[str]) -> None:
        missing = documents.grounded(text, values)
        if missing:
            raise ResearchError(
                "nombres absents des valeurs lues : " + ", ".join(missing[:5]) + " (réécrire la phrase sans eux)"
            )

    def _base(self, archived: Any, kind: str, label: str, claim: str, issuers: list[str]) -> dict[str, Any]:
        n = len(self.findings) + 1
        return {
            "finding_id": f"{self.brief.subject}-{self.brief.researcher}-f{n:02d}",
            "run_id": self.brief.run_id,
            "subject": self.brief.subject,
            "researcher": self.brief.researcher,
            "objective": self.brief.objective,
            "kind": kind,
            "label": " ".join(str(label).split())[:160],
            "claim": " ".join(str(claim).split())[:400],
            "issuers": [i.upper() for i in issuers if isinstance(i, str)][:6],
            "url": archived.url,
            "host": archived.host,
            "response_id": archived.response_id,
            "archive_key": archived.archive_key,
            "retrieved_at": archived.retrieved_at,
            "host_status": archived.host_status,
            "robots_ok_at_fetch": archived.robots_ok,
            "as_of": self.brief.as_of,
            **self._licence(archived.host, archived.host_status),
        }

    # ------------------------------------------------------------------ consignation
    def record_finding(self, args: dict[str, Any]) -> dict[str, Any]:
        if len(self.findings) >= MAX_FINDINGS:
            raise ResearchError(f"au plus {MAX_FINDINGS} constats par chercheur")
        kind = args.get("kind")
        if kind not in FINDING_KINDS:
            raise ResearchError(f"kind doit être parmi {FINDING_KINDS}")
        archived = self.web.get(str(args.get("response_id") or ""))
        fields_in = args.get("fields") or {}
        if not isinstance(fields_in, dict) or not fields_in or len(fields_in) > 12:
            raise ResearchError("fields doit associer 1 à 12 noms à des localisateurs")
        values: dict[str, str] = {}
        locators: dict[str, str] = {}
        for name, locator in fields_in.items():
            key = re.sub(r"[^A-Za-z0-9_]", "_", str(name))[:40]
            value = documents.scalar(documents.resolve(archived.tree, str(locator)))
            if value == "":
                raise ResearchError(f"valeur vide à {locator!r}")
            values[key] = value[:2000]
            locators[key] = str(locator)
        for alternatives in REQUIRED_FIELDS[kind]:
            if not any(a in values for a in alternatives):
                raise ResearchError(f"un constat {kind} exige le champ {' ou '.join(alternatives)}")
        if archived.host in MARKET_HOSTS and kind == "signal" and "resolution_rules" not in values:
            raise ResearchError("une cote de marché exige fields.resolution_rules (règles telles quelles)")
        observation, obs_basis, publication, pub_basis = self._dates(
            archived,
            archived.tree,
            args.get("observation_locator"),
            args.get("observation_date"),
            args.get("publication_locator"),
        )
        if kind in ("fact", "signal", "quote") and observation is None:
            raise ResearchError("une valeur exige sa date d'observation (observation_locator ou observation_date)")
        label = str(args.get("label") or values.get("title") or kind)
        claim = str(args.get("claim") or "")
        if not claim.strip():
            raise ResearchError("claim est requis (une phrase neutre en français)")
        allowed = [*values.values(), *_date_parts(observation), *_date_parts(publication)]
        self._ground(f"{label} {claim}", allowed)
        finding = self._base(archived, kind, label, claim, args.get("issuers") or self.brief.issuers)
        link = values.get("link") or values.get("url")
        finding.update(
            values=values,
            locators=locators,
            unit=(str(args.get("unit"))[:40] if args.get("unit") else None),
            observation_date=observation,
            observation_basis=obs_basis,
            publication_date=publication,
            publication_basis=pub_basis,
            item_url=link if isinstance(link, str) and link.startswith("https://") else archived.url,
        )
        self.findings.append(finding)
        return {
            "status": "ok",
            "finding_id": finding["finding_id"],
            "values": values,
            "observation_date": observation,
            "publication_date": publication,
        }

    def record_series(self, args: dict[str, Any]) -> dict[str, Any]:
        if len(self.findings) >= MAX_FINDINGS:
            raise ResearchError(f"au plus {MAX_FINDINGS} constats par chercheur")
        archived = self.web.get(str(args.get("response_id") or ""))
        rows_locator = str(args.get("rows") or "")
        date_field, value_field = str(args.get("date_field") or ""), str(args.get("value_field") or "")
        rows = documents.extract_rows(archived.tree, rows_locator, date_field, value_field)
        observations = []
        for row in rows:
            day = parse_any_date(row["date"])
            if day is None:
                continue
            observations.append({"date": day[:10], "value": row["value"], "row": row["row"]})
        if not observations:
            raise ResearchError("aucune date lisible dans la série")
        observations.sort(key=lambda o: o["date"])
        observations = observations[-MAX_SERIES_ROWS:]
        last = observations[-1]
        publication_field = args.get("publication_field")
        publication_locator = None
        if publication_field:
            publication_locator = (
                f"{rows_locator}[{last['row']}].{publication_field}"
                if not str(publication_field).startswith("[")
                else f"{rows_locator}[{last['row']}]{publication_field}"
            )
        _, _, publication, pub_basis = self._dates(archived, archived.tree, None, last["date"], publication_locator)
        label = str(args.get("label") or args.get("series_id") or "série")
        claim = str(args.get("claim") or "")
        if not claim.strip():
            raise ResearchError("claim est requis (une phrase neutre en français)")
        allowed = [o["value"] for o in observations] + [p for o in observations for p in _date_parts(o["date"])]
        allowed += _date_parts(publication)
        self._ground(f"{label} {claim}", allowed)
        finding = self._base(archived, "series", label, claim, args.get("issuers") or [])
        finding.update(
            series_id=str(args.get("series_id") or label)[:80],
            unit=(str(args.get("unit"))[:40] if args.get("unit") else None),
            frequency=(str(args.get("frequency"))[:20] if args.get("frequency") else None),
            observations=[{"date": o["date"], "value": o["value"]} for o in observations],
            series_spec={
                "rows": rows_locator,
                "date_field": date_field,
                "value_field": value_field,
                "publication_field": publication_field,
            },
            observation_date=last["date"],
            observation_basis="source",
            publication_date=publication,
            publication_basis=pub_basis,
            item_url=archived.url,
            values={"last": last["value"]},
        )
        self.findings.append(finding)
        return {
            "status": "ok",
            "finding_id": finding["finding_id"],
            "points": len(observations),
            "last": {"date": last["date"], "value": last["value"]},
            "publication_date": publication,
        }

    # ------------------------------------------------------------------ outils
    def tools(self) -> list[Any]:
        run = self
        sources = pack_sources(run.brief.packs)

        def guarded(fn):
            def wrapper(*args, **kwargs):
                reason = run._spend()
                if reason:
                    return tool_result({"status": "error", "reason": reason})
                try:
                    return tool_result(fn(*args, **kwargs))
                except (ResearchError, WebError, documents.DocumentError) as exc:
                    return tool_result({"status": "error", "reason": str(exc)})

            return wrapper

        @tool(
            name="search_source",
            description="Search a source catalogue or search API of your packs. Sources: " + ", ".join(sources),
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "enum": list(sources) or ["feeds"]},
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                    },
                    "required": ["source", "query"],
                }
            },
        )
        def search_source(source: str, query: str, limit: int = 8) -> str:
            @guarded
            def go():
                if source not in sources:
                    raise ResearchError(f"source hors de vos paquets : {source}")
                adapter = search.ADAPTERS[source]
                if source == "feeds":
                    return {"status": "ok", **adapter(run.web, query, limit, tuple(run.brief.packs))}
                return {"status": "ok", **adapter(run.web, str(query)[:250], int(limit))}

            return go()

        def _preview(archived: Any, offset: int) -> dict[str, Any]:
            return {
                "status": "ok",
                "response_id": archived.response_id,
                "url": archived.url,
                "http_status": archived.status,
                "format": archived.fmt,
                "host_status": archived.host_status,
                "retrieved_at": archived.retrieved_at,
                "last_modified": archived.headers.get("Last-Modified"),
                **documents.preview(archived.tree, offset),
            }

        @tool(
            name="fetch",
            description="GET a URL on an allowed host; returns a paged preview (path = value lines) and a response_id.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}},
                    "required": ["url"],
                }
            },
        )
        def fetch(url: str, offset: int = 0) -> str:
            @guarded
            def go():
                return _preview(run.web.fetch(str(url).strip()), offset)

            return go()

        @tool(
            name="view",
            description="Show more lines of an already fetched response (no new request).",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {"response_id": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}},
                    "required": ["response_id", "offset"],
                }
            },
        )
        def view(response_id: str, offset: int) -> str:
            @guarded
            def go():
                return _preview(run.web.get(response_id), offset)

            return go()

        statcan_allowed = "www150.statcan.gc.ca" in pack_hosts(run.brief.packs)

        @tool(
            name="statcan_table",
            description="Statistics Canada table metadata (dimensions and member ids) by product id, e.g. 18100205.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {"product_id": {"type": "integer"}},
                    "required": ["product_id"],
                }
            },
        )
        def statcan_table(product_id: int) -> str:
            @guarded
            def go():
                if not statcan_allowed:
                    raise ResearchError("Statistique Canada n'est pas dans vos paquets")
                archived = run.web.post_json(
                    "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata", [{"productId": int(product_id)}]
                )
                return _preview(archived, 0)

            return go()

        @tool(
            name="statcan_data",
            description="Latest N data points of a Statistics Canada table coordinate (10 member ids joined by dots, "
            "e.g. 1.1.0.0.0.0.0.0.0.0). Use record_series with rows `[0].object.vectorDataPoint`, date_field refPer, "
            "value_field value, publication_field releaseTime.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer"},
                        "coordinate": {"type": "string"},
                        "latest_n": {"type": "integer", "minimum": 1, "maximum": 60},
                    },
                    "required": ["product_id", "coordinate"],
                }
            },
        )
        def statcan_data(product_id: int, coordinate: str, latest_n: int = 12) -> str:
            @guarded
            def go():
                if not statcan_allowed:
                    raise ResearchError("Statistique Canada n'est pas dans vos paquets")
                if not _COORDINATE.match(str(coordinate)):
                    raise ResearchError("coordinate doit compter 10 identifiants séparés par des points")
                archived = run.web.post_json(
                    "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods",
                    [{"productId": int(product_id), "coordinate": str(coordinate), "latestN": int(latest_n)}],
                )
                return _preview(archived, 0)

            return go()

        locator_map = {"type": "object", "additionalProperties": {"type": "string"}}

        @tool(
            name="record_finding",
            description="Record one finding from a fetched response by locators. kind: news (fields title, link), "
            "fact or signal or quote (field value; markets also resolution_rules, bid, ask, volume), filing (fields "
            "form, accession). The code reads every value and date.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": list(FINDING_KINDS)},
                        "label": {"type": "string"},
                        "claim": {"type": "string"},
                        "response_id": {"type": "string"},
                        "fields": locator_map,
                        "observation_locator": {"type": "string"},
                        "observation_date": {"type": "string"},
                        "publication_locator": {"type": "string"},
                        "unit": {"type": "string"},
                        "issuers": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["kind", "label", "claim", "response_id", "fields"],
                }
            },
        )
        def record_finding(
            kind: str,
            label: str,
            claim: str,
            response_id: str,
            fields: dict[str, str],
            observation_locator: str | None = None,
            observation_date: str | None = None,
            publication_locator: str | None = None,
            unit: str | None = None,
            issuers: list[str] | None = None,
        ) -> str:
            args = {
                "kind": kind,
                "label": label,
                "claim": claim,
                "response_id": response_id,
                "fields": fields,
                "observation_locator": observation_locator,
                "observation_date": observation_date,
                "publication_locator": publication_locator,
                "unit": unit,
                "issuers": issuers,
            }

            @guarded
            def go():
                return run.record_finding(args)

            return go()

        @tool(
            name="record_series",
            description="Record a time series from a fetched response: rows = locator of the list of rows, "
            "date_field and value_field = paths inside each row (CSV: rows `rows`, fields = column names).",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "claim": {"type": "string"},
                        "response_id": {"type": "string"},
                        "rows": {"type": "string"},
                        "date_field": {"type": "string"},
                        "value_field": {"type": "string"},
                        "publication_field": {"type": "string"},
                        "series_id": {"type": "string"},
                        "unit": {"type": "string"},
                        "frequency": {"type": "string"},
                        "issuers": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["label", "claim", "response_id", "rows", "date_field", "value_field"],
                }
            },
        )
        def record_series(
            label: str,
            claim: str,
            response_id: str,
            rows: str,
            date_field: str,
            value_field: str,
            publication_field: str | None = None,
            series_id: str | None = None,
            unit: str | None = None,
            frequency: str | None = None,
            issuers: list[str] | None = None,
        ) -> str:
            args = {
                "label": label,
                "claim": claim,
                "response_id": response_id,
                "rows": rows,
                "date_field": date_field,
                "value_field": value_field,
                "publication_field": publication_field,
                "series_id": series_id,
                "unit": unit,
                "frequency": frequency,
                "issuers": issuers,
            }

            @guarded
            def go():
                return run.record_series(args)

            return go()

        @tool(
            name="propose_host",
            description="Propose a relevant host outside your packs (at most 2). Its findings stay in quarantine.",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}, "why": {"type": "string"}},
                    "required": ["url", "why"],
                }
            },
        )
        def propose_host(url: str, why: str) -> str:
            @guarded
            def go():
                entry = run.web.propose_host(str(url).strip(), why)
                return {
                    "status": "ok",
                    "host": entry.host,
                    "robots_status": entry.robots_status,
                    "readable": entry.robots_allows,
                    "note": "findings from this host stay in quarantine until a human approves its licence",
                }

            return go()

        @tool(
            name="finish",
            description="End the mission with a one-paragraph French summary and the evidence not found (gaps).",
            inputSchema={
                "json": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "gaps": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["summary"],
                }
            },
            context=True,
        )
        def finish(tool_context, summary: str, gaps: list[str] | None = None) -> str:
            run.finished = True
            run.summary = " ".join(str(summary).split())[:1200]
            run.gaps = _strings(gaps or [], 10, 300)
            tool_context.agent.cancel(after_current_tools=True)
            return tool_result({"status": "ok", "findings": len(run.findings)})

        return [
            search_source,
            fetch,
            view,
            statcan_table,
            statcan_data,
            record_finding,
            record_series,
            propose_host,
            finish,
        ]


def research(
    *,
    brief: Brief,
    store: Store,
    trace: Trace,
    model_factory: ModelFactory,
    model_id: str,
    web: ResearchWeb | None = None,
) -> dict[str, Any]:
    from .packs import describe_packs

    web = web or ResearchWeb(store=store, allowed_hosts=pack_hosts(brief.packs))
    run = ResearcherRun(brief=brief, store=store, web=web, deadline=time.monotonic() + brief.budget_s)
    subject = SUBJECTS[brief.subject]
    prompt = SYSTEM_PROMPT.format(
        subject=subject.code,
        subject_name=subject.name,
        researcher=brief.researcher,
        objective=brief.objective,
        evidence="; ".join(brief.evidence_wanted) or "as relevant to the mission",
        issuers=", ".join(brief.issuers) or "none",
        themes=", ".join(brief.themes) or "none",
        since=brief.since,
        as_of_line=(f"Point in time: only evidence published on or before {brief.as_of}." if brief.as_of else ""),
        budget_s=int(brief.budget_s),
        max_tool_calls=brief.max_tool_calls,
        packs=describe_packs(brief.packs),
    )
    spec = AgentSpec(
        actor="researcher",
        name=f"Researcher {brief.subject}-{brief.researcher}",
        effort="medium",
        system_prompt=prompt,
        tools=run.tools(),
        max_turns=brief.max_tool_calls + 4,
        max_tokens=8000,
        tool_summaries={
            "record_finding": lambda i: {"kind": i.get("kind"), "label": str(i.get("label"))[:80]},
            "record_series": lambda i: {"label": str(i.get("label"))[:80], "rows": i.get("rows")},
        },
    )
    error = None
    try:
        run_agent(spec, "Start the mission.", model_factory=model_factory, model_id=model_id, trace=trace)
    except AppError as exc:
        error = f"{exc.code}: {exc.message}"
    store.put_json(brief.prefix + "findings.json", {"brief": brief.to_dict(), "findings": run.findings})
    quarantine = [
        {
            "host": q.host,
            "url": q.url,
            "why": q.why,
            "robots_status": q.robots_status,
            "readable": q.robots_allows,
            "fetches": q.fetches,
            "proposed_at": q.proposed_at,
        }
        for q in web.quarantine.values()
    ]
    if error and not run.findings:
        raise AppError("model_error", error)
    return {
        "subject": brief.subject,
        "researcher": brief.researcher,
        "findings": len(run.findings),
        "findings_key": brief.prefix + "findings.json",
        "summary": run.summary,
        "gaps": run.gaps,
        "quarantine": quarantine,
        "blocked_hosts": dict(web.blocked),
        "requests": dict(web.counts),
        "warnings": web.warnings + ([error] if error else []) + ([] if run.finished else ["finish non appelé"]),
        "tool_calls": run.tool_calls,
    }
