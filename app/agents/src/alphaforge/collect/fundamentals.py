"""A6 : documents « Company Fundamentals » des fondamentaux EDGAR (``general/societes/<ticker>.md``).

Le bloc ``data`` est exactement celui que ``collect.edgar`` a construit; A6 le relit avec le lecteur du volet
finance (``okf_facts.parse_company_fundamentals``) avant d'écrire, n'écrit que si ``data`` change, et n'écrase
jamais un document qu'il n'a pas écrit lui-même (les seeds ATD et CSU, relevés à la main et poussés par Terraform).

Si l'élément porte un code SIC de ``edgar.SIC_ACTIVITY``, A6 écrit aussi un fait ESG ``sector_activity``
(``general/faits/data-sec-gov/<AAAA-MM-JJ>-<empreinte>.md``), relu par ``okf_facts.parse_esg``. L'empreinte vient
du titre et du code : tant que le code ne change pas, le fait existant reste et n'est pas réécrit.
"""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any, Protocol

from .. import clock, okf
from ..store import Store
from . import edgar, general, staging

FUNDAMENTALS_STALE_DAYS = 120  # un trimestre de plus que le dernier dépôt
SECTOR_STALE_DAYS = 365
SECTOR_PREFIX = "general/faits/data-sec-gov/"
ACTIVITY_FR = {
    "fossil_fuels": "combustibles fossiles",
    "tobacco": "tabac",
    "alcohol": "alcool",
    "weapons": "armement",
}
A6_AUTHOR = "agent:A6"
UNCHANGED = "inchangé"


class _Candidate(Protocol):
    key: str
    item: dict[str, Any]
    target: str


def _fmt(value: float) -> str:
    return f"{value:,.3f}".replace(",", " ").rstrip("0").rstrip(".") if isinstance(value, float) else str(value)


def _cells(entry: dict[str, Any]) -> str:
    numbers = {
        name: value
        for name, value in entry.items()
        if isinstance(value, int | float) and not isinstance(value, bool) and name != "months"
    }
    return ", ".join(f"{name} {_fmt(value)}" for name, value in numbers.items())


def _body(item: dict[str, Any], data: dict[str, Any], block: dict[str, Any]) -> str:
    rows = [
        f"| {p['period']} | {p['published_at']} | {p['source']} | {_cells(p)} |" for p in block.get("periods") or []
    ]
    rows += [
        f"| Bilan au {b['observed_at']} | {b['published_at']} | {b['source']} | {_cells(b)} |"
        for b in block.get("balance_sheets") or []
    ]
    skipped = data.get("skipped") or []
    lines = [
        f"# {item['title']}",
        "",
        f"Chiffres publiés par {block.get('issuer')} dans ses dépôts à la SEC, selon les normes "
        f"{block.get('accounting_standard')}, en millions de {block.get('reporting_currency')} (bénéfice par action "
        f"dans la devise, par action). Lus par le code dans EDGAR `companyfacts` (CIK {data.get('cik')}, taxonomie "
        f"`{data.get('taxonomy')}`), sans modèle. Ils servent à la simulation; rien ici ne constitue un conseil en "
        "placement.",
        "",
        "Chaque période et chaque bilan viennent du premier dépôt qui les publie, et prennent sa date de dépôt comme "
        "date de publication : un retraitement publié plus tard ne remplace pas la valeur d'origine.",
        "",
        "| Période | Publiée le | Dépôt | Valeurs |",
        "| --- | --- | --- | --- |",
        *rows,
        "",
        "## Limites",
        "",
        "- Seuls les formulaires d'origine (10-Q, 10-K, 20-F, 40-F, 6-K) sont lus, jamais leurs amendements.",
        "- Un concept déclaré dans une autre unité que celle des résultats est ignoré, jamais converti.",
        "- Les cumuls depuis le début de l'exercice (6 ou 9 mois) ne sont pas repris.",
        *([f"- Concepts ignorés : {len(skipped)} (unité non retenue)."] if skipped else []),
        "",
    ]
    return "\n".join(lines)


def fundamentals_doc(candidate: _Candidate, now: str) -> okf.OkfDoc:
    """Document « Company Fundamentals » : ``data`` est exactement le bloc construit par ``collect.edgar``."""
    item = candidate.item
    data = item.get("data") or {}
    block = data.get("fundamentals") or {}
    ticker = str(block.get("ticker") or "")
    latest = clock.parse_datetime(item["published_at"]) or clock.utcnow()
    return okf.new_doc(
        type="Company Fundamentals",
        title=item["title"],
        description=(
            f"Chiffres clés publiés par {block.get('issuer')} ({ticker}) dans ses dépôts à la SEC, en millions de "
            f"{block.get('reporting_currency')}, avec leurs dates d'observation et de publication."
        ),
        tags=["societes", "fondamentaux", "sec-edgar", edgar.doc_slug(ticker)],
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by=A6_AUTHOR,
        at=now,
        status="stable",
        stale_after=clock.iso(latest + timedelta(days=FUNDAMENTALS_STALE_DAYS)),
        sources=list(data.get("sources") or []),
        data=block,
        body=_body(item, data, block),
    )


def write_fundamentals(store: Store, candidate: _Candidate, now: str) -> str | None:
    """Écrit le document; renvoie ``None`` si écrit, sinon la raison (refusé, seed protégé, ``UNCHANGED``)."""
    from ..finance.strategy.okf_facts import OkfFactsError, parse_company_fundamentals

    doc = fundamentals_doc(candidate, now)
    try:
        parse_company_fundamentals(okf.render(doc), candidate.target, "a6")
    except OkfFactsError as exc:
        return f"fondamentaux refusés par le lecteur du volet finance : {exc}"
    current = store.get(candidate.target)
    if current is not None:
        try:
            existing = okf.parse(current.text)
        except okf.OkfError:
            return f"document existant illisible, non écrasé : {candidate.target}"
        if (existing.frontmatter.get("generated") or {}).get("by") != A6_AUTHOR:
            return f"seed protégé, jamais écrasé par A6 : {candidate.target}"
        if existing.frontmatter.get("data") == doc.frontmatter.get("data"):
            return UNCHANGED
    general.write_document(store, candidate.target, doc)
    return None


def sector_activity_doc(item: dict[str, Any], now: str) -> tuple[str, okf.OkfDoc] | None:
    """Fait ESG ``sector_activity`` tiré du code SIC de l'émetteur, ou ``None`` si le code n'est pas dans la table."""
    data = item.get("data") or {}
    sic = data.get("sic") or {}
    block = data.get("fundamentals") or {}
    activity = edgar.SIC_ACTIVITY.get(sic.get("code")) if isinstance(sic.get("code"), int) else None
    ticker = str(block.get("ticker") or "")
    if activity is None or not ticker:
        return None
    retrieved = str(item.get("retrieved_at") or now)
    day = retrieved[:10]
    digest = staging.short_hash(f"sic|{ticker}|{sic['code']}", 8)
    key = f"{SECTOR_PREFIX}{day}-{digest}.md"
    issuer = block.get("issuer") or ticker
    title = f"{issuer} ({ticker}) — activité : {ACTIVITY_FR[activity]} (code SIC {sic['code']})"
    licence = "Données publiques de la SEC (accès équitable : 10 requêtes par seconde, User-Agent déclaré)"
    doc = okf.new_doc(
        type="Fact",
        title=title,
        description=(
            f"Fact : la SEC classe {issuer} sous le code SIC {sic['code']} ({sic.get('description')}), une activité "
            f"de la catégorie « {ACTIVITY_FR[activity]} » du questionnaire."
        ),
        tags=["faits", "esg", activity, edgar.doc_slug(ticker)],
        owners=["alphaforge-a6"],
        sensitivity="public",
        generated_by=A6_AUTHOR,
        at=now,
        status="stable",
        stale_after=clock.iso((clock.parse_datetime(retrieved) or clock.utcnow()) + timedelta(days=SECTOR_STALE_DAYS)),
        sources=[
            {
                "id": f"sec-submissions-{edgar.doc_slug(ticker)}",
                "title": f"SEC EDGAR, submissions de {issuer} (code SIC)",
                "resource": sic.get("url"),
                "retrieved_at": retrieved,
                "licence": licence,
                "attribution": "Source : U.S. Securities and Exchange Commission, EDGAR",
            }
        ],
        data={
            "kind": "fact",
            "esg": {"kind": "sector_activity", "metric": activity, "period": day},
            "value": str(sic["code"]),
            "unit": "code SIC",
            "label": f"Code SIC {sic['code']} : {sic.get('description')}",
            "tickers": [ticker],
            "url": sic.get("url"),
            "published_at": retrieved,
            "published_at_basis": "retrieved_at_upper_bound",
            "observed_at": day,
            "retrieved_at": retrieved,
            "provenance": {
                "host": "data.sec.gov",
                "licence": licence,
                "attribution_text": "Source : U.S. Securities and Exchange Commission, EDGAR",
                "basis": "code SIC de submissions, table fixe edgar.SIC_ACTIVITY (sans modèle)",
            },
            "collected_by": "A5",
            "run_id": data.get("run_id"),
        },
        body="\n".join(
            [
                f"# {title}",
                "",
                f"- Source : SEC EDGAR — <{sic.get('url')}>",
                "- Source : U.S. Securities and Exchange Commission, EDGAR",
                f"- Code SIC : {sic['code']} ({sic.get('description')})",
                f"- Catégorie d'exclusion du questionnaire : {ACTIVITY_FR[activity]} (`{activity}`)",
                f"- Relevé le : {retrieved}",
                "",
                "## Limites",
                "",
                "- Le code SIC classe l'activité principale déclarée à la SEC, pas la part de revenus par activité.",
                "- La correspondance code → catégorie est une table fixe du code (`collect/edgar.py`), sans modèle.",
                "",
            ]
        ),
    )
    return key, doc


def write_sector_activity(store: Store, item: dict[str, Any], now: str) -> tuple[str | None, str | None]:
    """Écrit le fait ``sector_activity`` s'il y a lieu; renvoie (clé écrite, raison du refus ou ``UNCHANGED``)."""
    from ..finance.strategy.okf_facts import OkfFactsError, parse_esg

    built = sector_activity_doc(item, now)
    if built is None:
        return None, None
    key, doc = built
    suffix = key.rsplit("-", 1)[-1]
    if any(i.key.endswith(f"-{suffix}") for i in store.list(SECTOR_PREFIX, limit=2000)):
        return None, UNCHANGED
    try:
        parse_esg(okf.render(doc), key, "a6")
    except OkfFactsError as exc:
        return None, f"fait d'activité sectorielle refusé par le lecteur du volet finance : {exc}"
    general.write_document(store, key, doc)
    return key, None


def write_all(  # noqa: PLR0913 - les deux listes du marqueur sont complétées en place
    store: Store,
    candidates: list[_Candidate],
    now: str,
    written: list[str],
    rejected: list[dict[str, str]],
    *,
    deadline: float,
) -> list[str]:
    """Écrit les fondamentaux retenus; complète ``written`` et ``rejected``, renvoie les clés inchangées."""
    unchanged = []
    for candidate in candidates:
        if time.monotonic() > deadline:
            rejected.append({"key": candidate.key, "reason": "délai de curation dépassé"})
            continue
        reason = write_fundamentals(store, candidate, now)
        if reason is None:
            written.append(candidate.target)
        elif reason == UNCHANGED:
            unchanged.append(candidate.target)
        else:
            rejected.append({"key": candidate.key, "reason": reason})
        sector_key, sector_reason = write_sector_activity(store, candidate.item, now)
        if sector_key is not None:
            written.append(sector_key)
        elif sector_reason not in (None, UNCHANGED):
            rejected.append({"key": candidate.key, "reason": sector_reason})
    return unchanged
