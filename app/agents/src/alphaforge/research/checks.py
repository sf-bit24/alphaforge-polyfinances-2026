"""Contrôles d'A6 sur les éléments de la recherche par experts, et documents OKF des nouveaux types.

S'ajoutent aux contrôles de la version 1 (source, dates, doublons), avec une raison pour chaque rejet :
1. ancrage : chaque valeur (et chaque ligne d'une série) est relue au localisateur dans la réponse archivée;
2. licence : ``licence`` et ``attribution_text`` présents; robots.txt respecté, sauf exception assumée;
3. quarantaine : un élément d'un hôte proposé par un chercheur est retenu hors de la base générale;
4. nombres : le titre et le résumé n'empruntent leurs nombres qu'aux valeurs lues et à leurs dates;
5. point dans le temps : rien de publié après ``as_of``;
6. cotes : règles de résolution exigées, palier de qualité gardé;
7. synthèses : chaque citation renvoie à un élément retenu, chaque nombre à un élément cité.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from .. import clock, okf
from ..collect import staging
from ..store import Store
from . import documents, items
from .packs import HOSTS

FACT_STALE_DAYS = 365
SIGNAL_STALE_DAYS = 7
FILING_STALE_DAYS = 730
BRIEF_STALE_DAYS = 30
SKIPPED_FILES = ("brief.json", "plan.json")
RESEARCH_PREFIXES = ("general/faits/", "general/signaux/", "general/depots/", "general/recherches/")


@dataclass
class ResearchCandidate:
    key: str
    item: dict[str, Any]
    target: str
    dedupe: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def list_staged(store: Store, run_id: str) -> list[tuple[str, Any]]:
    staged = []
    for prefix in (f"staging/{run_id}/experts/", f"staging/{run_id}/router/"):
        for info in store.list(prefix, limit=2000):
            name = info.key.rsplit("/", 1)[-1]
            if name.startswith("_") or name in SKIPPED_FILES or not name.endswith(".json"):
                continue
            try:
                staged.append((info.key, store.get_json(info.key)))
            except ValueError:
                staged.append((info.key, None))
    return staged


def quarantine_proposals(store: Store, run_id: str) -> list[dict[str, Any]]:
    proposals = []
    for info in store.list(f"staging/{run_id}/researchers/", limit=2000):
        if not info.key.endswith("/_done.json"):
            continue
        marker = store.get_json(info.key) or {}
        for entry in marker.get("quarantine") or []:
            proposals.append({**entry, "researcher": f"{marker.get('subject')}-{marker.get('researcher')}"})
    return proposals


# ----------------------------------------------------------------------------- cibles
def _hash(item: dict[str, Any]) -> str:
    return staging.short_hash(str(item.get("id")), 8)


def target(item: dict[str, Any]) -> str:
    kind = item["kind"]
    data = item.get("data") or {}
    observed = str(item.get("observed_at") or item.get("published_at") or "")[:10]
    if kind == "fact":
        return (
            f"general/faits/{staging.slugify(str(data.get('label') or item['title']), 50)}/{observed}-{_hash(item)}.md"
        )
    if kind == "signal":
        slug = staging.slugify(str(data.get("label") or item["title"]), 50)
        return f"general/signaux/{slug}/{observed}-{_hash(item)}.md"
    if kind == "filing":
        owner = (item.get("tickers") or [None])[0] or (data.get("provenance") or {}).get("host") or "depot"
        accession = (data.get("values") or {}).get("accession") or (data.get("values") or {}).get("accessionNumber")
        return (
            f"general/depots/{staging.slugify(str(owner), 20)}/{staging.slugify(str(accession or item['id']), 40)}.md"
        )
    if kind == "brief":
        published = clock.parse_datetime(item.get("published_at")) or clock.utcnow()
        return f"general/recherches/{published:%Y}/{published:%m}/{staging.slugify(item['title'], 60)}-{_hash(item)}.md"
    if kind == "news":
        published = clock.parse_datetime(item["published_at"])
        url_hash = staging.short_hash(staging.normalize_url(item["url"]), 8)
        return f"general/actualites/{published:%Y}/{published:%m}/{staging.title_key(item['title'])}-{url_hash}.md"
    series = data.get("series_id") or data.get("symbol") or item["id"]
    return f"general/donnees/{staging.series_slug(str(series))}/{observed}.md"


# ----------------------------------------------------------------------------- ancrage
def _archive_tree(store: Store, key: str, cache: dict[str, Any]) -> Any:
    if key in cache:
        return cache[key]
    document = store.get_json(key) if key else None
    if not isinstance(document, dict) or "body" not in document:
        cache[key] = None
        return None
    try:
        tree = documents.parse_tree(str(document["body"]).encode("utf-8"), document.get("format") or "json")
    except documents.DocumentError:
        tree = None
    cache[key] = tree
    return tree


def check_grounding(store: Store, item: dict[str, Any], cache: dict[str, Any]) -> str | None:
    data = item.get("data") or {}
    prov = data.get("provenance") or {}
    tree = _archive_tree(store, str(prov.get("archive_key") or ""), cache)
    if tree is None:
        return "réponse archivée introuvable ou illisible : valeur non vérifiable"
    values = data.get("values") or {}
    for name, locator in (prov.get("locators") or {}).items():
        try:
            value = documents.scalar(documents.resolve(tree, locator))
        except documents.DocumentError as exc:
            return f"localisateur {name} non résolu dans l'archive : {exc}"
        if value[:2000] != str(values.get(name)):
            return f"valeur {name} différente de l'archive"
    spec = prov.get("series_spec")
    if item["kind"] == "series":
        if not spec:
            return "série sans spécification de lignes"
        try:
            rows = documents.extract_rows(tree, spec["rows"], spec["date_field"], spec["value_field"])
        except documents.DocumentError as exc:
            return f"lignes de la série non relues : {exc}"
        archived = {(str(r["date"])[:10], r["value"]) for r in rows}
        from .researcher import parse_any_date

        archived |= {((parse_any_date(r["date"]) or "")[:10], r["value"]) for r in rows}
        for observation in data.get("observations") or []:
            if (observation.get("date"), observation.get("value")) not in archived:
                return f"observation {observation.get('date')} absente de l'archive"
    return None


# ----------------------------------------------------------------------------- validation
def validate_research(
    staged: list[tuple[str, Any]],
    existing_keys: set[str],
    store: Store,
    *,
    url_hashes: set[str] | None = None,
) -> tuple[list[ResearchCandidate], list[dict[str, str]], list[dict[str, Any]]]:
    accepted: list[ResearchCandidate] = []
    rejected: list[dict[str, str]] = []
    quarantined: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    cache: dict[str, Any] = {}
    briefs: list[tuple[str, dict[str, Any]]] = []
    for key, item in staged:

        def reject(reason: str, key: str = key) -> None:
            rejected.append({"key": key, "reason": reason})

        if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
            reject("élément mal formé (id ou titre manquant)")
            continue
        kind = item.get("kind")
        if kind not in staging.ITEM_KINDS + staging.RESEARCH_KINDS:
            reject("type d'élément inconnu")
            continue
        if kind == "brief":
            briefs.append((key, item))
            continue
        url = item.get("url")
        if not item.get("source") or not isinstance(url, str) or not url.startswith("https://"):
            reject("source manquante (nom et adresse https requis)")
            continue
        published = clock.parse_datetime(item.get("published_at"))
        retrieved = clock.parse_datetime(item.get("retrieved_at"))
        if published is None or retrieved is None:
            reject("date de publication ou de récupération manquante")
            continue
        if published > retrieved:
            reject("publié après sa date de récupération")
            continue
        if kind in ("series", "quote", "fact", "signal"):
            observed = clock.parse_datetime(str(item.get("observed_at") or "")[:10])
            if observed is None:
                reject("date d'observation manquante")
                continue
            if observed.date() > published.date():
                reject("date d'observation postérieure à la publication")
                continue
        data = item.get("data") or {}
        prov = data.get("provenance") or {}
        if not prov.get("licence") or not prov.get("attribution_text"):
            reject("licence ou texte d'attribution manquant")
            continue
        host = str(prov.get("host") or "")
        if prov.get("host_status") == "quarantined":
            quarantined.append({"key": key, "id": item["id"], "host": host, "title": item["title"]})
            reject("hôte en quarantaine : en attente d'approbation humaine de sa licence")
            continue
        exception = host in HOSTS and HOSTS[host].robots_exception
        if prov.get("robots_ok_at_fetch") is not True and not exception:
            reject("robots.txt non respecté à la collecte")
            continue
        as_of = clock.parse_datetime(prov.get("as_of")) if prov.get("as_of") else None
        if as_of is not None and published > as_of:
            reject("publié après le point dans le temps demandé (as_of)")
            continue
        problem = check_grounding(store, item, cache)
        if problem:
            reject(problem)
            continue
        missing = documents.grounded(f"{item['title']} {item.get('summary') or ''}", items.allowed_numbers(item))
        if missing:
            reject("nombres non fondés dans le titre ou le résumé : " + ", ".join(missing[:4]))
            continue
        if kind == "signal" and host in items.MARKET_HOSTS and not (data.get("market") or {}).get("resolution_rules"):
            reject("cote de marché sans règles de résolution")
            continue
        path = target(item)
        dedupe = [path, f"id:{item['id']}"]
        if kind == "news":
            url_hash = staging.short_hash(staging.normalize_url(item["url"]), 8)
            dedupe.append(f"url:{url_hash}")
            if url_hash in (url_hashes or set()):
                reject("doublon d'un document existant (même adresse)")
                continue
        if path in existing_keys:
            reject(f"doublon d'un document existant : {path}")
            continue
        duplicate_of = next((seen[k] for k in dedupe if k in seen), None)
        if duplicate_of:
            reject(f"doublon dans la collecte : {duplicate_of}")
            continue
        for k in dedupe:
            seen[k] = key
        accepted.append(ResearchCandidate(key=key, item=item, target=path, dedupe=dedupe, tags=data.get("tags") or []))
    by_id = {c.item["id"]: c for c in accepted}
    for key, item in briefs:
        data = item.get("data") or {}
        citations = [c for c in data.get("citations") or [] if isinstance(c, str)]
        missing_ids = [c for c in citations if c not in by_id]
        if not citations or missing_ids:
            rejected.append(
                {"key": key, "reason": "synthèse : citations absentes ou non retenues " + ", ".join(missing_ids[:4])}
            )
            continue
        allowed = [n for c in citations for n in items.allowed_numbers(by_id[c].item)]
        missing = documents.grounded(f"{item['title']} {data.get('text') or ''}", allowed)
        if missing:
            rejected.append({"key": key, "reason": "synthèse : nombres non fondés " + ", ".join(missing[:4])})
            continue
        path = target(item)
        if path in existing_keys:
            rejected.append({"key": key, "reason": f"doublon d'un document existant : {path}"})
            continue
        accepted.append(ResearchCandidate(key=key, item=item, target=path, dedupe=[path]))
    return accepted, rejected, quarantined


# ----------------------------------------------------------------------------- documents
_TYPES = {"fact": "Fact", "signal": "Market Signal", "filing": "Regulatory Filing"}
_FOLDER_TAG = {"fact": "faits", "signal": "signaux", "filing": "depots"}
_STALE = {"fact": FACT_STALE_DAYS, "signal": SIGNAL_STALE_DAYS, "filing": FILING_STALE_DAYS}


def _source_entry(item: dict[str, Any]) -> dict[str, Any]:
    prov = (item.get("data") or {}).get("provenance") or {}
    return {
        "id": item["id"],
        "title": item["title"],
        "resource": item.get("url"),
        "published_at": item.get("published_at"),
        "observed_at": item.get("observed_at"),
        "retrieved_at": item.get("retrieved_at"),
        "licence": prov.get("licence"),
        "attribution": prov.get("attribution_text"),
    }


def research_doc(candidate: ResearchCandidate, now: str) -> okf.OkfDoc:
    item = candidate.item
    kind = item["kind"]
    data = item.get("data") or {}
    prov = data.get("provenance") or {}
    market = data.get("market") or {}
    values = data.get("values") or {}
    anchor = clock.parse_datetime(str(item.get("observed_at") or item.get("published_at"))[:10]) or clock.utcnow()
    body = [
        f"# {item['title']}",
        "",
        f"- Source : {item['source']} — <{item['url']}>",
        f"- {prov.get('attribution_text')}",
        f"- Licence : {prov.get('licence')}" + (f" — <{prov['licence_url']}>" if prov.get("licence_url") else ""),
        f"- Date d'observation : {item.get('observed_at') or '—'}",
        f"- Date de publication : {item.get('published_at')}"
        + (
            " (borne supérieure : date de récupération)"
            if prov.get("publication_basis") == "retrieved_at_upper_bound"
            else ""
        ),
        f"- Récupérée le : {item.get('retrieved_at')}",
        f"- Recherche : {data.get('collected_by')}",
        "",
        "## Constat",
        "",
        item.get("summary") or "",
        "",
        "## Valeurs lues dans la source",
        "",
        "| Champ | Valeur |",
        "| --- | --- |",
        *[f"| {k} | {str(v)[:200].replace('|', '/')} |" for k, v in values.items()],
        "",
    ]
    if market:
        body += [
            "## Marché",
            "",
            f"- Palier de qualité : {market.get('quality_tier')} "
            "(élevé : volume d'au moins 1 M et fourchette d'au plus 2 cents)",
            f"- Règles de résolution, telles quelles : {str(market.get('resolution_rules') or '—')[:1500]}",
            "",
        ]
    body += [
        "## Limites",
        "",
        "- Contexte, pas un signal d'achat ou de vente." if kind == "signal" else "- Fait sourcé, à lire avec sa date.",
        "- Une valeur ne sert dans une simulation qu'à partir de sa date de publication.",
        *([f"- {prov['licence_note']}"] if prov.get("licence_note") else []),
        "",
    ]
    return okf.new_doc(
        type=_TYPES[kind],
        title=item["title"],
        description=f"{_TYPES[kind]} : {str(item.get('summary') or '')[:180]}",
        tags=list(dict.fromkeys([_FOLDER_TAG[kind], *candidate.tags, *[t.lower() for t in item.get("tickers") or []]])),
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A6",
        at=now,
        status="stable",
        stale_after=clock.iso(anchor + timedelta(days=_STALE[kind])),
        sources=[_source_entry(item)],
        data={
            "kind": kind,
            "item_id": item["id"],
            **{k: v for k, v in data.items() if k not in ("run_id",)},
            "url": item["url"],
            "published_at": item.get("published_at"),
            "observed_at": item.get("observed_at"),
            "retrieved_at": item.get("retrieved_at"),
            "run_id": data.get("run_id"),
            "staging_key": candidate.key,
        },
        body="\n".join(body),
    )


def brief_doc(candidate: ResearchCandidate, now: str, targets: dict[str, ResearchCandidate]) -> okf.OkfDoc:
    item = candidate.item
    data = item.get("data") or {}
    cited = [targets[c] for c in data.get("citations") or [] if c in targets]
    published = clock.parse_datetime(item.get("published_at")) or clock.utcnow()
    body = [
        f"# {item['title']}",
        "",
        f"- Question : {data.get('question')}",
        f"- Sujets : {', '.join(data.get('subjects') or [])}",
        f"- Rédigée le : {item.get('published_at')} par A0, à partir des constats des experts",
        *([f"- Point dans le temps : {data['as_of']}"] if data.get("as_of") else []),
        "",
        data.get("text") or "",
        "",
        "## Sources citées",
        "",
        *[
            f"- [{c.item['title']}]({c.target.removeprefix('general/')}) — {c.item.get('source')}, "
            f"publié le {str(c.item.get('published_at'))[:10]}"
            for c in cited
        ],
        "",
        "## Lacunes",
        "",
        *([f"- {g}" for g in data.get("gaps") or []] or ["- Aucune lacune signalée."]),
        "",
        "Synthèse automatique : contexte et explication, jamais un conseil personnalisé ni une recommandation.",
        "",
    ]
    return okf.new_doc(
        type="Research Brief",
        title=item["title"],
        description=f"Synthèse de recherche : {str(data.get('question') or '')[:180]}",
        tags=list(dict.fromkeys(["recherches", *[s.lower() for s in data.get("subjects") or []]])),
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A0",
        at=now,
        status="stable",
        stale_after=clock.iso(published + timedelta(days=BRIEF_STALE_DAYS)),
        sources=[_source_entry(c.item) for c in cited],
        data={
            "kind": "brief",
            "item_id": item["id"],
            "question": data.get("question"),
            "subjects": data.get("subjects"),
            "citations": [{"item_id": c.item["id"], "document": c.target} for c in cited],
            "as_of": data.get("as_of"),
            "gaps": data.get("gaps"),
            "run_id": data.get("run_id"),
            "staging_key": candidate.key,
        },
        body="\n".join(body),
    )
