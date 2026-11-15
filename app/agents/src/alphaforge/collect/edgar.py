"""Fondamentaux publiés à la SEC (EDGAR ``companyfacts``) : code déterministe, sans modèle.

A5 appelle ``stage_fundamentals`` à chaque collecte : pour chaque action de l'univers présente dans EDGAR, le code
lit la correspondance symbole → CIK (``company_tickers.json``) puis ``companyfacts`` (jamais l'API ``frames``), et
met en attente un élément ``fundamentals`` dont le bloc ``data.fundamentals`` suit exactement le format
« Company Fundamentals » de ``finance.strategy.okf_facts``. A6 le relit avec ce même lecteur avant d'écrire
``general/societes/<ticker>.md``, et n'écrase jamais un seed (ATD et CSU, relevés à la main).

Règles :
- point dans le temps : une période (ou un bilan) vient d'un seul dépôt, le PREMIER qui la publie (date ``filed``).
  Ses comparatifs de l'année précédente (``prior_year``) viennent du même dépôt. Les retraitements publiés plus tard
  ne remplacent pas la valeur d'origine : aucune valeur n'est connue avant sa date de publication;
- formulaires d'origine seulement (10-Q, 10-K, 20-F, 40-F, 6-K), jamais les amendements ``/A``;
- taxonomie ``ifrs-full`` si l'émetteur y déclare ses chiffres (RY, TD, CNQ, MFC), ``us-gaap`` sinon;
- un concept dans une unité inconnue (autre devise que celle des résultats, ``shares``, ``pure``…) est ignoré et
  noté dans ``skipped`` : on ne convertit ni ne devine aucune unité;
- montants en millions de la devise de publication; BPA dilué dans la devise par action;
- pièges : CN est déposée sous son symbole NYSE ``CNI``; l'historique d'ExxonMobil reste sous son ancien CIK
  (changé le 2026-07-01), lu en plus du nouveau; ATD et CSU sont absentes d'EDGAR.
- 10 requêtes par seconde au plus et User-Agent avec courriel de contact (``collect.http``).

Activité sectorielle : le code lit aussi le code SIC de l'émetteur (``submissions``) et, s'il figure dans
``SIC_ACTIVITY`` (table fixe, sans modèle), joint à l'élément une activité exclue possible (``fossil_fuels``,
``tobacco``, ``alcohol``, ``weapons``). A6 en tire un fait ESG ``sector_activity`` (CONTRACTS.md, section 11.5).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .. import clock
from . import http, staging

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
# Codes SIC (classification de la SEC) → activité du questionnaire (``okf.ESG_ACTIVITIES``). Table fixe et courte :
# un code absent ne donne aucun fait. 4911 (électricité) n'y est pas : le code ne dit pas si elle est fossile.
SIC_ACTIVITY = {
    1221: "fossil_fuels",  # charbon bitumineux et lignite
    1222: "fossil_fuels",
    1231: "fossil_fuels",  # anthracite
    1311: "fossil_fuels",  # pétrole brut et gaz naturel
    1321: "fossil_fuels",  # liquides de gaz naturel
    1381: "fossil_fuels",  # forage de puits de pétrole et de gaz
    1382: "fossil_fuels",  # services d'exploration pétrolière et gazière
    1389: "fossil_fuels",  # services aux champs de pétrole et de gaz
    2911: "fossil_fuels",  # raffinage du pétrole
    2990: "fossil_fuels",  # produits divers du pétrole et du charbon
    4610: "fossil_fuels",  # pipelines (hors gaz naturel)
    4612: "fossil_fuels",  # pipelines de pétrole brut
    4613: "fossil_fuels",  # pipelines de produits pétroliers raffinés
    4922: "fossil_fuels",  # transport de gaz naturel
    4923: "fossil_fuels",  # transport et distribution de gaz naturel
    4924: "fossil_fuels",  # distribution de gaz naturel
    5171: "fossil_fuels",  # dépôts pétroliers en vrac
    5172: "fossil_fuels",  # commerce de gros de produits pétroliers
    2111: "tobacco",  # cigarettes
    2121: "tobacco",
    2131: "tobacco",
    2141: "tobacco",
    2082: "alcohol",  # bière
    2084: "alcohol",  # vins et spiritueux
    2085: "alcohol",  # boissons alcoolisées distillées
    3482: "weapons",  # munitions de petit calibre
    3483: "weapons",  # munitions
    3484: "weapons",  # armes légères
    3489: "weapons",  # armement, n.c.a.
}
HOSTS = ("www.sec.gov", "data.sec.gov")
MAX_BYTES = 60_000_000  # companyfacts d'un grand émetteur : plusieurs dizaines de Mo (décompressé)
TIMEOUT = 30.0
HTTP_FORBIDDEN = 403

SEC_SYMBOL = {"CNR.TO": "CNI"}  # CN est déposée sous son symbole NYSE
LEGACY_CIKS = {"XOM": (34088,)}  # ExxonMobil : historique sous l'ancien CIK, changé le 2026-07-01
FORMS = frozenset({"10-Q", "10-K", "20-F", "40-F", "6-K"})
CURRENCIES = ("USD", "CAD", "EUR")  # devises admises par ``okf_facts`` (Currency)
QUARTERS_KEPT = 4
YEARS_KEPT = 2
BALANCES_KEPT = 4

# Champ du registre de ``okf_facts`` → concepts, par ordre de préférence.
PERIOD_CONCEPTS: dict[str, dict[str, tuple[str, ...]]] = {
    "us-gaap": {
        "revenue": (
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "RevenuesNetOfInterestExpense",
        ),
        "gross_profit": ("GrossProfit",),
        "operating_income": ("OperatingIncomeLoss",),
        "net_income": ("ProfitLoss",),
        "net_income_attributable": ("NetIncomeLoss",),
        "diluted_eps": ("EarningsPerShareDiluted",),
        "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
        "capital_expenditures": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    },
    "ifrs-full": {
        "revenue": ("Revenue", "RevenueFromContractsWithCustomers"),
        "gross_profit": ("GrossProfit",),
        "operating_income": ("ProfitLossFromOperatingActivities",),
        "net_income": ("ProfitLoss",),
        "net_income_attributable": ("ProfitLossAttributableToOwnersOfParent",),
        "diluted_eps": ("DilutedEarningsLossPerShare",),
        "operating_cash_flow": ("CashFlowsFromUsedInOperatingActivities",),
        "capital_expenditures": ("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",),
    },
}
BALANCE_CONCEPTS: dict[str, dict[str, tuple[str, ...]]] = {
    "us-gaap": {
        "total_assets": ("Assets",),
        "cash": ("CashAndCashEquivalentsAtCarryingValue",),
        "long_term_debt": ("LongTermDebtNoncurrent", "LongTermDebt"),
        "equity_attributable": ("StockholdersEquity",),
        "total_liabilities": ("Liabilities",),
        "total_equity": ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",),
        "non_controlling_interests": ("MinorityInterest",),
    },
    "ifrs-full": {
        "total_assets": ("Assets",),
        "cash": ("CashAndCashEquivalents",),
        "equity_attributable": ("EquityAttributableToOwnersOfParent",),
        "total_liabilities": ("Liabilities",),
        "total_equity": ("Equity",),
        "non_controlling_interests": ("NoncontrollingInterests",),
    },
}
PER_SHARE = frozenset({"diluted_eps"})
STANDARD = {"us-gaap": "US GAAP", "ifrs-full": "IFRS"}


class EdgarError(ValueError):
    pass


def sec_symbol(ticker: str) -> str:
    """Symbole sous lequel la SEC connaît l'émetteur : ``CNR.TO`` → ``CNI``, ``RY.TO`` → ``RY``."""
    t = ticker.strip().upper()
    return SEC_SYMBOL.get(t, t.removesuffix(".TO"))


def doc_slug(ticker: str) -> str:
    """Nom du document sous ``general/societes/`` : ``RY.TO`` → ``ry``, comme les seeds ``atd.md`` et ``csu.md``."""
    return staging.slugify(ticker.strip().upper().removesuffix(".TO"), 20)


def target_key(ticker: str) -> str:
    return f"general/societes/{doc_slug(ticker)}.md"


def parse_ticker_map(payload: Any) -> dict[str, tuple[int, str]]:
    """``company_tickers.json`` → symbole SEC → (CIK, raison sociale)."""
    rows = payload.values() if isinstance(payload, dict) else payload if isinstance(payload, list) else []
    out: dict[str, tuple[int, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol, cik, title = row.get("ticker"), row.get("cik_str"), row.get("title")
        if isinstance(symbol, str) and isinstance(cik, int) and not isinstance(cik, bool):
            out.setdefault(symbol.upper(), (cik, str(title or symbol)))
    return out


# ----------------------------------------------------------------------------------------- construction
@dataclass(frozen=True)
class _Rec:
    field: str
    concept: str
    start: date | None
    end: date
    value: float
    unit: str
    accn: str
    form: str
    filed: date


@dataclass
class Built:
    ticker: str
    cik: int
    taxonomy: str
    fundamentals: dict[str, Any]
    sources: list[dict[str, Any]]
    skipped: list[str] = field(default_factory=list)
    sic: int | None = None
    sic_description: str | None = None

    @property
    def latest_published(self) -> str:
        dates = [p["published_at"] for p in self.fundamentals["periods"]]
        dates += [b["published_at"] for b in self.fundamentals["balance_sheets"]]
        return max(dates)

    @property
    def latest_observed(self) -> str:
        dates = [p["observed_at"] for p in self.fundamentals["periods"]]
        dates += [b["observed_at"] for b in self.fundamentals["balance_sheets"]]
        return max(dates)


def _iso(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def merge_facts(payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fusionne les ``facts`` de plusieurs CIK d'un même émetteur (ancien et nouveau CIK d'ExxonMobil)."""
    merged: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for taxonomy, concepts in (payload.get("facts") or {}).items():
            if not isinstance(concepts, dict):
                continue
            target = merged.setdefault(taxonomy, {})
            for concept, body in concepts.items():
                units = (body or {}).get("units") if isinstance(body, dict) else None
                if not isinstance(units, dict):
                    continue
                slot = target.setdefault(concept, {"units": {}})
                for unit, rows in units.items():
                    if isinstance(rows, list):
                        slot["units"].setdefault(unit, []).extend(rows)
    return merged


def choose_taxonomy(facts: dict[str, dict[str, Any]]) -> str:
    ifrs = facts.get("ifrs-full") or {}
    mapped = {c for concepts in PERIOD_CONCEPTS["ifrs-full"].values() for c in concepts}
    return "ifrs-full" if any(c in ifrs for c in mapped) else "us-gaap"


def _reporting_currency(concepts: dict[str, Any], taxonomy: str) -> str | None:
    for name in (*PERIOD_CONCEPTS[taxonomy]["revenue"], "Assets"):
        units = (concepts.get(name) or {}).get("units") or {}
        for currency in CURRENCIES:
            if currency in units:
                return currency
    return None


def _row_record(field_name: str, concept: str, unit: str, row: Any) -> _Rec | None:
    """Une ligne de ``companyfacts`` d'un formulaire d'origine, bien datée et chiffrée; ``None`` sinon."""
    if not isinstance(row, dict):
        return None
    form = str(row.get("form") or "")
    end, filed, value = _iso(row.get("end")), _iso(row.get("filed")), row.get("val")
    if form not in FORMS or end is None or filed is None or not row.get("accn"):
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return _Rec(
        field=field_name,
        concept=concept,
        start=_iso(row.get("start")),
        end=end,
        value=float(value),
        unit=unit,
        accn=str(row["accn"]),
        form=form,
        filed=filed,
    )


def _records(concepts: dict[str, Any], taxonomy: str, currency: str, skipped: list[str]) -> list[_Rec]:
    out: list[_Rec] = []
    mapping = {**PERIOD_CONCEPTS[taxonomy], **BALANCE_CONCEPTS[taxonomy]}
    for field_name, names in mapping.items():
        expected = f"{currency}/shares" if field_name in PER_SHARE else currency
        for concept in names:
            units = (concepts.get(concept) or {}).get("units") or {}
            skipped += [
                f"{taxonomy}:{concept} en {unit} (unité non retenue, on ne convertit pas)"
                for unit in units
                if unit != expected
            ]
            rows = (_row_record(field_name, concept, expected, row) for row in units.get(expected) or [])
            out += [r for r in rows if r is not None]
    return out


def _kind(start: date, end: date) -> tuple[str, int] | None:
    days = (end - start).days
    if 80 <= days <= 100:
        return "quarter", days
    if 350 <= days <= 380:
        return "fiscal_year", days
    return None  # cumul depuis le début de l'exercice (6 ou 9 mois) : non retenu


def _value(field_name: str, value: float) -> float:
    return round(value, 4) if field_name in PER_SHARE else round(value / 1_000_000, 3)


def _pick(records: list[_Rec]) -> dict[str, float]:
    """Une valeur par champ, du concept préféré (ordre de ``*_CONCEPTS``)."""
    out: dict[str, tuple[int, float]] = {}
    for r in records:
        rank = _concept_rank(r)
        if r.field not in out or rank < out[r.field][0]:
            out[r.field] = (rank, _value(r.field, r.value))
    return {name: value for name, (_, value) in sorted(out.items())}


def _concept_rank(r: _Rec) -> int:
    for table in (PERIOD_CONCEPTS, BALANCE_CONCEPTS):
        for taxonomy in table.values():
            names = taxonomy.get(r.field)
            if names and r.concept in names:
                return names.index(r.concept)
    return 99


def _source_id(accn: str) -> str:
    return f"sec-{accn}"


@dataclass(frozen=True)
class Issuer:
    """Émetteur tel que l'univers et la SEC le connaissent."""

    ticker: str
    cik: int
    name: str
    exchange: str | None = None


Span = tuple[date, date]


@dataclass
class _Tables:
    """Lignes retenues, rangées par période (début, fin) et par date de bilan; dépôts utilisés."""

    taxonomy: str
    durations: dict[Span, list[_Rec]] = field(default_factory=dict)
    instants: dict[date, list[_Rec]] = field(default_factory=dict)
    used: dict[str, tuple[date, str]] = field(default_factory=dict)

    @classmethod
    def of(cls, records: list[_Rec], taxonomy: str) -> _Tables:
        tables = cls(taxonomy)
        for r in records:
            if r.field in BALANCE_CONCEPTS[taxonomy]:
                if r.start is None:
                    tables.instants.setdefault(r.end, []).append(r)
            elif r.start is not None and _kind(r.start, r.end) is not None:
                tables.durations.setdefault((r.start, r.end), []).append(r)
        return tables

    def origin(self, recs: list[_Rec]) -> tuple[_Rec, dict[str, float]]:
        """Premier dépôt qui publie ces lignes, et les valeurs qu'il donne (une par champ)."""
        first = min(recs, key=lambda r: (r.filed, r.accn))
        return first, _pick([r for r in recs if r.accn == first.accn])

    def selected_spans(self) -> list[Span]:
        by_kind: dict[str, list[Span]] = {"quarter": [], "fiscal_year": []}
        for start, end in self.durations:
            kind = _kind(start, end)
            if kind is not None:
                by_kind[kind[0]].append((start, end))
        quarters = sorted(by_kind["quarter"], key=lambda span: span[1])[-QUARTERS_KEPT:]
        return quarters + sorted(by_kind["fiscal_year"], key=lambda span: span[1])[-YEARS_KEPT:]

    def prior_year(self, kind: str, end: date, accn: str) -> dict[str, Any] | None:
        """Comparatif de la même période un an plus tôt, publié dans le même dépôt."""
        target = end - timedelta(days=365)
        prior = [
            r
            for (start, prior_end), recs in self.durations.items()
            if (_kind(start, prior_end) or ("",))[0] == kind and abs((prior_end - target).days) <= 7
            for r in recs
            if r.accn == accn and r.field in PERIOD_CONCEPTS[self.taxonomy]
        ]
        values = _pick(prior)
        return {"observed_at": max(r.end for r in prior).isoformat(), **values} if values else None

    def period(self, span: Span) -> dict[str, Any] | None:
        start, end = span
        first, values = self.origin(self.durations[span])
        kind, days = _kind(start, end) or ("", 0)
        if not values or end > first.filed:
            return None
        entry: dict[str, Any] = {
            "period": f"{'Trimestre' if kind == 'quarter' else 'Exercice'} clos le {end.isoformat()}",
            "kind": kind,
            "months": max(1, round(days / 30.44)),
            "observed_at": end.isoformat(),
            "published_at": first.filed.isoformat(),
            "source": _source_id(first.accn),
            **values,
        }
        prior = self.prior_year(kind, end, first.accn)
        if prior:
            entry["prior_year"] = prior
        self.used[first.accn] = (first.filed, first.form)
        return entry

    def balance_sheet(self, end: date) -> dict[str, Any] | None:
        first, values = self.origin(self.instants[end])
        if not values or end > first.filed:
            return None
        self.used[first.accn] = (first.filed, first.form)
        return {
            "observed_at": end.isoformat(),
            "published_at": first.filed.isoformat(),
            "source": _source_id(first.accn),
            **values,
        }

    def sources(self, issuer: Issuer, retrieved_at: str) -> list[dict[str, Any]]:
        ordered = sorted(self.used.items(), key=lambda kv: (kv[1][0], kv[0]), reverse=True)
        return [
            {
                "id": _source_id(accn),
                "title": f"SEC EDGAR, formulaire {form} de {issuer.name} déposé le {filed.isoformat()} (numéro {accn})",
                "resource": f"https://www.sec.gov/Archives/edgar/data/{issuer.cik}/{accn.replace('-', '')}/",
                "retrieved_at": retrieved_at,
            }
            for accn, (filed, form) in ordered
        ]


def build_fundamentals(issuer: Issuer, payloads: list[dict[str, Any]], retrieved_at: str) -> Built:
    """Bloc ``data`` « Company Fundamentals » et ``sources`` à partir des réponses ``companyfacts``."""
    facts = merge_facts(payloads)
    taxonomy = choose_taxonomy(facts)
    concepts = facts.get(taxonomy) or {}
    currency = _reporting_currency(concepts, taxonomy)
    if currency is None:
        raise EdgarError(f"{issuer.ticker} : aucune devise de publication reconnue ({', '.join(CURRENCIES)})")
    skipped: list[str] = []
    tables = _Tables.of(_records(concepts, taxonomy, currency, skipped), taxonomy)
    periods = [p for p in (tables.period(span) for span in tables.selected_spans()) if p]
    sheets = [b for b in (tables.balance_sheet(end) for end in sorted(tables.instants)[-BALANCES_KEPT:]) if b]
    if not periods and not sheets:
        raise EdgarError(f"{issuer.ticker} : aucune période ni aucun bilan exploitable dans companyfacts")
    ticker = issuer.ticker.strip().upper()
    data: dict[str, Any] = {
        "ticker": ticker,
        "issuer": issuer.name,
        **({"exchange": issuer.exchange} if issuer.exchange else {}),
        "reporting_currency": currency,
        "unit": "millions",
        "accounting_standard": STANDARD[taxonomy],
        "retrieved_from": f"SEC EDGAR companyfacts, CIK {issuer.cik:010d}, taxonomie {taxonomy}",
        "periods": sorted(periods, key=lambda p: (p["observed_at"], p["kind"]), reverse=True),
        "balance_sheets": sorted(sheets, key=lambda b: b["observed_at"], reverse=True),
    }
    return Built(
        ticker=ticker,
        cik=issuer.cik,
        taxonomy=taxonomy,
        fundamentals=data,
        sources=tables.sources(issuer, retrieved_at),
        skipped=sorted(set(skipped)),
    )


def fundamentals_item(built: Built, *, run_id: str, retrieved_at: str) -> dict[str, Any]:
    """Élément ``fundamentals`` mis en attente par A5 (titre et résumé écrits par le code)."""
    data = built.fundamentals
    summary = (
        f"Chiffres publiés par {data['issuer']} dans ses dépôts à la SEC ({data['accounting_standard']}, millions de "
        f"{data['reporting_currency']}) : {len(data['periods'])} période(s) et {len(data['balance_sheets'])} bilan(s), "
        "chacun daté par le dépôt qui l'a publié en premier."
    )
    return staging.new_item(
        item_id=f"fundamentals-{doc_slug(built.ticker)}",
        kind="fundamentals",
        title=f"{data['issuer']} ({built.ticker}) — chiffres financiers publiés (SEC EDGAR)",
        url=COMPANYFACTS_URL.format(cik=built.cik),
        source="SEC EDGAR",
        published_at=f"{built.latest_published}T00:00:00Z",
        observed_at=built.latest_observed,
        retrieved_at=retrieved_at,
        language="fr",
        tickers=[built.ticker],
        summary=summary,
        data={
            "fundamentals": data,
            "sources": built.sources,
            "cik": f"{built.cik:010d}",
            "taxonomy": built.taxonomy,
            "skipped": built.skipped[:40],
            **(
                {
                    "sic": {
                        "code": built.sic,
                        "description": built.sic_description,
                        "url": SUBMISSIONS_URL.format(cik=built.cik),
                    }
                }
                if built.sic is not None
                else {}
            ),
            "collected_by": "A5",
            "run_id": run_id,
        },
    )


# ----------------------------------------------------------------------------------------- réseau
Getter = Any  # Callable[[str], bytes] : injecté par les tests (aucun appel réseau)


def _default_get(url: str) -> bytes:
    return http.http_get(url, timeout=TIMEOUT, max_bytes=MAX_BYTES, allowed_hosts=HOSTS).body


class _SecRefusedError(Exception):
    """La SEC refuse la lecture (403, courriel de contact absent) : inutile d'insister pour les titres suivants."""


def parse_sic(payload: Any) -> tuple[int, str] | None:
    """``submissions`` → (code SIC, libellé), ou ``None`` si absent ou illisible."""
    if not isinstance(payload, dict):
        return None
    try:
        code = int(str(payload.get("sic") or "").strip())
    except ValueError:
        return None
    return code, str(payload.get("sicDescription") or "").strip()[:120]


def _fetch_one(issuer: Issuer, get: Getter, retrieved_at: str) -> Built:
    symbol = sec_symbol(issuer.ticker)
    ciks = (issuer.cik, *[c for c in LEGACY_CIKS.get(symbol, ()) if c != issuer.cik])
    try:
        payloads = [json.loads(get(COMPANYFACTS_URL.format(cik=c))) for c in ciks]
    except http.FetchError as exc:
        if exc.status == HTTP_FORBIDDEN:
            raise _SecRefusedError(f"{issuer.ticker} : {exc}") from exc
        raise EdgarError(f"{issuer.ticker} : {exc}") from exc
    built = build_fundamentals(issuer, payloads, retrieved_at)
    try:
        sic = parse_sic(json.loads(get(SUBMISSIONS_URL.format(cik=issuer.cik))))
    except (http.FetchError, ValueError):
        sic = None  # le code SIC est un complément : son absence ne bloque pas les fondamentaux
    if sic is not None:
        built.sic, built.sic_description = sic
    return built


def stage_fundamentals(
    *,
    run_id: str,
    tickers: dict[str, str | None],
    stage: Any,
    deadline: float,
    get: Getter | None = None,
) -> dict[str, Any]:
    """Lit EDGAR pour ``tickers`` (symbole → bourse) et appelle ``stage(item)`` pour chacun; renvoie un bilan.

    Les titres absents d'EDGAR (ATD.TO, CSU.TO) sont notés, pas en erreur. Une erreur de réseau est notée pour son
    titre; un 403 de la SEC (courriel de contact absent) arrête la lecture proprement."""
    get = get or _default_get
    report: dict[str, Any] = {"staged": [], "absent": [], "errors": []}
    try:
        mapping = parse_ticker_map(json.loads(get(TICKERS_URL)))
    except (http.FetchError, ValueError) as exc:
        report["errors"].append(f"correspondance des symboles de la SEC illisible : {exc}")
        return report
    for ticker, exchange in tickers.items():
        if time.monotonic() > deadline:
            report["errors"].append("délai atteint : fondamentaux EDGAR incomplets")
            break
        found = mapping.get(sec_symbol(ticker))
        if found is None:
            report["absent"].append(ticker)
            continue
        retrieved_at = clock.iso()
        try:
            built = _fetch_one(Issuer(ticker, found[0], found[1], exchange), get, retrieved_at)
        except _SecRefusedError as exc:
            report["errors"].append(str(exc))
            break
        except (EdgarError, ValueError) as exc:
            report["errors"].append(str(exc))
            continue
        stage(fundamentals_item(built, run_id=run_id, retrieved_at=retrieved_at))
        report["staged"].append(ticker)
    return report
