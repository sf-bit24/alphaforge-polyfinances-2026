"""Contrôles d'A6 sur les éléments de la recherche par experts, et documents OKF des nouveaux types.

S'ajoutent aux contrôles de la version 1 (source, dates, doublons), avec une raison pour chaque rejet :
1. ancrage : chaque valeur (et chaque ligne d'une série) est relue au localisateur dans la réponse archivée;
2. licence : ``licence`` et ``attribution_text`` présents; robots.txt respecté, sauf exception assumée;
3. quarantaine : un élément d'un hôte proposé par un chercheur est retenu hors de la base générale;
4. nombres : le titre et le résumé n'empruntent leurs nombres qu'aux valeurs lues et à leurs dates;
5. point dans le temps : rien de publié après ``as_of``;
6. cotes : règles de résolution exigées, palier de qualité gardé;
7. synthèses : chaque citation renvoie à un élément retenu, chaque nombre à un élément cité;
8. preuves ESG : ``data.esg`` seulement sur un fait, catégorie de la liste fermée, hôte du paquet
   ``funds-sustainability``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    # Synthèse : citations dont l'élément double un document existant ou un autre élément de la collecte.
    refs: dict[str, ResearchCandidate] = field(default_factory=dict)


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


def source_slug(item: dict[str, Any]) -> str:
    """Dossier d'un fait ou d'un signal : l'hôte lu, fixé par le code, jamais un libellé écrit par un modèle."""
    host = str(((item.get("data") or {}).get("provenance") or {}).get("host") or item.get("source") or "")
    return staging.slugify(host.removeprefix("www."), 50)


def target(item: dict[str, Any]) -> str:
    """Clé d'un élément dans ``general/`` : arborescence fermée de CONTRACTS.md, section 5."""
    kind = item["kind"]
    data = item.get("data") or {}
    observed = str(item.get("observed_at") or item.get("published_at") or "")[:10]
    if kind in ("fact", "signal"):
        folder = "faits" if kind == "fact" else "signaux"
        return f"general/{folder}/{source_slug(item)}/{observed}-{_hash(item)}.md"
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


def _series_problem(tree: Any, spec: dict[str, Any] | None, observations: list[dict[str, Any]]) -> str | None:
    """Relit les lignes de la série dans l'archive; rend la raison du rejet, ou ``None``."""
    if not spec:
        return "série sans spécification de lignes"
    try:
        rows = documents.extract_rows(tree, spec["rows"], spec["date_field"], spec["value_field"])
    except documents.DocumentError as exc:
        return f"lignes de la série non relues : {exc}"
    archived = {(str(row["date"])[:10], row["value"]) for row in rows}
    from .researcher import parse_any_date

    archived |= {((parse_any_date(row["date"]) or "")[:10], row["value"]) for row in rows}
    for observation in observations:
        if (observation.get("date"), observation.get("value")) not in archived:
            return f"observation {observation.get('date')} absente de l'archive"
    return None


def check_grounding(store: Store, item: dict[str, Any], cache: dict[str, Any]) -> str | None:
    data = item.get("data") or {}
    provenance = data.get("provenance") or {}
    tree = _archive_tree(store, str(provenance.get("archive_key") or ""), cache)
    if tree is None:
        return "réponse archivée introuvable ou illisible : valeur non vérifiable"
    values = data.get("values") or {}
    for name, locator in (provenance.get("locators") or {}).items():
        try:
            value = documents.scalar(documents.resolve(tree, locator))
        except documents.DocumentError as exc:
            return f"localisateur {name} non résolu dans l'archive : {exc}"
        if value[:2000] != str(values.get(name)):
            return f"valeur {name} différente de l'archive"
    spec = provenance.get("series_spec")
    if item["kind"] == "series":
        return _series_problem(tree, spec, data.get("observations") or [])
    return None


# ----------------------------------------------------------------------------- validation
class _ItemRejectedError(Exception):
    """Un contrôle du code écarte l'élément; le message est la raison gardée dans les rejets."""


def _check_shape(item: Any) -> None:
    if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
        raise _ItemRejectedError("élément mal formé (id ou titre manquant)")
    if item.get("kind") not in staging.ITEM_KINDS + staging.RESEARCH_KINDS:
        raise _ItemRejectedError("type d'élément inconnu")


def _require_source(item: dict[str, Any]) -> None:
    url = item.get("url")
    if not item.get("source") or not isinstance(url, str) or not url.startswith("https://"):
        raise _ItemRejectedError("source manquante (nom et adresse https requis)")


def _publication_date(item: dict[str, Any]) -> datetime:
    published = clock.parse_datetime(item.get("published_at"))
    retrieved = clock.parse_datetime(item.get("retrieved_at"))
    if published is None or retrieved is None:
        raise _ItemRejectedError("date de publication ou de récupération manquante")
    if published > retrieved:
        raise _ItemRejectedError("publié après sa date de récupération")
    return published


def _check_observation(item: dict[str, Any], published: datetime) -> None:
    if item["kind"] not in ("series", "quote", "fact", "signal"):
        return
    observed = clock.parse_datetime(str(item.get("observed_at") or "")[:10])
    if observed is None:
        raise _ItemRejectedError("date d'observation manquante")
    if observed.date() > published.date():
        raise _ItemRejectedError("date d'observation postérieure à la publication")


def _check_licence(provenance: dict[str, Any]) -> None:
    if not provenance.get("licence") or not provenance.get("attribution_text"):
        raise _ItemRejectedError("licence ou texte d'attribution manquant")


def _check_robots(provenance: dict[str, Any], host: str) -> None:
    exception = host in HOSTS and HOSTS[host].robots_exception
    if provenance.get("robots_ok_at_fetch") is not True and not exception:
        raise _ItemRejectedError("robots.txt non respecté à la collecte")


def _check_as_of(provenance: dict[str, Any], published: datetime) -> None:
    as_of = clock.parse_datetime(provenance.get("as_of")) if provenance.get("as_of") else None
    if as_of is not None and published > as_of:
        raise _ItemRejectedError("publié après le point dans le temps demandé (as_of)")


def _check_numbers(item: dict[str, Any]) -> None:
    missing = documents.grounded(
        f"{item['title']} {item.get('summary') or ''}", items.allowed_numbers(item), items.allowed_dates(item)
    )
    if missing:
        raise _ItemRejectedError("nombres non fondés dans le titre ou le résumé : " + ", ".join(missing[:4]))


def _check_market_rules(item: dict[str, Any], host: str) -> None:
    market = (item.get("data") or {}).get("market") or {}
    if item["kind"] == "signal" and host in items.MARKET_HOSTS and not market.get("resolution_rules"):
        raise _ItemRejectedError("cote de marché sans règles de résolution")


def esg_problem(kind: str, data: dict[str, Any], host: str) -> str | None:
    """Raison de rejeter le bloc ``data.esg`` d'un élément (CONTRACTS.md, section 11.5), ou None."""
    if "esg" not in data:
        return None
    if kind != "fact":
        return "fait ESG : seul un élément fact peut porter data.esg"
    problems = okf.esg_problems(data["esg"])
    if problems:
        return "fait ESG refusé : " + "; ".join(problems)
    if host not in items.ESG_HOSTS:
        return f"fait ESG d'un hôte hors du paquet funds-sustainability : {host}"
    return None


def _check_esg(item: dict[str, Any], host: str) -> None:
    problem = esg_problem(item["kind"], item.get("data") or {}, host)
    if problem:
        raise _ItemRejectedError(problem)


@dataclass
class _ResearchReview:
    """Une passe de contrôles : éléments retenus, quarantaine, synthèses en attente et doublons déjà vus."""

    store: Store
    existing_keys: set[str]
    url_hashes: set[str]
    accepted: list[ResearchCandidate] = field(default_factory=list)
    quarantined: list[dict[str, Any]] = field(default_factory=list)
    briefs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    seen: dict[str, str] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=dict)
    # Élément vérifié mais doublon : une synthèse qui le cite renvoie au document déjà écrit (ou retenu).
    refs: dict[str, ResearchCandidate] = field(default_factory=dict)
    by_key: dict[str, ResearchCandidate] = field(default_factory=dict)

    def examine(self, key: str, item: Any) -> None:
        """Contrôles d'un élément, dans l'ordre; une synthèse attend que tous les éléments aient été vus."""
        _check_shape(item)
        if item["kind"] == "brief":
            self.briefs.append((key, item))
            return
        _require_source(item)
        published = _publication_date(item)
        _check_observation(item, published)
        provenance = (item.get("data") or {}).get("provenance") or {}
        _check_licence(provenance)
        host = str(provenance.get("host") or "")
        self._hold_if_quarantined(key, item, provenance, host)
        _check_robots(provenance, host)
        _check_as_of(provenance, published)
        problem = check_grounding(self.store, item, self.cache)
        if problem:
            raise _ItemRejectedError(problem)
        _check_numbers(item)
        _check_market_rules(item, host)
        _check_esg(item, host)
        self._accept(key, item)

    def _hold_if_quarantined(self, key: str, item: dict[str, Any], provenance: dict[str, Any], host: str) -> None:
        if provenance.get("host_status") == "quarantined":
            self.quarantined.append({"key": key, "id": item["id"], "host": host, "title": item["title"]})
            raise _ItemRejectedError("hôte en quarantaine : en attente d'approbation humaine de sa licence")

    def _dedupe_keys(self, key: str, item: dict[str, Any], path: str) -> list[str]:
        """Clés de doublon; un doublon est rejeté, et noté dans ``refs`` pour les synthèses qui le citent."""
        dedupe = [path, f"id:{item['id']}"]
        if item["kind"] == "news":
            url_hash = staging.short_hash(staging.normalize_url(item["url"]), 8)
            dedupe.append(f"url:{url_hash}")
            if url_hash in self.url_hashes:
                raise _ItemRejectedError("doublon d'un document existant (même adresse)")
        if path in self.existing_keys:
            self.refs[item["id"]] = ResearchCandidate(key=key, item=item, target=path)
            raise _ItemRejectedError(f"doublon d'un document existant : {path}")
        duplicate_of = next((self.seen[dedupe_key] for dedupe_key in dedupe if dedupe_key in self.seen), None)
        if duplicate_of:
            if duplicate_of in self.by_key:
                self.refs[item["id"]] = self.by_key[duplicate_of]
            raise _ItemRejectedError(f"doublon dans la collecte : {duplicate_of}")
        return dedupe

    def _accept(self, key: str, item: dict[str, Any]) -> None:
        path = target(item)
        dedupe = self._dedupe_keys(key, item, path)
        for dedupe_key in dedupe:
            self.seen[dedupe_key] = key
        tags = (item.get("data") or {}).get("tags") or []
        candidate = ResearchCandidate(key=key, item=item, target=path, dedupe=dedupe, tags=tags)
        self.accepted.append(candidate)
        self.by_key[key] = candidate

    def examine_brief(self, key: str, item: dict[str, Any], by_id: dict[str, ResearchCandidate]) -> None:
        """Chaque citation renvoie à un élément retenu (ou déjà écrit), chaque nombre à un élément cité."""
        data = item.get("data") or {}
        citations = [citation for citation in data.get("citations") or [] if isinstance(citation, str)]
        resolved = {citation: by_id.get(citation) or self.refs.get(citation) for citation in citations}
        missing_ids = [citation for citation, found in resolved.items() if found is None]
        if not citations or missing_ids:
            raise _ItemRejectedError("synthèse : citations absentes ou non retenues " + ", ".join(missing_ids[:4]))
        values = [number for citation in citations for number in items.allowed_numbers(resolved[citation].item)]
        dates = [day for citation in citations for day in items.allowed_dates(resolved[citation].item)]
        missing = documents.grounded(f"{item['title']} {data.get('text') or ''}", values, dates)
        if missing:
            raise _ItemRejectedError("synthèse : nombres non fondés " + ", ".join(missing[:4]))
        path = target(item)
        if path in self.existing_keys:
            raise _ItemRejectedError(f"doublon d'un document existant : {path}")
        brief_refs = {citation: found for citation, found in resolved.items() if citation not in by_id}
        self.accepted.append(ResearchCandidate(key=key, item=item, target=path, dedupe=[path], refs=brief_refs))


def validate_research(
    staged: list[tuple[str, Any]],
    existing_keys: set[str],
    store: Store,
    *,
    url_hashes: set[str] | None = None,
) -> tuple[list[ResearchCandidate], list[dict[str, str]], list[dict[str, Any]]]:
    review = _ResearchReview(store=store, existing_keys=existing_keys, url_hashes=url_hashes or set())
    rejected: list[dict[str, str]] = []
    for key, item in staged:
        try:
            review.examine(key, item)
        except _ItemRejectedError as rejection:
            rejected.append({"key": key, "reason": str(rejection)})
    by_id = {candidate.item["id"]: candidate for candidate in review.accepted}
    for key, item in review.briefs:
        try:
            review.examine_brief(key, item, by_id)
        except _ItemRejectedError as rejection:
            rejected.append({"key": key, "reason": str(rejection)})
    return review.accepted, rejected, review.quarantined


# ----------------------------------------------------------------------------- documents
_TYPES = {"fact": "Fact", "signal": "Market Signal", "filing": "Regulatory Filing"}
_FOLDER_TAG = {"fact": "faits", "signal": "signaux", "filing": "depots"}
_STALE = {"fact": FACT_STALE_DAYS, "signal": SIGNAL_STALE_DAYS, "filing": FILING_STALE_DAYS}


def _source_entry(item: dict[str, Any]) -> dict[str, Any]:
    provenance = (item.get("data") or {}).get("provenance") or {}
    return {
        "id": item["id"],
        "title": item["title"],
        "resource": item.get("url"),
        "published_at": item.get("published_at"),
        "observed_at": item.get("observed_at"),
        "retrieved_at": item.get("retrieved_at"),
        "licence": provenance.get("licence"),
        "attribution": provenance.get("attribution_text"),
    }


def _provenance_lines(item: dict[str, Any], data: dict[str, Any], provenance: dict[str, Any]) -> list[str]:
    """Source, attribution, licence et dates du constat, en tête de son document."""
    return [
        f"- Source : {item['source']} — <{item['url']}>",
        f"- {provenance.get('attribution_text')}",
        f"- Licence : {provenance.get('licence')}"
        + (f" — <{provenance['licence_url']}>" if provenance.get("licence_url") else ""),
        f"- Date d'observation : {item.get('observed_at') or '—'}",
        f"- Date de publication : {item.get('published_at')}"
        + (
            " (borne supérieure : date de récupération)"
            if provenance.get("publication_basis") == "retrieved_at_upper_bound"
            else ""
        ),
        f"- Récupérée le : {item.get('retrieved_at')}",
        f"- Recherche : {data.get('collected_by')}",
    ]


def _market_lines(market: dict[str, Any]) -> list[str]:
    if not market:
        return []
    return [
        "## Marché",
        "",
        f"- Palier de qualité : {market.get('quality_tier')} "
        "(élevé : volume d'au moins 1 M et fourchette d'au plus 2 cents)",
        f"- Règles de résolution, telles quelles : {str(market.get('resolution_rules') or '—')[:1500]}",
        "",
    ]


def _esg_lines(esg: dict[str, Any]) -> list[str]:
    if not esg:
        return []
    return [
        "## Preuve ESG",
        "",
        f"- Catégorie : {esg.get('kind')} — mesure : {esg.get('metric')} — période : {esg.get('period')}",
        "- Fait sourcé et daté : il appuie une préférence de l'investisseur, ce n'est pas une note ESG.",
        "",
    ]


def _limit_lines(kind: str, provenance: dict[str, Any]) -> list[str]:
    return [
        "## Limites",
        "",
        "- Contexte, pas un signal d'achat ou de vente." if kind == "signal" else "- Fait sourcé, à lire avec sa date.",
        "- Une valeur ne sert dans une simulation qu'à partir de sa date de publication.",
        *([f"- {provenance['licence_note']}"] if provenance.get("licence_note") else []),
        "",
    ]


def _research_body(item: dict[str, Any], kind: str, data: dict[str, Any]) -> str:
    provenance = data.get("provenance") or {}
    values = data.get("values") or {}
    lines = [
        f"# {item['title']}",
        "",
        *_provenance_lines(item, data, provenance),
        "",
        "## Constat",
        "",
        item.get("summary") or "",
        "",
        "## Valeurs lues dans la source",
        "",
        "| Champ | Valeur |",
        "| --- | --- |",
        *[f"| {name} | {str(value)[:200].replace('|', '/')} |" for name, value in values.items()],
        "",
        *_market_lines(data.get("market") or {}),
        *_esg_lines(data.get("esg") or {}),
        *_limit_lines(kind, provenance),
    ]
    return "\n".join(lines)


def _research_data(candidate: ResearchCandidate, kind: str, data: dict[str, Any]) -> dict[str, Any]:
    item = candidate.item
    return {
        "kind": kind,
        "item_id": item["id"],
        **{name: value for name, value in data.items() if name not in ("run_id",)},
        "url": item["url"],
        "tickers": list(item.get("tickers") or []),  # lu par okf_facts.parse_filing (sujet « filings »)
        "published_at": item.get("published_at"),
        "observed_at": item.get("observed_at"),
        "retrieved_at": item.get("retrieved_at"),
        "run_id": data.get("run_id"),
        "staging_key": candidate.key,
    }


def research_doc(candidate: ResearchCandidate, now: str) -> okf.OkfDoc:
    item = candidate.item
    kind = item["kind"]
    data = item.get("data") or {}
    anchor = clock.parse_datetime(str(item.get("observed_at") or item.get("published_at"))[:10]) or clock.utcnow()
    body = _research_body(item, kind, data)
    return okf.new_doc(
        type=_TYPES[kind],
        title=item["title"],
        description=f"{_TYPES[kind]} : {str(item.get('summary') or '')[:180]}",
        tags=list(
            dict.fromkeys(
                [_FOLDER_TAG[kind], *candidate.tags, *[ticker.lower() for ticker in item.get("tickers") or []]]
            )
        ),
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A6",
        at=now,
        status="stable",
        stale_after=clock.iso(anchor + timedelta(days=_STALE[kind])),
        sources=[_source_entry(item)],
        data=_research_data(candidate, kind, data),
        body=body,
    )


def _cited_source_line(cited: ResearchCandidate) -> str:
    return (
        f"- [{cited.item['title']}]({cited.target.removeprefix('general/')}) — {cited.item.get('source')}, "
        f"publié le {str(cited.item.get('published_at'))[:10]}"
    )


def _brief_body(item: dict[str, Any], data: dict[str, Any], cited: list[ResearchCandidate]) -> str:
    lines = [
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
        *[_cited_source_line(candidate) for candidate in cited],
        "",
        "## Lacunes",
        "",
        *([f"- {gap}" for gap in data.get("gaps") or []] or ["- Aucune lacune signalée."]),
        "",
        "Synthèse automatique : contexte et explication, jamais un conseil personnalisé ni une recommandation.",
        "",
    ]
    return "\n".join(lines)


def brief_doc(candidate: ResearchCandidate, now: str, targets: dict[str, ResearchCandidate]) -> okf.OkfDoc:
    item = candidate.item
    data = item.get("data") or {}
    cited = [targets[citation] for citation in data.get("citations") or [] if citation in targets]
    published = clock.parse_datetime(item.get("published_at")) or clock.utcnow()
    body = _brief_body(item, data, cited)
    return okf.new_doc(
        type="Research Brief",
        title=item["title"],
        description=f"Synthèse de recherche : {str(data.get('question') or '')[:180]}",
        tags=list(dict.fromkeys(["recherches", *[subject.lower() for subject in data.get("subjects") or []]])),
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by="agent:A0",
        at=now,
        status="stable",
        stale_after=clock.iso(published + timedelta(days=BRIEF_STALE_DAYS)),
        sources=[_source_entry(cited_candidate.item) for cited_candidate in cited],
        data={
            "kind": "brief",
            "item_id": item["id"],
            "question": data.get("question"),
            "subjects": data.get("subjects"),
            "citations": [
                {"item_id": cited_candidate.item["id"], "document": cited_candidate.target} for cited_candidate in cited
            ],
            "as_of": data.get("as_of"),
            "gaps": data.get("gaps"),
            "run_id": data.get("run_id"),
            "staging_key": candidate.key,
        },
        body=body,
    )
