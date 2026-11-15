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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from strands import tool

from .. import clock, okf
from ..agentkit import AgentSpec, ModelFactory, run_agent, tool_result
from ..errors import AppError
from ..store import Store
from ..trace import Trace
from . import documents, search
from .items import ESG_HOSTS, MARKET_HOSTS
from .packs import (
    HOSTS,
    RESEARCHER_BUDGET_S,
    RESEARCHER_MAX_BUDGET_S,
    RESEARCHER_MAX_TOOL_CALLS,
    SUBJECTS,
    describe_packs,
    pack_hosts,
    pack_sources,
)
from .web import Archived, ResearchWeb, WebError

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

# Outils du chercheur : textes et schémas lus par le modèle (la liste des sources s'ajoute à la description).
SEARCH_SOURCE_DESCRIPTION = "Search a source catalogue or search API of your packs. Sources: "
FETCH_DESCRIPTION = "GET a URL on an allowed host; returns a paged preview (path = value lines) and a response_id."
FETCH_SCHEMA = {
    "json": {
        "type": "object",
        "properties": {"url": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}},
        "required": ["url"],
    }
}
VIEW_DESCRIPTION = "Show more lines of an already fetched response (no new request)."
VIEW_SCHEMA = {
    "json": {
        "type": "object",
        "properties": {"response_id": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}},
        "required": ["response_id", "offset"],
    }
}
STATCAN_TABLE_DESCRIPTION = "Statistics Canada table metadata (dimensions and member ids) by product id, e.g. 18100205."
STATCAN_TABLE_SCHEMA = {
    "json": {
        "type": "object",
        "properties": {"product_id": {"type": "integer"}},
        "required": ["product_id"],
    }
}
STATCAN_DATA_DESCRIPTION = (
    "Latest N data points of a Statistics Canada table coordinate (10 member ids joined by dots, "
    "e.g. 1.1.0.0.0.0.0.0.0.0). Use record_series with rows `[0].object.vectorDataPoint`, date_field refPer, "
    "value_field value, publication_field releaseTime."
)
STATCAN_DATA_SCHEMA = {
    "json": {
        "type": "object",
        "properties": {
            "product_id": {"type": "integer"},
            "coordinate": {"type": "string"},
            "latest_n": {"type": "integer", "minimum": 1, "maximum": 60},
        },
        "required": ["product_id", "coordinate"],
    }
}
RECORD_FINDING_DESCRIPTION = (
    "Record one finding from a fetched response by locators. kind: news (fields title, link), "
    "fact or signal or quote (field value; markets also resolution_rules, bid, ask, volume), filing (fields "
    "form, accession). The code reads every value and date. ESG evidence (funds-sustainability hosts only, "
    "kind fact): esg_kind (emissions, incident, index_exclusion, sector_activity), esg_metric (snake_case; "
    "for sector_activity one of tobacco, weapons, fossil_fuels, gambling, alcohol), esg_period (YYYY, "
    "YYYY-MM or YYYY-MM-DD; defaults to the observation date). A finding about emissions, incidents, index "
    "exclusions or sector activity is ESG evidence only with esg_kind: always set it for those, and record the "
    "measured value itself (a total, a count), never a dataset's metadata such as its modification date."
)
RECORD_FINDING_SCHEMA = {
    "json": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(FINDING_KINDS)},
            "label": {"type": "string"},
            "claim": {"type": "string"},
            "response_id": {"type": "string"},
            "fields": {"type": "object", "additionalProperties": {"type": "string"}},
            "observation_locator": {"type": "string"},
            "observation_date": {"type": "string"},
            "publication_locator": {"type": "string"},
            "unit": {"type": "string"},
            "issuers": {"type": "array", "items": {"type": "string"}},
            "esg_kind": {"type": "string", "enum": list(okf.ESG_KINDS)},
            "esg_metric": {"type": "string"},
            "esg_period": {"type": "string"},
        },
        "required": ["kind", "label", "claim", "response_id", "fields"],
    }
}
RECORD_SERIES_DESCRIPTION = (
    "Record a time series from a fetched response: rows = locator of the list of rows, "
    "date_field and value_field = paths inside each row (CSV: rows `rows`, fields = column names)."
)
RECORD_SERIES_SCHEMA = {
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
}
PROPOSE_HOST_DESCRIPTION = "Propose a relevant host outside your packs (at most 2). Its findings stay in quarantine."
PROPOSE_HOST_SCHEMA = {
    "json": {
        "type": "object",
        "properties": {"url": {"type": "string"}, "why": {"type": "string"}},
        "required": ["url", "why"],
    }
}
FINISH_DESCRIPTION = "End the mission with a one-paragraph French summary and the evidence not found (gaps)."
FINISH_SCHEMA = {
    "json": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "gaps": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary"],
    }
}
TOOL_SUMMARIES = {
    "record_finding": lambda tool_input: {"kind": tool_input.get("kind"), "label": str(tool_input.get("label"))[:80]},
    "record_series": lambda tool_input: {"label": str(tool_input.get("label"))[:80], "rows": tool_input.get("rows")},
}


class ResearchError(Exception):
    pass


def _esg_block(args: dict[str, Any], kind: str, host: str, observation: str | None) -> dict[str, str] | None:
    """Bloc ``data.esg`` d'un fait ESG (CONTRACTS.md, section 11.5) : liste fermée, hôtes du paquet
    ``funds-sustainability`` seulement. Le modèle choisit la catégorie; la valeur reste lue au localisateur."""
    if not args.get("esg_kind"):
        return None
    if kind != "fact":
        raise ResearchError("esg_kind ne s'applique qu'à un constat fact")
    if host not in ESG_HOSTS:
        raise ResearchError(f"esg_kind exige un hôte du paquet funds-sustainability (pas {host})")
    esg = {
        "kind": str(args.get("esg_kind")),
        "metric": str(args.get("esg_metric") or ""),
        "period": str(args.get("esg_period") or (observation or "")[:10]),
    }
    problems = okf.esg_problems(esg)
    if problems:
        raise ResearchError("fait ESG refusé : " + "; ".join(problems))
    return esg


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
    return [" ".join(str(text).split())[:size] for text in value if isinstance(text, str) and text.strip()][:limit]


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
    packs = [pack for pack in payload.get("packs") or [] if isinstance(pack, str)]
    if not packs or any(pack not in SUBJECTS[subject].packs for pack in packs):
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


def _looks_like_timestamp(value: Any) -> bool:
    return isinstance(value, int | float) or (isinstance(value, str) and value.strip().isdigit() and len(value) >= 10)


def _timestamp_date(value: Any) -> str | None:
    """Horodatage Unix (secondes ou millisecondes) d'une plage plausible, en ISO; ``None`` hors de cette plage."""
    number = float(value)
    if number > 1e11:
        number /= 1000.0  # millisecondes
    if 6e8 < number < 5e9:
        return clock.iso(datetime.fromtimestamp(number, UTC))
    return None


def _pattern_date(text: str) -> str | None:
    """Mois ``AAAA-MM``, trimestre ``AAAA-Qn`` ou date compacte ``AAAAMMJJ[THHMMSSZ]``."""
    match = _MONTH.match(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-01"
    match = _QUARTER.match(text)
    if match:
        return f"{match.group(1)}-{(int(match.group(2)) - 1) * 3 + 1:02d}-01"
    match = _COMPACT.match(text)
    if match:
        year, month, day, hour, minute, second = match.groups()
        if hour:
            return f"{year}-{month}-{day}T{hour}:{minute}:{second}Z"
        return f"{year}-{month}-{day}"
    return None


def _rfc_date(text: str) -> str | None:
    """Date RFC 2822 des flux (``Thu, 13 Nov 2026 14:00:00 GMT``); sans fuseau, elle est lue en UTC."""
    try:
        parsed = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return clock.iso(parsed)


def parse_any_date(value: Any) -> str | None:
    """Date ou horodatage lu dans une source, rendu en ISO (``AAAA-MM-JJ`` ou ``…Z``); ``None`` si illisible."""
    if value is None:
        return None
    if _looks_like_timestamp(value):
        timestamp = _timestamp_date(value)
        if timestamp is not None:
            return timestamp
    text = str(value).strip()
    if not text:
        return None
    parsed = clock.parse_datetime(text)
    if parsed is not None:
        return text[:10] if len(text) == 10 else clock.iso(parsed)
    return _pattern_date(text) or _rfc_date(text)


def _dates_pool(*values: str | None) -> list[str]:
    return [str(value)[:10].replace("-", "/") for value in values if value]


def _is_after(moment: str, reference: str) -> bool:
    moment_at, reference_at = clock.parse_datetime(moment), clock.parse_datetime(reference)
    return bool(moment_at and reference_at and moment_at > reference_at)


def _observation_date(
    tree: Any, observation_locator: str | None, observation_date: str | None
) -> tuple[str | None, str]:
    """Date d'observation et son origine : lue dans la source, donnée par le chercheur, ou aucune."""
    if observation_locator:
        observation = parse_any_date(documents.scalar(documents.resolve(tree, observation_locator)))
        if observation is None:
            raise ResearchError(f"date d'observation illisible à {observation_locator!r}")
        return observation, "source"
    if observation_date:
        observation = parse_any_date(observation_date)
        if observation is None:
            raise ResearchError("observation_date illisible")
        return observation, "researcher"
    return None, "none"


def _publication_date(archived: Archived, publication_locator: str | None) -> tuple[str, str]:
    """Date de publication lue dans la source, sinon l'heure de récupération comme borne supérieure."""
    if not publication_locator:
        return archived.retrieved_at, "retrieved_at_upper_bound"
    publication = parse_any_date(documents.scalar(documents.resolve(archived.tree, publication_locator)))
    if publication is None:
        raise ResearchError(f"date de publication illisible à {publication_locator!r}")
    return publication, "source"


# ----------------------------------------------------------------------------- lecture des constats
def _read_fields(tree: Any, fields: Any) -> tuple[dict[str, str], dict[str, str]]:
    """Valeurs lues aux localisateurs (noms ramenés à ``[A-Za-z0-9_]``) et localisateurs, sous les mêmes noms."""
    if not isinstance(fields, dict) or not fields or len(fields) > 12:
        raise ResearchError("fields doit associer 1 à 12 noms à des localisateurs")
    values: dict[str, str] = {}
    locators: dict[str, str] = {}
    for name, locator in fields.items():
        key = re.sub(r"[^A-Za-z0-9_]", "_", str(name))[:40]
        value = documents.scalar(documents.resolve(tree, str(locator)))
        if value == "":
            raise ResearchError(f"valeur vide à {locator!r}")
        values[key] = value[:2000]
        locators[key] = str(locator)
    return values, locators


def _check_required_fields(kind: str, values: dict[str, str], host: str) -> None:
    for alternatives in REQUIRED_FIELDS[kind]:
        if not any(name in values for name in alternatives):
            raise ResearchError(f"un constat {kind} exige le champ {' ou '.join(alternatives)}")
    if host in MARKET_HOSTS and kind == "signal" and "resolution_rules" not in values:
        raise ResearchError("une cote de marché exige fields.resolution_rules (règles telles quelles)")


def _required_claim(args: dict[str, Any]) -> str:
    claim = str(args.get("claim") or "")
    if not claim.strip():
        raise ResearchError("claim est requis (une phrase neutre en français)")
    return claim


def _clipped(value: Any, size: int) -> str | None:
    return str(value)[:size] if value else None


def _series_spec(args: dict[str, Any]) -> dict[str, Any]:
    """Où lire la série : liste des lignes, champs de date et de valeur, champ de la date de publication."""
    return {
        "rows": str(args.get("rows") or ""),
        "date_field": str(args.get("date_field") or ""),
        "value_field": str(args.get("value_field") or ""),
        "publication_field": args.get("publication_field"),
    }


def _dated_observations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lignes à date lisible, triées par date; les ``MAX_SERIES_ROWS`` dernières."""
    observations = []
    for row in rows:
        day = parse_any_date(row["date"])
        if day is None:
            continue
        observations.append({"date": day[:10], "value": row["value"], "row": row["row"]})
    if not observations:
        raise ResearchError("aucune date lisible dans la série")
    observations.sort(key=lambda observation: observation["date"])
    return observations[-MAX_SERIES_ROWS:]


def _publication_locator(rows_locator: str, last: dict[str, Any], publication_field: Any) -> str | None:
    """Localisateur de la date de publication dans la dernière ligne : un champ, ou un ``[...]`` collé à la ligne."""
    if not publication_field:
        return None
    return (
        f"{rows_locator}[{last['row']}].{publication_field}"
        if not str(publication_field).startswith("[")
        else f"{rows_locator}[{last['row']}]{publication_field}"
    )


def _preview(archived: Archived, offset: int) -> dict[str, Any]:
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


def _search_source_schema(sources: tuple[str, ...]) -> dict[str, Any]:
    return {
        "json": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": list(sources) or ["feeds"]},
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            "required": ["source", "query"],
        }
    }


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
        archived: Archived,
        observation_locator: str | None,
        observation_date: str | None,
        publication_locator: str | None,
    ) -> tuple[str | None, str, str, str]:
        observation, observation_basis = _observation_date(archived.tree, observation_locator, observation_date)
        publication, publication_basis = _publication_date(archived, publication_locator)
        if _is_after(publication, archived.retrieved_at):
            raise ResearchError("date de publication postérieure à la récupération : refusée")
        if observation and _is_after(observation[:10], publication[:10]) and publication_basis == "source":
            raise ResearchError("date d'observation postérieure à la publication")
        if self.brief.as_of and _is_after(publication, self.brief.as_of):
            raise ResearchError(f"publié après as_of ({self.brief.as_of}) : hors du point dans le temps demandé")
        return observation, observation_basis, publication, publication_basis

    def _ground(self, text: str, values: list[str], dates: list[str]) -> None:
        missing = documents.grounded(text, values, dates)
        if missing:
            raise ResearchError(
                "nombres absents des valeurs lues : " + ", ".join(missing[:5]) + " (réécrire la phrase sans eux)"
            )

    def _base(self, archived: Archived, kind: str, label: str, claim: str, issuers: list[str]) -> dict[str, Any]:
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
            "issuers": [issuer.upper() for issuer in issuers if isinstance(issuer, str)][:6],
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
    def _check_room(self) -> None:
        if len(self.findings) >= MAX_FINDINGS:
            raise ResearchError(f"au plus {MAX_FINDINGS} constats par chercheur")

    def record_finding(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_room()
        kind = args.get("kind")
        if kind not in FINDING_KINDS:
            raise ResearchError(f"kind doit être parmi {FINDING_KINDS}")
        archived = self.web.get(str(args.get("response_id") or ""))
        if archived.host in MARKET_HOSTS and kind in ("fact", "quote"):
            kind = "signal"  # une cote de marché prédictif est toujours un signal, avec ses règles de résolution
        values, locators = _read_fields(archived.tree, args.get("fields") or {})
        _check_required_fields(kind, values, archived.host)
        observation, observation_basis, publication, publication_basis = self._dates(
            archived, args.get("observation_locator"), args.get("observation_date"), args.get("publication_locator")
        )
        if kind in ("fact", "signal", "quote") and observation is None:
            raise ResearchError("une valeur exige sa date d'observation (observation_locator ou observation_date)")
        esg = _esg_block(args, kind, archived.host, observation)
        label = str(args.get("label") or values.get("title") or kind)
        claim = _required_claim(args)
        self._ground(f"{label} {claim}", list(values.values()), _dates_pool(observation, publication))
        finding = self._base(archived, kind, label, claim, args.get("issuers") or self.brief.issuers)
        if esg is not None:
            finding["esg"] = esg
        link = values.get("link") or values.get("url")
        finding.update(
            values=values,
            locators=locators,
            unit=_clipped(args.get("unit"), 40),
            observation_date=observation,
            observation_basis=observation_basis,
            publication_date=publication,
            publication_basis=publication_basis,
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
        self._check_room()
        archived = self.web.get(str(args.get("response_id") or ""))
        spec = _series_spec(args)
        rows = documents.extract_rows(archived.tree, spec["rows"], spec["date_field"], spec["value_field"])
        observations = _dated_observations(rows)
        last = observations[-1]
        publication_locator = _publication_locator(spec["rows"], last, spec["publication_field"])
        _, _, publication, publication_basis = self._dates(archived, None, last["date"], publication_locator)
        label = str(args.get("label") or args.get("series_id") or "série")
        claim = _required_claim(args)
        self._ground(
            f"{label} {claim}",
            [observation["value"] for observation in observations],
            _dates_pool(observations[0]["date"], last["date"], publication),
        )
        finding = self._base(archived, "series", label, claim, args.get("issuers") or [])
        finding.update(
            series_id=str(args.get("series_id") or label)[:80],
            unit=_clipped(args.get("unit"), 40),
            frequency=_clipped(args.get("frequency"), 20),
            observations=[{"date": observation["date"], "value": observation["value"]} for observation in observations],
            series_spec=spec,
            observation_date=last["date"],
            observation_basis="source",
            publication_date=publication,
            publication_basis=publication_basis,
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
    def _guarded(self, action: Callable[[], dict[str, Any]]) -> str:
        """Compte l'appel dans le budget, puis rend au modèle le résultat de l'action ou la raison du refus."""
        reason = self._spend()
        if reason:
            return tool_result({"status": "error", "reason": reason})
        try:
            return tool_result(action())
        except (ResearchError, WebError, documents.DocumentError) as exc:
            return tool_result({"status": "error", "reason": str(exc)})

    def _search_source(self, source: str, query: str, limit: int) -> dict[str, Any]:
        if source not in pack_sources(self.brief.packs):
            raise ResearchError(f"source hors de vos paquets : {source}")
        adapter = search.ADAPTERS[source]
        if source == "feeds":
            return {"status": "ok", **adapter(self.web, query, limit, tuple(self.brief.packs))}
        return {"status": "ok", **adapter(self.web, str(query)[:250], int(limit))}

    def _check_statcan_allowed(self) -> None:
        if "www150.statcan.gc.ca" not in pack_hosts(self.brief.packs):
            raise ResearchError("Statistique Canada n'est pas dans vos paquets")

    def _statcan_table(self, product_id: int) -> dict[str, Any]:
        self._check_statcan_allowed()
        archived = self.web.post_json(
            "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata", [{"productId": int(product_id)}]
        )
        return _preview(archived, 0)

    def _statcan_data(self, product_id: int, coordinate: str, latest_n: int) -> dict[str, Any]:
        self._check_statcan_allowed()
        if not _COORDINATE.match(str(coordinate)):
            raise ResearchError("coordinate doit compter 10 identifiants séparés par des points")
        archived = self.web.post_json(
            "https://www150.statcan.gc.ca/t1/wds/rest/getDataFromCubePidCoordAndLatestNPeriods",
            [{"productId": int(product_id), "coordinate": str(coordinate), "latestN": int(latest_n)}],
        )
        return _preview(archived, 0)

    def _propose_host(self, url: str, why: str) -> dict[str, Any]:
        entry = self.web.propose_host(str(url).strip(), why)
        return {
            "status": "ok",
            "host": entry.host,
            "robots_status": entry.robots_status,
            "readable": entry.robots_allows,
            "note": "findings from this host stay in quarantine until a human approves its licence",
        }

    def _finish(self, tool_context: Any, summary: str, gaps: list[str] | None) -> str:
        self.finished = True
        self.summary = " ".join(str(summary).split())[:1200]
        self.gaps = _strings(gaps or [], 10, 300)
        tool_context.agent.cancel(after_current_tools=True)
        return tool_result({"status": "ok", "findings": len(self.findings)})

    def _reading_tools(self) -> list[Any]:
        run = self
        sources = pack_sources(run.brief.packs)

        @tool(
            name="search_source",
            description=SEARCH_SOURCE_DESCRIPTION + ", ".join(sources),
            inputSchema=_search_source_schema(sources),
        )
        def search_source(source: str, query: str, limit: int = 8) -> str:
            return run._guarded(lambda: run._search_source(source, query, limit))

        @tool(name="fetch", description=FETCH_DESCRIPTION, inputSchema=FETCH_SCHEMA)
        def fetch(url: str, offset: int = 0) -> str:
            return run._guarded(lambda: _preview(run.web.fetch(str(url).strip()), offset))

        @tool(name="view", description=VIEW_DESCRIPTION, inputSchema=VIEW_SCHEMA)
        def view(response_id: str, offset: int) -> str:
            return run._guarded(lambda: _preview(run.web.get(response_id), offset))

        @tool(name="statcan_table", description=STATCAN_TABLE_DESCRIPTION, inputSchema=STATCAN_TABLE_SCHEMA)
        def statcan_table(product_id: int) -> str:
            return run._guarded(lambda: run._statcan_table(product_id))

        @tool(name="statcan_data", description=STATCAN_DATA_DESCRIPTION, inputSchema=STATCAN_DATA_SCHEMA)
        def statcan_data(product_id: int, coordinate: str, latest_n: int = 12) -> str:
            return run._guarded(lambda: run._statcan_data(product_id, coordinate, latest_n))

        return [search_source, fetch, view, statcan_table, statcan_data]

    def _record_finding_tool(self) -> Any:
        run = self

        @tool(name="record_finding", description=RECORD_FINDING_DESCRIPTION, inputSchema=RECORD_FINDING_SCHEMA)
        def record_finding(  # noqa: PLR0913 - signature imposée par le schéma de l'outil (validée par strands)
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
            esg_kind: str | None = None,
            esg_metric: str | None = None,
            esg_period: str | None = None,
        ) -> str:
            args = {
                "esg_kind": esg_kind,
                "esg_metric": esg_metric,
                "esg_period": esg_period,
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
            return run._guarded(lambda: run.record_finding(args))

        return record_finding

    def _record_series_tool(self) -> Any:
        run = self

        @tool(name="record_series", description=RECORD_SERIES_DESCRIPTION, inputSchema=RECORD_SERIES_SCHEMA)
        def record_series(  # noqa: PLR0913 - signature imposée par le schéma de l'outil (validée par strands)
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
            return run._guarded(lambda: run.record_series(args))

        return record_series

    def _closing_tools(self) -> list[Any]:
        run = self

        @tool(name="propose_host", description=PROPOSE_HOST_DESCRIPTION, inputSchema=PROPOSE_HOST_SCHEMA)
        def propose_host(url: str, why: str) -> str:
            return run._guarded(lambda: run._propose_host(url, why))

        @tool(name="finish", description=FINISH_DESCRIPTION, inputSchema=FINISH_SCHEMA, context=True)
        def finish(tool_context, summary: str, gaps: list[str] | None = None) -> str:
            return run._finish(tool_context, summary, gaps)

        return [propose_host, finish]

    def tools(self) -> list[Any]:
        return [
            *self._reading_tools(),
            self._record_finding_tool(),
            self._record_series_tool(),
            *self._closing_tools(),
        ]


def _system_prompt(brief: Brief) -> str:
    subject = SUBJECTS[brief.subject]
    return SYSTEM_PROMPT.format(
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


def _quarantine_report(web: ResearchWeb) -> list[dict[str, Any]]:
    return [
        {
            "host": entry.host,
            "url": entry.url,
            "why": entry.why,
            "robots_status": entry.robots_status,
            "readable": entry.robots_allows,
            "fetches": entry.fetches,
            "proposed_at": entry.proposed_at,
        }
        for entry in web.quarantine.values()
    ]


def _research_summary(run: ResearcherRun, error: str | None) -> dict[str, Any]:
    brief, web = run.brief, run.web
    return {
        "subject": brief.subject,
        "researcher": brief.researcher,
        "findings": len(run.findings),
        "findings_key": brief.prefix + "findings.json",
        "summary": run.summary,
        "gaps": run.gaps,
        "quarantine": _quarantine_report(web),
        "blocked_hosts": dict(web.blocked),
        "requests": dict(web.counts),
        "warnings": web.warnings + ([error] if error else []) + ([] if run.finished else ["finish non appelé"]),
        "tool_calls": run.tool_calls,
    }


def research(
    *,
    brief: Brief,
    store: Store,
    trace: Trace,
    model_factory: ModelFactory,
    model_id: str,
) -> dict[str, Any]:
    web = ResearchWeb(store=store, allowed_hosts=pack_hosts(brief.packs))
    run = ResearcherRun(brief=brief, store=store, web=web, deadline=time.monotonic() + brief.budget_s)
    spec = AgentSpec(
        actor="researcher",
        name=f"Researcher {brief.subject}-{brief.researcher}",
        effort="medium",
        system_prompt=_system_prompt(brief),
        tools=run.tools(),
        max_turns=brief.max_tool_calls + 4,
        max_tokens=8000,
        tool_summaries=TOOL_SUMMARIES,
    )
    error = None
    try:
        run_agent(spec, "Start the mission.", model_factory=model_factory, model_id=model_id, trace=trace)
    except AppError as exc:
        error = f"{exc.code}: {exc.message}"
    store.put_json(brief.prefix + "findings.json", {"brief": brief.to_dict(), "findings": run.findings})
    if error and not run.findings:
        raise AppError("model_error", error)
    return _research_summary(run, error)
