"""A6, ``Supervisor OKF`` : valide ce que A4 et A5 ont collecté et alimente la base générale.

Contrôles du code (toujours appliqués, avec leur raison) :
1. élément lisible, type ``news``, ``series`` ou ``quote``, titre présent;
2. source présente (nom et adresse ``https``);
3. date de publication présente et lisible; date de récupération présente;
4. ``published_at`` <= ``retrieved_at``;
5. date d'observation présente pour une série ou une cotation, et antérieure ou égale à la publication
   (la date d'observation et la date de publication sont gardées toutes les deux dans le document);
6. pas de doublon dans la collecte (même adresse canonique ou même titre);
7. pas de doublon d'un document existant de la base générale (même adresse, même titre, ou même série à la
   même date d'observation).
Puis l'agent relit les éléments retenus comme un éditeur (hors sujet, promotionnel, même événement en double) et
peut en rejeter, avec une raison. Les marqueurs absents ou en erreur de A4 ou A5 n'empêchent pas la curation.
A6 ne lance pas l'ingestion de la Knowledge Base : Step Functions s'en charge après le marqueur.
Chaque document qu'A6 écrit (actualité, donnée, et ceux de la recherche : fait, signal, dépôt, synthèse) l'est avec
son fichier compagnon ``<clé>.metadata.json`` (type, ticker, kind, published_epoch : filtres de la Knowledge Base,
CONTRACTS.md 5.1), par ``general.write_document``.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from strands import tool

from .. import clock, okf
from ..agentkit import AgentSpec, ModelFactory, run_agent, tool_result
from ..errors import AppError
from ..research import checks as research_checks
from ..store import Store
from ..trace import Trace
from . import general, staging

MAX_ITEMS = 200
NEWS_STALE_DAYS = 90
DATA_STALE_DAYS = 35
DATA_KINDS = ("series", "quote")
# Dernières observations reprises dans le tableau d'un document de données.
DOCUMENT_OBSERVATIONS = 30

SYSTEM_PROMPT = """You are A6, the Supervisor OKF of AlphaForge AI's general knowledge base, in a simulation-only \
decision-support prototype for Canadian retail investors. The items below already passed the code's checks (source \
present, publication date present and not after retrieval, observation date kept, exact duplicates removed). Review \
them as an editor, using only their titles, sources, dates and summaries:
- reject news that is off-topic for investors, promotional, clickbait, an opinion piece presented as news, a \
price-prediction article, or that reports the same event as another item of the list (keep the most informative \
and credible one);
- accept data series and quotes unless they look malformed;
- accept facts, market signals, filings and research briefs unless they look malformed, off-topic, or written as \
advice or a forecast (these were researched by subject experts and their values were re-read by the code);
- give every rejection a short reason in French, and 1 to 3 short French tags to accepted news (for example taux, \
inflation, energie, technologie, banques, commerce, marches).
Call review_items once with your decisions (items you do not mention are accepted), then call finish.
"""


@dataclass
class Candidate:
    key: str
    item: dict[str, Any]
    target: str
    dedupe: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def _existing_index(store: Store) -> dict[str, set[str]]:
    # Documents seulement : les fichiers compagnons (.md.metadata.json) ne sont pas des doublons possibles.
    news_keys = [info.key for info in store.list("general/actualites/", limit=20000) if info.key.endswith(".md")]
    data_keys = [info.key for info in store.list("general/donnees/", limit=20000) if info.key.endswith(".md")]
    url_hashes, titles = set(), set()
    for key in news_keys:
        stem = key.rsplit("/", 1)[-1].removesuffix(".md")
        if "-" in stem:
            title_part, _, suffix = stem.rpartition("-")
            url_hashes.add(suffix)
            titles.add(title_part)
    return {"news_keys": set(news_keys), "data_keys": set(data_keys), "url_hashes": url_hashes, "titles": titles}


def _news_target(item: dict[str, Any]) -> tuple[str, str, str]:
    published = clock.parse_datetime(item["published_at"])
    url_hash = staging.short_hash(staging.normalize_url(item["url"]), 8)
    title = staging.title_key(item["title"])
    return f"general/actualites/{published:%Y}/{published:%m}/{title}-{url_hash}.md", url_hash, title


def _data_target(item: dict[str, Any]) -> str:
    data = item.get("data") or {}
    series = data.get("series_id") or data.get("symbol") or item["id"]
    return f"general/donnees/{staging.series_slug(str(series))}/{item['observed_at'][:10]}.md"


class _ItemRejectedError(Exception):
    """Un contrôle du code écarte l'élément; le message est la raison gardée dans les rejets."""


def _require_identified_source(item: Any) -> None:
    if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
        raise _ItemRejectedError("élément mal formé (id ou titre manquant)")
    if item.get("kind") not in staging.ITEM_KINDS:
        raise _ItemRejectedError("type d'élément inconnu")
    url = item.get("url")
    if not item.get("source") or not isinstance(url, str) or not url.startswith("https://"):
        raise _ItemRejectedError("source manquante (nom et adresse https requis)")


def _publication_date(item: dict[str, Any]) -> datetime:
    """Date de publication d'un élément bien daté : lisible, et pas après sa récupération."""
    published = clock.parse_datetime(item.get("published_at"))
    if published is None:
        raise _ItemRejectedError("date de publication manquante ou illisible")
    retrieved = clock.parse_datetime(item.get("retrieved_at"))
    if retrieved is None:
        raise _ItemRejectedError("date de récupération manquante ou illisible")
    if published > retrieved:
        raise _ItemRejectedError("publié après sa date de récupération")
    return published


def _data_placement(item: dict[str, Any], published: datetime, existing: dict[str, set[str]]) -> tuple[str, list[str]]:
    """Document cible d'une série ou d'une cotation, et ses clés de doublon."""
    observed = clock.parse_datetime(item.get("observed_at"))
    if observed is None:
        raise _ItemRejectedError("date d'observation manquante")
    if observed > published:
        raise _ItemRejectedError("date d'observation postérieure à la publication")
    target = _data_target(item)
    if target in existing["data_keys"]:
        raise _ItemRejectedError(f"doublon d'un document existant : {target}")
    return target, [target]


def _news_placement(item: dict[str, Any], existing: dict[str, set[str]]) -> tuple[str, list[str]]:
    """Document cible d'une actualité, et ses clés de doublon (adresse canonique et titre)."""
    target, url_hash, title = _news_target(item)
    if url_hash in existing["url_hashes"] or target in existing["news_keys"]:
        raise _ItemRejectedError("doublon d'un document existant (même adresse)")
    if title in existing["titles"]:
        raise _ItemRejectedError("doublon d'un document existant (même titre)")
    return target, [f"url:{url_hash}", f"title:{title}"]


def _checked_candidate(key: str, item: Any, existing: dict[str, set[str]], first_keys: dict[str, str]) -> Candidate:
    """Candidat d'un élément qui passe tous les contrôles; lève ``_ItemRejectedError`` avec la raison sinon.

    ``first_keys`` garde, pour chaque clé de doublon déjà vue dans la collecte, l'élément qui l'a posée.
    """
    _require_identified_source(item)
    published = _publication_date(item)
    if item["kind"] in DATA_KINDS:
        target, dedupe_keys = _data_placement(item, published, existing)
    else:
        target, dedupe_keys = _news_placement(item, existing)
    duplicate_of = next((first_keys[k] for k in dedupe_keys if k in first_keys), None)
    if duplicate_of:
        raise _ItemRejectedError(f"doublon dans la collecte : {duplicate_of}")
    for dedupe_key in dedupe_keys:
        first_keys[dedupe_key] = key
    return Candidate(key=key, item=item, target=target, dedupe=dedupe_keys)


def validate_items(
    staged: list[tuple[str, Any]], existing: dict[str, set[str]]
) -> tuple[list[Candidate], list[dict[str, str]]]:
    """Contrôles déterministes; renvoie les candidats retenus et les rejets ``{key, reason}``."""
    accepted: list[Candidate] = []
    rejected: list[dict[str, str]] = []
    first_keys: dict[str, str] = {}
    for key, item in staged:
        try:
            accepted.append(_checked_candidate(key, item, existing, first_keys))
        except _ItemRejectedError as rejection:
            rejected.append({"key": key, "reason": str(rejection)})
    return accepted, rejected


def _news_body(item: dict[str, Any], data: dict[str, Any], tickers: list[str]) -> str:
    lines = [
        f"# {item['title']}",
        "",
        f"- Source : {item['source']} — <{item['url']}>",
        f"- Publiée le : {item['published_at']}"
        + (" (date vue par GDELT)" if data.get("published_at_basis") == "gdelt_seendate" else ""),
        f"- Récupérée le : {item['retrieved_at']}",
        f"- Langue de la source : {item.get('language') or 'inconnue'}",
        f"- Titres concernés : {', '.join(tickers) or 'aucun'}",
        "",
        "## Résumé",
        "",
        item.get("summary") or "",
        "",
        f"Résumé rédigé par {data.get('collected_by') or 'A4'} à partir du titre et de l'extrait fournis par "
        "la source; "
        "à vérifier dans l'article.",
        "",
        "## Limites",
        "",
        "- Contenu non vérifié au-delà du titre et de l'extrait de la source.",
        "- Une nouvelle n'entre dans une simulation qu'à partir de sa date de publication.",
        "",
    ]
    return "\n".join(lines)


def _news_data(candidate: Candidate, data: dict[str, Any], tickers: list[str]) -> dict[str, Any]:
    item = candidate.item
    return {
        "kind": "news",
        "item_id": item["id"],
        "url": item["url"],
        "source": item["source"],
        "published_at": item["published_at"],
        "observed_at": item.get("observed_at"),
        "retrieved_at": item["retrieved_at"],
        "language": item.get("language"),
        "tickers": tickers,
        "provider": data.get("provider"),
        "published_at_basis": data.get("published_at_basis", "source"),
        "collected_by": data.get("collected_by") or "A4",
        "run_id": data.get("run_id"),
        "staging_key": candidate.key,
    }


def news_doc(candidate: Candidate, now: str) -> okf.OkfDoc:
    item = candidate.item
    data = item.get("data") or {}
    published = clock.parse_datetime(item["published_at"])
    tickers = list(item.get("tickers") or [])
    tags = ["actualites", *candidate.tags, *[ticker.lower() for ticker in tickers]]
    source_entry = {
        "id": item["id"],
        "title": item["title"],
        "resource": item["url"],
        "published_at": item["published_at"],
        "retrieved_at": item["retrieved_at"],
    }
    return okf.new_doc(
        type="News",
        title=item["title"],
        description=f"Actualité du {published:%Y-%m-%d} ({item['source']}). {str(item.get('summary') or '')[:160]}",
        tags=list(dict.fromkeys(tags)),
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A6",
        at=now,
        status="stable",
        stale_after=clock.iso(published + timedelta(days=NEWS_STALE_DAYS)),
        sources=[source_entry],
        data=_news_data(candidate, data, tickers),
        body=_news_body(item, data, tickers),
    )


def _data_body(item: dict[str, Any], data: dict[str, Any]) -> str:
    rows = data.get("observations") or data.get("closes") or []
    basis = data.get("published_at_basis")
    lines = [
        f"# {item['title']}",
        "",
        f"- Source : {item['source']} — <{item['url']}>",
        f"- Date d'observation : {item['observed_at']}",
        f"- Date de publication : {item['published_at']}"
        + (
            " (borne supérieure : date de récupération, la source ne donne pas la date exacte)"
            if basis == "retrieved_at_upper_bound"
            else ""
        ),
        f"- Récupérée le : {item['retrieved_at']}",
        f"- Unité : {data.get('unit') or data.get('currency') or '—'}"
        f" · Fréquence : {data.get('frequency') or 'quotidienne'}",
        "",
        "## Résumé",
        "",
        item.get("summary") or "",
        "",
        "## Observations",
        "",
        "| Date | Valeur |",
        "| --- | --- |",
        *[f"| {row['date']} | {row['value']} |" for row in rows[-DOCUMENT_OBSERVATIONS:]],
        "",
        "## Limites",
        "",
        "- Une valeur ne sert dans une simulation qu'à partir de sa date de publication, pas de sa date d'observation.",
        "- Les séries FRED sont les dernières valeurs révisées; les cours Yahoo Finance ne sont pas certifiés.",
        "",
    ]
    return "\n".join(lines)


def _data_payload(candidate: Candidate, data: dict[str, Any]) -> dict[str, Any]:
    item = candidate.item
    return {
        "kind": item["kind"],
        "item_id": item["id"],
        **{k: v for k, v in data.items() if k != "run_id"},
        "url": item["url"],
        "source": item["source"],
        "published_at": item["published_at"],
        "observed_at": item["observed_at"],
        "retrieved_at": item["retrieved_at"],
        "run_id": data.get("run_id"),
        "staging_key": candidate.key,
    }


def data_doc(candidate: Candidate, now: str) -> okf.OkfDoc:
    item = candidate.item
    data = item.get("data") or {}
    observed = clock.parse_datetime(item["observed_at"])
    source_entry = {
        "id": item["id"],
        "title": item["title"],
        "resource": item["url"],
        "published_at": item["published_at"],
        "observed_at": item["observed_at"],
        "retrieved_at": item["retrieved_at"],
    }
    series = data.get("series_id") or data.get("symbol")
    return okf.new_doc(
        type="Data Series",
        title=item["title"],
        description=f"{data.get('label') or series} : observation au {item['observed_at'][:10]}, {item['source']}.",
        tags=list(dict.fromkeys(["donnees", staging.series_slug(str(series)), *candidate.tags])),
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A6",
        at=now,
        status="stable",
        stale_after=clock.iso(observed + timedelta(days=DATA_STALE_DAYS)),
        sources=[source_entry],
        data=_data_payload(candidate, data),
        body=_data_body(item, data),
    )


@dataclass(frozen=True)
class _IndexSection:
    """Une rubrique de l'index de la base générale."""

    folder: str
    heading: str
    # Nombre de documents listés, les plus récents d'abord; ``None`` : tous, par ordre alphabétique.
    latest: int | None


INDEX_SECTIONS = (
    _IndexSection("methodologie", "Méthodologie ({count})", None),
    _IndexSection("notions", "Notions financières ({count})", None),
    _IndexSection("societes", "Sociétés ({count})", None),
    _IndexSection("actualites", "Actualités ({count}, les plus récentes)", 150),
    _IndexSection("donnees", "Données ({count}, les plus récentes)", 150),
    _IndexSection("recherches", "Synthèses de recherche ({count}, les plus récentes)", 100),
    _IndexSection("faits", "Faits sourcés ({count}, les plus récents)", 100),
    _IndexSection("signaux", "Signaux de contexte ({count}, les plus récents)", 100),
    _IndexSection("depots", "Dépôts réglementaires ({count}, les plus récents)", 100),
)


def _document_title(store: Store, key: str) -> str:
    """Titre du document, ou sa clé s'il est absent ou illisible."""
    stored = store.get(key)
    try:
        return okf.parse(stored.text).title if stored else key
    except okf.OkfError:
        return key


def _index_entries(store: Store, keys: list[str]) -> dict[str, list[str]]:
    """Liens de l'index par rubrique; ``keys`` est trié du plus récent au plus ancien."""
    listed = {
        section.folder: [key for key in keys if key.startswith(f"general/{section.folder}/")][: section.latest]
        for section in INDEX_SECTIONS
    }
    selected = [key for folder_keys in listed.values() for key in folder_keys]
    with ThreadPoolExecutor(max_workers=8) as pool:
        titles = dict(zip(selected, pool.map(partial(_document_title, store), selected), strict=True))
    return {
        folder: [f"- [{titles[key]}]({key.removeprefix('general/')})" for key in folder_keys]
        for folder, folder_keys in listed.items()
    }


def _index_body(entries: dict[str, list[str]], counts: dict[str, int]) -> str:
    lines = [
        "# Base générale d'AlphaForge AI",
        "",
        "Savoir commun à tous les investisseurs : méthodologie, notions financières, chiffres publiés des sociétés, "
        "actualités datées et données publiques. Elle ne "
        "contient rien d'un client. Chaque actualité ou donnée garde sa date de publication et sa date d'observation.",
        "",
    ]
    for section in INDEX_SECTIONS:
        links = entries[section.folder]
        lines += [
            "## " + section.heading.format(count=counts[section.folder]),
            "",
            *(sorted(links) if section.latest is None else links),
            "",
        ]
    return "\n".join(lines)


def write_general_index(store: Store, now: str) -> None:
    keys = [
        info.key
        for info in store.list("general/", limit=5000)
        if info.key.endswith(".md") and info.key != "general/index.md"
    ]
    keys.sort(reverse=True)
    entries = _index_entries(store, keys)
    counts = {
        section.folder: sum(1 for key in keys if key.startswith(f"general/{section.folder}/"))
        for section in INDEX_SECTIONS
    }
    doc = okf.new_doc(
        type="Index",
        title="Base générale",
        description=(
            "Index de la base générale : méthodologie, notions financières, sociétés, actualités et données "
            "publiques datées."
        ),
        tags=["index", "base-generale"],
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A6",
        at=now,
        status="stable",
        sources=[],
        data={"counts": counts},
        body=_index_body(entries, counts),
    )
    store.put_text("general/index.md", okf.render(doc))


REVIEW_ITEMS_SCHEMA = {
    "json": {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "decision": {"type": "string", "enum": ["accept", "reject"]},
                        "reason": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                    },
                    "required": ["id", "decision"],
                },
            }
        },
        "required": ["decisions"],
    }
}


class ReviewState:
    def __init__(self, candidates: list[Candidate]):
        self.by_id = {c.item["id"]: c for c in candidates}
        self.rejections: dict[str, str] = {}
        self.reviewed = False
        self.finished = False

    def tools(self) -> list[Any]:
        state = self

        @tool(
            name="review_items",
            description="Record editorial decisions: id, decision accept or reject, reason (French), tags.",
            inputSchema=REVIEW_ITEMS_SCHEMA,
        )
        def review_items(decisions: list[dict[str, Any]]) -> str:
            return tool_result(state.record_decisions(decisions))

        @tool(
            name="finish",
            description="End the review.",
            inputSchema={"json": {"type": "object", "properties": {"note": {"type": "string"}}}},
            context=True,
        )
        def finish(tool_context, note: str = "") -> str:
            state.finished = True
            tool_context.agent.cancel(after_current_tools=True)
            return tool_result({"status": "ok"})

        return [review_items, finish]

    def record_decisions(self, decisions: list[dict[str, Any]]) -> dict[str, Any]:
        unknown = []
        for decision in decisions:
            candidate = self.by_id.get(decision.get("id")) if isinstance(decision, dict) else None
            if candidate is None:
                unknown.append(decision.get("id") if isinstance(decision, dict) else None)
            elif decision.get("decision") == "reject":
                reason = " ".join(str(decision.get("reason") or "rejeté par la revue éditoriale").split())[:200]
                self.rejections[candidate.item["id"]] = reason
            else:
                self.rejections.pop(candidate.item["id"], None)
                candidate.tags = [staging.slugify(str(tag), 30) for tag in (decision.get("tags") or [])][:3]
        self.reviewed = True
        return {"status": "ok", "rejected": len(self.rejections), "unknown_ids": unknown}


def _marker_warnings(store: Store, run_id: str) -> list[str]:
    """Un marqueur de A4 ou A5 absent ou en erreur n'empêche pas la curation : il devient un avertissement."""
    warnings: list[str] = []
    for role in ("press", "data"):
        marker = store.get_json(staging.marker_key(run_id, role))
        if marker is None:
            warnings.append(f"marqueur {role} absent : curation de ce qui est arrivé")
        elif marker.get("status") != "ok":
            warnings.append(f"marqueur {role} en erreur : {marker.get('error')}")
    return warnings


def _read_staged(store: Store, run_id: str) -> list[tuple[str, Any]]:
    """Éléments déposés par A4 et A5; un élément illisible vaut ``None`` et sera rejeté par les contrôles."""
    staged: list[tuple[str, Any]] = []
    for role in ("press", "data"):
        for info in store.list(staging.staging_prefix(run_id, role), limit=MAX_ITEMS):
            if info.key.endswith("/_done.json") or not info.key.endswith(".json"):
                continue
            try:
                staged.append((info.key, store.get_json(info.key)))
            except (ValueError, json.JSONDecodeError):
                staged.append((info.key, None))
    return staged


def _validate_research(
    store: Store, research_staged: list[Any], existing: dict[str, set[str]]
) -> tuple[list[Candidate], list[dict[str, str]], list[dict[str, Any]]]:
    known = existing["news_keys"] | existing["data_keys"]
    for prefix in research_checks.RESEARCH_PREFIXES:
        known |= {info.key for info in store.list(prefix, limit=20000)}
    return research_checks.validate_research(research_staged, known, store, url_hashes=existing["url_hashes"])


@dataclass
class _Intake:
    """Ce que les contrôles du code ont retenu, rejeté et mis en quarantaine."""

    candidates: list[Candidate]
    rejected: list[dict[str, str]]
    quarantined: list[dict[str, Any]]
    has_research: bool


def _checked_intake(store: Store, run_id: str, trace: Trace) -> _Intake:
    staged = _read_staged(store, run_id)
    research_staged = research_checks.list_staged(store, run_id)
    trace.add(
        "storage",
        "store",
        "Éléments collectés lus",
        f"staging/{run_id}/",
        outputs={"items": len(staged), "research_items": len(research_staged)},
    )
    existing = _existing_index(store)
    candidates, rejected = validate_items(staged, existing)
    quarantined: list[dict[str, Any]] = []
    if research_staged:
        research_candidates, research_rejected, quarantined = _validate_research(store, research_staged, existing)
        candidates = [*candidates, *research_candidates]
        rejected += research_rejected
    trace.add(
        "deterministic",
        "A6",
        "Contrôles du code",
        None,
        outputs={"accepted": len(candidates), "rejected": len(rejected)},
    )
    return _Intake(candidates, rejected, quarantined, has_research=bool(research_staged))


def _review_listing(candidates: list[Candidate]) -> list[dict[str, Any]]:
    """Ce que l'agent lit de chaque élément pour sa revue éditoriale."""
    return [
        {
            "id": c.item["id"],
            "kind": c.item["kind"],
            "title": c.item["title"],
            "source": c.item["source"],
            "published_at": c.item["published_at"],
            "observed_at": c.item.get("observed_at"),
            "tickers": c.item.get("tickers"),
            "summary": str(c.item.get("summary") or "")[:300],
        }
        for c in candidates
    ]


def _review_summary(tool_input: dict[str, Any]) -> dict[str, int]:
    decisions = tool_input.get("decisions") or []
    return {
        "decisions": len(decisions),
        "rejects": sum(1 for d in decisions if isinstance(d, dict) and d.get("decision") == "reject"),
    }


def _run_editorial_review(
    candidates: list[Candidate], warnings: list[str], *, model_factory: ModelFactory, model_id: str, trace: Trace
) -> ReviewState:
    """Fait relire les candidats par l'agent; une revue indisponible ou muette devient un avertissement."""
    review = ReviewState(candidates)
    spec = AgentSpec(
        actor="A6",
        name="Supervisor OKF",
        effort="medium",
        system_prompt=SYSTEM_PROMPT,
        tools=review.tools(),
        max_turns=4,
        max_tokens=16000,
        tool_summaries={"review_items": _review_summary},
    )
    try:
        run_agent(
            spec,
            "<items>\n" + json.dumps(_review_listing(candidates), ensure_ascii=False) + "\n</items>",
            model_factory=model_factory,
            model_id=model_id,
            trace=trace,
        )
    except AppError as exc:
        warnings.append(f"revue éditoriale indisponible ({exc.code})")
    if not review.reviewed:
        # Sans revue, seules les données dont le texte vient du code sont écrites ; les actualités
        # (résumé rédigé par A4) attendent la prochaine collecte, qui les proposera de nouveau.
        warnings.append("A6 n'a rendu aucune décision : actualités non publiées, données écrites")
    return review


def _kept_after_review(
    review: ReviewState, candidates: list[Candidate], rejected: list[dict[str, str]]
) -> list[Candidate]:
    kept = []
    for candidate in candidates:
        reason = review.rejections.get(candidate.item["id"])
        if reason:
            rejected.append({"key": candidate.key, "reason": f"revue éditoriale : {reason}"})
        elif not review.reviewed and candidate.item["kind"] == "news":
            rejected.append({"key": candidate.key, "reason": "revue éditoriale indisponible : actualité non publiée"})
        else:
            kept.append(candidate)
    return kept


def _without_orphan_briefs(
    candidates: list[Candidate], by_id: dict[str, Candidate], rejected: list[dict[str, str]]
) -> list[Candidate]:
    """Écarte les synthèses qui citent un élément que la revue a rejeté."""
    briefs = [c for c in candidates if c.item["kind"] == "brief"]
    for brief in briefs:
        refs = getattr(brief, "refs", {})
        missing = [c for c in (brief.item.get("data") or {}).get("citations") or [] if c not in by_id and c not in refs]
        if missing:
            rejected.append({"key": brief.key, "reason": "synthèse : éléments cités rejetés par la revue"})
            candidates = [c for c in candidates if c is not brief]
    return candidates


def _document_for(candidate: Candidate, now: str, by_id: dict[str, Candidate]) -> okf.OkfDoc:
    kind = candidate.item["kind"]
    if kind == "news":
        return news_doc(candidate, now)
    if kind in DATA_KINDS:
        return data_doc(candidate, now)
    if kind == "brief":
        return research_checks.brief_doc(candidate, now, {**candidate.refs, **by_id})
    return research_checks.research_doc(candidate, now)


def _quarantine_report(store: Store, run_id: str, quarantined: list[dict[str, Any]], now: str) -> dict[str, int]:
    """Écrit la quarantaine de la recherche, s'il y en a une, et renvoie ses compteurs."""
    proposals = research_checks.quarantine_proposals(store, run_id)
    if quarantined or proposals:
        store.put_json(
            f"staging/{run_id}/supervisor/quarantine.json",
            {"run_id": run_id, "items": quarantined, "proposed_hosts": proposals, "written_at": now},
        )
    return {"quarantined": len(quarantined), "proposed_hosts": len(proposals)}


def curate(  # noqa: PLR0913 - signature gardée : le service de collecte et les tests l'appellent par mots-clés
    *,
    run_id: str,
    store: Store,
    trace: Trace,
    model_factory: ModelFactory,
    model_id: str,
    budget_seconds: float = 240,
) -> dict[str, Any]:
    started = time.monotonic()
    warnings = _marker_warnings(store, run_id)
    intake = _checked_intake(store, run_id, trace)
    candidates, rejected = intake.candidates, intake.rejected
    if candidates:
        review = _run_editorial_review(
            candidates, warnings, model_factory=model_factory, model_id=model_id, trace=trace
        )
        candidates = _kept_after_review(review, candidates, rejected)
    now = clock.iso()
    written = []
    by_id = {c.item["id"]: c for c in candidates}
    candidates = _without_orphan_briefs(candidates, by_id, rejected)
    for candidate in candidates:
        if time.monotonic() - started > budget_seconds:
            rejected.append({"key": candidate.key, "reason": "délai de curation dépassé"})
            continue
        doc = _document_for(candidate, now, by_id)
        problems = okf.validate(doc)
        if problems:
            rejected.append({"key": candidate.key, "reason": "document OKF invalide : " + "; ".join(problems)})
            continue
        general.write_document(store, candidate.target, doc)
        written.append(candidate.target)
    trace.add(
        "storage",
        "store",
        "Documents écrits dans la base générale",
        None,
        outputs={"written": len(written), "rejected": len(rejected)},
    )
    if written:
        write_general_index(store, now)
    result: dict[str, Any] = {"written": written, "rejected": rejected, "warnings": warnings}
    if intake.has_research:
        result.update(_quarantine_report(store, run_id, intake.quarantined, now))
    return result
