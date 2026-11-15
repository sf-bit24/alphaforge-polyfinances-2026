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
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from strands import tool

from .. import clock, okf
from ..agentkit import AgentSpec, ModelFactory, run_agent, tool_result
from ..errors import AppError
from ..research import checks as research_checks
from ..store import Store
from ..trace import Trace
from . import staging

MAX_ITEMS = 200
NEWS_STALE_DAYS = 90
DATA_STALE_DAYS = 35

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
    news_keys = [info.key for info in store.list("general/actualites/", limit=20000)]
    data_keys = [info.key for info in store.list("general/donnees/", limit=20000)]
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


def validate_items(
    staged: list[tuple[str, Any]], existing: dict[str, set[str]]
) -> tuple[list[Candidate], list[dict[str, str]]]:
    """Contrôles déterministes; renvoie les candidats retenus et les rejets ``{key, reason}``."""
    accepted: list[Candidate] = []
    rejected: list[dict[str, str]] = []
    seen: dict[str, str] = {}
    for key, item in staged:

        def reject(reason: str, key: str = key) -> None:
            rejected.append({"key": key, "reason": reason})

        if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
            reject("élément mal formé (id ou titre manquant)")
            continue
        if item.get("kind") not in staging.ITEM_KINDS:
            reject("type d'élément inconnu")
            continue
        url = item.get("url")
        if not item.get("source") or not isinstance(url, str) or not url.startswith("https://"):
            reject("source manquante (nom et adresse https requis)")
            continue
        published = clock.parse_datetime(item.get("published_at"))
        if published is None:
            reject("date de publication manquante ou illisible")
            continue
        retrieved = clock.parse_datetime(item.get("retrieved_at"))
        if retrieved is None:
            reject("date de récupération manquante ou illisible")
            continue
        if published > retrieved:
            reject("publié après sa date de récupération")
            continue
        if item["kind"] in ("series", "quote"):
            observed = clock.parse_datetime(item.get("observed_at"))
            if observed is None:
                reject("date d'observation manquante")
                continue
            if observed > published:
                reject("date d'observation postérieure à la publication")
                continue
            target = _data_target(item)
            keys = [target]
            if target in existing["data_keys"]:
                reject(f"doublon d'un document existant : {target}")
                continue
        else:
            target, url_hash, title = _news_target(item)
            keys = [f"url:{url_hash}", f"title:{title}"]
            if url_hash in existing["url_hashes"] or target in existing["news_keys"]:
                reject("doublon d'un document existant (même adresse)")
                continue
            if title in existing["titles"]:
                reject("doublon d'un document existant (même titre)")
                continue
        duplicate_of = next((seen[k] for k in keys if k in seen), None)
        if duplicate_of:
            reject(f"doublon dans la collecte : {duplicate_of}")
            continue
        for k in keys:
            seen[k] = key
        accepted.append(Candidate(key=key, item=item, target=target, dedupe=keys))
    return accepted, rejected


def news_doc(candidate: Candidate, now: str) -> okf.OkfDoc:
    item = candidate.item
    data = item.get("data") or {}
    published = clock.parse_datetime(item["published_at"])
    tickers = [t for t in item.get("tickers") or []]
    tags = ["actualites", *candidate.tags, *[t.lower() for t in tickers]]
    source_entry = {
        "id": item["id"],
        "title": item["title"],
        "resource": item["url"],
        "published_at": item["published_at"],
        "retrieved_at": item["retrieved_at"],
    }
    body = [
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
        data={
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
        },
        body="\n".join(body),
    )


def data_doc(candidate: Candidate, now: str) -> okf.OkfDoc:
    item = candidate.item
    data = item.get("data") or {}
    rows = data.get("observations") or data.get("closes") or []
    observed = clock.parse_datetime(item["observed_at"])
    source_entry = {
        "id": item["id"],
        "title": item["title"],
        "resource": item["url"],
        "published_at": item["published_at"],
        "observed_at": item["observed_at"],
        "retrieved_at": item["retrieved_at"],
    }
    basis = data.get("published_at_basis")
    body = [
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
        *[f"| {row['date']} | {row['value']} |" for row in rows[-30:]],
        "",
        "## Limites",
        "",
        "- Une valeur ne sert dans une simulation qu'à partir de sa date de publication, pas de sa date d'observation.",
        "- Les séries FRED sont les dernières valeurs révisées; les cours Yahoo Finance ne sont pas certifiés.",
        "",
    ]
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
        data={
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
        },
        body="\n".join(body),
    )


def write_general_index(store: Store, now: str) -> None:
    infos = [i for i in store.list("general/", limit=5000) if i.key.endswith(".md") and i.key != "general/index.md"]
    infos.sort(key=lambda i: i.key, reverse=True)

    def title(info: Any) -> tuple[str, str]:
        obj = store.get(info.key)
        try:
            return info.key, okf.parse(obj.text).title if obj else info.key
        except okf.OkfError:
            return info.key, info.key

    sections = {
        "methodologie": [],
        "notions": [],
        "societes": [],
        "actualites": [],
        "donnees": [],
        "recherches": [],
        "faits": [],
        "signaux": [],
        "depots": [],
    }
    selected = [
        i for i in infos if i.key.startswith(("general/methodologie/", "general/notions/", "general/societes/"))
    ]
    selected += [i for i in infos if i.key.startswith("general/actualites/")][:150]
    selected += [i for i in infos if i.key.startswith("general/donnees/")][:150]
    for folder in ("recherches", "faits", "signaux", "depots"):
        selected += [i for i in infos if i.key.startswith(f"general/{folder}/")][:100]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for key, doc_title in pool.map(title, selected):
            folder = key.split("/")[1]
            if folder in sections:
                sections[folder].append(f"- [{doc_title}]({key.removeprefix('general/')})")
    counts = {name: sum(1 for i in infos if i.key.startswith(f"general/{name}/")) for name in sections}
    body = [
        "# Base générale d'AlphaForge AI",
        "",
        "Savoir commun à tous les investisseurs : méthodologie, notions financières, chiffres publiés des sociétés, "
        "actualités datées et données publiques. Elle ne "
        "contient rien d'un client. Chaque actualité ou donnée garde sa date de publication et sa date d'observation.",
        "",
        f"## Méthodologie ({counts['methodologie']})",
        "",
        *sorted(sections["methodologie"]),
        "",
        f"## Notions financières ({counts['notions']})",
        "",
        *sorted(sections["notions"]),
        "",
        f"## Sociétés ({counts['societes']})",
        "",
        *sorted(sections["societes"]),
        "",
        f"## Actualités ({counts['actualites']}, les plus récentes)",
        "",
        *sections["actualites"],
        "",
        f"## Données ({counts['donnees']}, les plus récentes)",
        "",
        *sections["donnees"],
        "",
        f"## Synthèses de recherche ({counts['recherches']}, les plus récentes)",
        "",
        *sections["recherches"],
        "",
        f"## Faits sourcés ({counts['faits']}, les plus récents)",
        "",
        *sections["faits"],
        "",
        f"## Signaux de contexte ({counts['signaux']}, les plus récents)",
        "",
        *sections["signaux"],
        "",
        f"## Dépôts réglementaires ({counts['depots']}, les plus récents)",
        "",
        *sections["depots"],
        "",
    ]
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
        body="\n".join(body),
    )
    store.put_text("general/index.md", okf.render(doc))


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
            inputSchema={
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
            },
        )
        def review_items(decisions: list[dict[str, Any]]) -> str:
            unknown = []
            for decision in decisions:
                candidate = state.by_id.get(decision.get("id")) if isinstance(decision, dict) else None
                if candidate is None:
                    unknown.append(decision.get("id") if isinstance(decision, dict) else None)
                    continue
                if decision.get("decision") == "reject":
                    reason = " ".join(str(decision.get("reason") or "rejeté par la revue éditoriale").split())[:200]
                    state.rejections[candidate.item["id"]] = reason
                else:
                    state.rejections.pop(candidate.item["id"], None)
                    candidate.tags = [staging.slugify(str(t), 30) for t in (decision.get("tags") or [])][:3]
            state.reviewed = True
            return tool_result({"status": "ok", "rejected": len(state.rejections), "unknown_ids": unknown})

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


def curate(
    *,
    run_id: str,
    store: Store,
    trace: Trace,
    model_factory: ModelFactory,
    model_id: str,
    budget_seconds: float = 240,
) -> dict[str, Any]:
    started = time.monotonic()
    warnings: list[str] = []
    for role in ("press", "data"):
        marker = store.get_json(staging.marker_key(run_id, role))
        if marker is None:
            warnings.append(f"marqueur {role} absent : curation de ce qui est arrivé")
        elif marker.get("status") != "ok":
            warnings.append(f"marqueur {role} en erreur : {marker.get('error')}")
    staged: list[tuple[str, Any]] = []
    for role in ("press", "data"):
        for info in store.list(staging.staging_prefix(run_id, role), limit=MAX_ITEMS):
            if info.key.endswith("/_done.json") or not info.key.endswith(".json"):
                continue
            try:
                staged.append((info.key, store.get_json(info.key)))
            except (ValueError, json.JSONDecodeError):
                staged.append((info.key, None))
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
        known = existing["news_keys"] | existing["data_keys"]
        for prefix in research_checks.RESEARCH_PREFIXES:
            known |= {info.key for info in store.list(prefix, limit=20000)}
        research_candidates, research_rejected, quarantined = research_checks.validate_research(
            research_staged, known, store, url_hashes=existing["url_hashes"]
        )
        candidates = [*candidates, *research_candidates]
        rejected += research_rejected
    trace.add(
        "deterministic",
        "A6",
        "Contrôles du code",
        None,
        outputs={"accepted": len(candidates), "rejected": len(rejected)},
    )
    if candidates:
        review = ReviewState(candidates)
        listing = [
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
        spec = AgentSpec(
            actor="A6",
            name="Supervisor OKF",
            effort="medium",
            system_prompt=SYSTEM_PROMPT,
            tools=review.tools(),
            max_turns=4,
            max_tokens=16000,
            tool_summaries={
                "review_items": lambda i: {
                    "decisions": len(i.get("decisions") or []),
                    "rejects": sum(
                        1 for d in i.get("decisions") or [] if isinstance(d, dict) and d.get("decision") == "reject"
                    ),
                }
            },
        )
        try:
            run_agent(
                spec,
                "<items>\n" + json.dumps(listing, ensure_ascii=False) + "\n</items>",
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
        kept = []
        for candidate in candidates:
            reason = review.rejections.get(candidate.item["id"])
            if reason:
                rejected.append({"key": candidate.key, "reason": f"revue éditoriale : {reason}"})
            elif not review.reviewed and candidate.item["kind"] == "news":
                rejected.append(
                    {"key": candidate.key, "reason": "revue éditoriale indisponible : actualité non publiée"}
                )
            else:
                kept.append(candidate)
        candidates = kept
    now = clock.iso()
    written = []
    by_id = {c.item["id"]: c for c in candidates}
    briefs = [c for c in candidates if c.item["kind"] == "brief"]
    for brief in briefs:
        refs = getattr(brief, "refs", {})
        missing = [c for c in (brief.item.get("data") or {}).get("citations") or [] if c not in by_id and c not in refs]
        if missing:
            rejected.append({"key": brief.key, "reason": "synthèse : éléments cités rejetés par la revue"})
            candidates = [c for c in candidates if c is not brief]
    for candidate in candidates:
        if time.monotonic() - started > budget_seconds:
            rejected.append({"key": candidate.key, "reason": "délai de curation dépassé"})
            continue
        kind = candidate.item["kind"]
        if kind == "news":
            doc = news_doc(candidate, now)
        elif kind in ("series", "quote"):
            doc = data_doc(candidate, now)
        elif kind == "brief":
            doc = research_checks.brief_doc(candidate, now, {**candidate.refs, **by_id})
        else:
            doc = research_checks.research_doc(candidate, now)
        problems = okf.validate(doc)
        if problems:
            rejected.append({"key": candidate.key, "reason": "document OKF invalide : " + "; ".join(problems)})
            continue
        store.put_text(candidate.target, okf.render(doc))
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
    if research_staged:
        proposals = research_checks.quarantine_proposals(store, run_id)
        if quarantined or proposals:
            store.put_json(
                f"staging/{run_id}/supervisor/quarantine.json",
                {"run_id": run_id, "items": quarantined, "proposed_hosts": proposals, "written_at": now},
            )
        result["quarantined"] = len(quarantined)
        result["proposed_hosts"] = len(proposals)
    return result
