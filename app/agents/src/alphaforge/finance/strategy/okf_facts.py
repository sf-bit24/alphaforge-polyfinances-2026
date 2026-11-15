"""Faits de la base générale OKF (fondamentaux publiés, actualités), lus de façon déterministe.

Lot E de l'étape 0. Ce module ne calcule AUCUN score : les fondamentaux ont un poids nul dans le classement de
l'étape 0 (2 titres sur 20 seulement sont couverts ; SEC EDGAR viendra avec l'issue #27). Ils servent de contexte
cité par les lentilles. Une actualité n'est jamais un fait : statut HYPOTHESE toujours, et
``debate.merge.apply_amendments`` refuse tout amendement qui s'en réclame (sauf ``flag_only``).

Règles :
- on ne lit que le frontmatter YAML (``okf.parse``), jamais un nombre du corps Markdown ;
- chaque champ chiffré a une unité déclarée dans un registre (millions de la devise de publication, montant par
  action, points de pourcentage, ratio) ; un champ inconnu fait refuser le document : on ne devine pas son unité ;
- point dans le temps : une entrée n'est admissible qu'à partir de sa date de publication (``published_at <= as_of``) ;
  ``prior_year`` n'a pas de date de publication propre et hérite de celle de sa période ; un dividende est publié
  à sa déclaration (``declared_at``) ; une actualité, à son ``published_at`` (date UTC) ;
- statut FAIT pour une valeur publiée telle quelle selon la norme comptable (IFRS) ; HYPOTHESE pour une mesure
  non IFRS définie par l'émetteur, une valeur convertie (points de pourcentage → fraction) ou dérivée (croissance
  sur un an).

Bibliothèque standard + pydantic + yaml (via ``okf.parse``) : sûr en CI, sans numpy. Simulation seulement.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from alphaforge import clock, okf
from alphaforge.finance.contracts.decision import Fact, Source

FUNDAMENTALS_PREFIX = "general/societes/"
NEWS_PREFIX = "general/actualites/"
FUND_FACT_PREFIX = "okf.fund."
NEWS_FACT_PREFIX = "okf.news."
FUNDAMENTALS_TYPE = "Company Fundamentals"
NEWS_TYPE = "News"
TRACE_PLACEHOLDER = "okf.general"  # l'appelant ré-estampille chaque Fact avec l'étape tracée qui le lit

Currency = Literal["CAD", "USD", "EUR"]
_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")


class OkfFactsError(ValueError):
    """Document de la base générale refusé : on le signale clairement, on ne devine jamais."""


class WrongDocType(OkfFactsError):
    """Document OKF d'un autre type connu (ex. un index sous ``general/societes/``) : ignoré, pas refusé."""


def canonical_ticker(ticker: Any) -> str:
    """``shop.to`` → ``SHOP.TO`` ; refuse ce qui n'a pas la forme d'un symbole."""
    if not isinstance(ticker, str):
        raise OkfFactsError(f"ticker non textuel : {ticker!r}")
    text = ticker.strip().upper()
    if not _TICKER.match(text):
        raise OkfFactsError(f"ticker invalide : {ticker!r}")
    return text


def as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.astimezone(UTC).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


# ----------------------------------------------------------------------------------------- registre des unités
@dataclass(frozen=True)
class Metric:
    """Unité d'un champ chiffré. ``gaap=False`` : mesure non conforme à la norme comptable, définie par l'émetteur."""

    label_fr: str
    kind: Literal["millions", "per_share", "pct", "ratio"]
    gaap: bool = True


PERIOD_METRICS: dict[str, Metric] = {
    "revenue": Metric("Produits", "millions"),
    "gross_profit": Metric("Bénéfice brut", "millions"),
    "operating_income": Metric("Bénéfice d'exploitation", "millions"),
    "net_income": Metric("Bénéfice net", "millions"),
    "net_income_attributable": Metric("Bénéfice net attribuable aux actionnaires", "millions"),
    "diluted_eps": Metric("Bénéfice net dilué par action", "per_share"),
    "adjusted_ebitda": Metric("BAIIA ajusté", "millions", gaap=False),
    "operating_cash_flow": Metric("Flux de trésorerie liés à l'exploitation", "millions"),
    "capital_expenditures": Metric("Acquisitions d'immobilisations", "millions"),
    "fcfa2s": Metric("Flux de trésorerie disponibles pour les actionnaires (FCFA2S)", "millions", gaap=False),
    "organic_growth_pct": Metric("Croissance interne", "pct", gaap=False),
}
BALANCE_METRICS: dict[str, Metric] = {
    "total_assets": Metric("Actif total", "millions"),
    "cash": Metric("Trésorerie et équivalents", "millions"),
    "long_term_debt": Metric("Dette à long terme", "millions"),
    "interest_bearing_debt": Metric("Dette portant intérêt", "millions"),
    "net_interest_bearing_debt": Metric("Dette nette portant intérêt", "millions", gaap=False),
    "equity_attributable": Metric("Capitaux propres attribuables aux actionnaires", "millions"),
    "leverage_ratio": Metric("Ratio de levier défini par l'émetteur", "ratio", gaap=False),
    "return_on_equity_pct": Metric("Rendement des capitaux propres", "pct", gaap=False),
    "debt_with_recourse": Metric("Dette avec recours", "millions"),
    "debt_without_recourse": Metric("Dette sans recours", "millions"),
    "irga_liability": Metric("Passif au titre de l'IRGA", "millions"),
    "total_liabilities": Metric("Passif total", "millions"),
    "total_equity": Metric("Capitaux propres totaux", "millions"),
    "non_controlling_interests": Metric("Participations ne donnant pas le contrôle", "millions"),
}


def fact_unit(metric: Metric, reporting_currency: str) -> tuple[str, str | None, float]:
    """(unité du Fact, devise, facteur) : les ``*_pct`` sont des points de pourcentage, un Fact « % » une fraction."""
    if metric.kind == "millions":
        return "millions", reporting_currency, 1.0
    if metric.kind == "per_share":
        return "par action", reporting_currency, 1.0
    if metric.kind == "pct":
        return "%", None, 0.01
    return "ratio", None, 1.0


# ----------------------------------------------------------------------------------------- validation stricte
def _iso_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and len(value.strip()) == 10:
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise ValueError(f"date ISO AAAA-MM-JJ attendue, reçu {value!r}")


def _number(name: str, value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} : nombre fini attendu, reçu {value!r}")
    return value


IsoDate = Annotated[date, BeforeValidator(_iso_date)]


def _split(raw: Any, structural: set[str], registry: dict[str, Metric], where: str) -> dict[str, Any]:
    """Sépare les champs de structure des champs chiffrés ; un champ chiffré hors registre fait refuser l'entrée."""
    if not isinstance(raw, dict):
        raise ValueError(f"{where} : mapping attendu, reçu {type(raw).__name__}")
    out = {k: v for k, v in raw.items() if k in structural}
    values: dict[str, int | float] = {}
    for k, v in raw.items():
        if k in structural:
            continue
        if k not in registry:
            raise ValueError(f"{where} : champ inconnu {k!r} (unité non déclarée dans le registre, on ne devine pas)")
        values[k] = _number(k, v)
    out["values"] = values
    return out


def _peek(raw: Any, name: str) -> Any:
    return raw.get(name) if isinstance(raw, dict) else None


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PriorYear(_Strict):
    """Même période un an plus tôt. Sa date de publication est celle de la période qui la porte (héritage)."""

    observed_at: IsoDate
    published_at: IsoDate
    values: dict[str, int | float]

    @model_validator(mode="before")
    @classmethod
    def _metrics(cls, raw: Any) -> dict[str, Any]:
        return _split(raw, {"observed_at", "published_at"}, PERIOD_METRICS, "prior_year")


class Period(_Strict):
    period: StrictStr = Field(min_length=1)
    kind: Literal["quarter", "fiscal_year", "year_to_date"]
    weeks: StrictInt | None = Field(default=None, gt=0)
    months: StrictInt | None = Field(default=None, gt=0)
    observed_at: IsoDate
    published_at: IsoDate
    source: StrictStr = Field(min_length=1)
    values: dict[str, int | float]
    prior_year: PriorYear | None = None

    @model_validator(mode="before")
    @classmethod
    def _metrics(cls, raw: Any) -> dict[str, Any]:
        structural = {"period", "kind", "weeks", "months", "observed_at", "published_at", "source", "prior_year"}
        out = _split(raw, structural, PERIOD_METRICS, f"periods[{_peek(raw, 'period')!r}]")
        prior = out.get("prior_year")
        if prior is not None:
            if not isinstance(prior, dict):
                raise ValueError("prior_year : mapping attendu")
            if "published_at" in prior:
                raise ValueError("prior_year ne déclare pas published_at : il hérite de celui de sa période")
            out["prior_year"] = {**prior, "published_at": out.get("published_at")}
        return out

    @model_validator(mode="after")
    def _dates(self) -> Period:
        if self.observed_at > self.published_at:
            raise ValueError(f"{self.period} : observed_at après published_at")
        if self.prior_year is not None and self.prior_year.observed_at >= self.observed_at:
            raise ValueError(f"{self.period} : prior_year.observed_at doit précéder observed_at")
        return self


class BalanceSheet(_Strict):
    observed_at: IsoDate
    published_at: IsoDate
    # Chiffres repris comme comparatifs d'états publiés plus tard : on garde la date de ces états (prudent).
    published_at_basis: Literal["comparative_in_later_statements"] | None = None
    source: StrictStr = Field(min_length=1)
    values: dict[str, int | float]

    @model_validator(mode="before")
    @classmethod
    def _metrics(cls, raw: Any) -> dict[str, Any]:
        structural = {"observed_at", "published_at", "published_at_basis", "source"}
        return _split(raw, structural, BALANCE_METRICS, f"balance_sheets[{_peek(raw, 'observed_at')!r}]")

    @model_validator(mode="after")
    def _dates(self) -> BalanceSheet:
        if self.observed_at > self.published_at:
            raise ValueError(f"bilan au {self.observed_at} : observed_at après published_at")
        return self


class Dividend(_Strict):
    """Dividende déclaré : la déclaration (communiqué) en est la date de publication."""

    declared_at: IsoDate
    amount: Annotated[float, BeforeValidator(lambda v: _number("amount", v))] = Field(gt=0)
    currency: Currency  # devise propre à l'entrée (ATD : dividende en CAD, résultats en USD)
    record_date: IsoDate | None = None
    payment_date: IsoDate | None = None
    source: StrictStr = Field(min_length=1)


class SourceRef(BaseModel):
    """Entrée ``sources`` du frontmatter : la publication de l'émetteur d'où viennent les chiffres."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    id: StrictStr
    title: StrictStr
    resource: StrictStr | None = None
    retrieved_at: datetime | None = None

    @field_validator("retrieved_at", mode="before")
    @classmethod
    def _ts(cls, value: Any) -> datetime | None:
        if value is None:
            return None
        parsed = clock.parse_datetime(value)
        if parsed is None:
            raise ValueError(f"retrieved_at illisible : {value!r}")
        return parsed


class CompanyFundamentals(_Strict):
    """Bloc ``data`` d'un document « Company Fundamentals », validé, avec sa provenance (clé, ETag ou sha256)."""

    key: StrictStr
    sha256: StrictStr  # ETag de l'objet du magasin, ou sha256 du texte
    url: StrictStr | None = None  # s3://<bucket>/<clé> si le bucket est connu
    ticker: str
    issuer: StrictStr
    exchange: StrictStr | None = None
    reporting_currency: Currency
    unit: Literal["millions"]
    accounting_standard: StrictStr = Field(min_length=1)
    retrieved_from: StrictStr | None = None
    periods: list[Period] = Field(default_factory=list)
    balance_sheets: list[BalanceSheet] = Field(default_factory=list)
    dividends: list[Dividend] = Field(default_factory=list)
    sources: dict[str, SourceRef]

    @field_validator("ticker", mode="before")
    @classmethod
    def _ticker(cls, value: Any) -> str:
        return canonical_ticker(value)

    @model_validator(mode="after")
    def _integrity(self) -> CompanyFundamentals:
        cited = [p.source for p in self.periods] + [b.source for b in self.balance_sheets]
        cited += [d.source for d in self.dividends]
        unknown = sorted({s for s in cited if s not in self.sources})
        if unknown:
            raise ValueError(f"source absente du frontmatter : {unknown}")
        for what, keys in (
            ("période", [p.period for p in self.periods]),
            ("bilan", [b.observed_at for b in self.balance_sheets]),
            ("dividende", [d.declared_at for d in self.dividends]),
        ):
            if len(keys) != len(set(keys)):
                raise ValueError(f"{what} en double")
        return self

    def admissible(self, as_of: date | datetime | str) -> CompanyFundamentals:
        """Vue point dans le temps : seulement les entrées publiées au plus tard à ``as_of`` (``prior_year`` suit
        sa période)."""
        d = as_date(as_of)
        return self.model_copy(
            update={
                "periods": [p for p in self.periods if p.published_at <= d],
                "balance_sheets": [b for b in self.balance_sheets if b.published_at <= d],
                "dividends": [x for x in self.dividends if x.declared_at <= d],
            }
        )


def _errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:6]:
        loc = ".".join(str(x) for x in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    return "; ".join(parts)


def _frontmatter(doc_text: str, key: str, expected: str) -> okf.OkfDoc:
    try:
        doc = okf.parse(doc_text)
    except okf.OkfError as exc:
        raise OkfFactsError(f"{key} : {exc}") from exc
    if doc.type != expected:
        if doc.type in okf.DOC_TYPES:
            raise WrongDocType(f"{key} : type {doc.type!r}, « {expected} » attendu")
        raise OkfFactsError(f"{key} : type inconnu {doc.type!r}")
    problems = okf.validate(doc)
    if problems:
        raise OkfFactsError(f"{key} : document OKF non conforme ({'; '.join(problems)})")
    return doc


def parse_company_fundamentals(
    doc_text: str, key: str, etag_or_sha: str, *, bucket: str | None = None
) -> CompanyFundamentals:
    """Lit et valide un document « Company Fundamentals » ; lève ``OkfFactsError`` (message clair) sinon."""
    doc = _frontmatter(doc_text, key, FUNDAMENTALS_TYPE)
    data = doc.frontmatter.get("data")
    if not isinstance(data, dict) or not data:
        raise OkfFactsError(f"{key} : bloc data absent ou vide")
    reserved = {"key", "sha256", "url", "sources"} & set(data)
    if reserved:
        raise OkfFactsError(f"{key} : champs réservés dans data : {sorted(reserved)}")
    ids = [s.get("id") for s in doc.frontmatter["sources"]]
    if len(ids) != len(set(ids)):
        raise OkfFactsError(f"{key} : identifiants de source en double")
    try:
        return CompanyFundamentals.model_validate(
            {
                **data,
                "key": key,
                "sha256": etag_or_sha,
                "url": f"s3://{bucket}/{key}" if bucket else None,
                "sources": {s["id"]: s for s in doc.frontmatter["sources"]},
            }
        )
    except ValidationError as exc:
        raise OkfFactsError(f"{key} : données refusées ({_errors(exc)})") from exc


# ----------------------------------------------------------------------------------------- Facts des fondamentaux
_KIND_RANK = {"quarter": 2, "year_to_date": 1, "fiscal_year": 0}  # à date égale : la période la plus courte


def _latest_period(periods: list[Period], field: str) -> Period | None:
    have = [p for p in periods if field in p.values]
    return max(have, key=lambda p: (p.observed_at, _KIND_RANK[p.kind], p.published_at, p.period), default=None)


def _latest_balance(sheets: list[BalanceSheet], field: str) -> BalanceSheet | None:
    have = [b for b in sheets if field in b.values]
    return max(have, key=lambda b: (b.observed_at, b.published_at), default=None)


def _status(metric: Metric, *, converted: bool = False, derived: bool = False) -> str:
    return "FAIT" if metric.gaap and not converted and not derived else "HYPOTHESE"


class _Builder:
    def __init__(self, cf: CompanyFundamentals, trace_id: str):
        self.cf, self.trace_id, self.out = cf, trace_id, []

    def sources(self, path: str, source_id: str) -> list[Source]:
        ref = self.cf.sources[source_id]
        return [
            Source(dataset=f"okf:{self.cf.key}", url=self.cf.url, sha256=self.cf.sha256, processing=path),
            Source(
                dataset=f"emetteur:{source_id}",
                url=ref.resource,
                retrieved_utc=ref.retrieved_at,
                processing=f"chiffre relevé dans : {ref.title}"[:300],
            ),
        ]

    def add(self, field_id, label, value, unit, currency, status, observed, published, path, source_id) -> None:
        self.out.append(
            Fact(
                fact_id=f"{FUND_FACT_PREFIX}{self.cf.ticker}.{field_id}",
                label_fr=label,
                value=value,
                unit=unit,
                currency=currency,
                as_of=observed,
                published=published,
                status=status,
                trace_id=self.trace_id,
                sources=self.sources(path, source_id),
            )
        )

    def period_metric(self, periods: list[Period], field: str) -> Period | None:
        p = _latest_period(periods, field)
        if p is None:
            return None
        cf, m = self.cf, PERIOD_METRICS[field]
        unit, cur, factor = fact_unit(m, cf.reporting_currency)
        what = f"en millions {cur}" if unit == "millions" else f"en {cur} par action" if unit == "par action" else ""
        label = f"{cf.ticker} : {m.label_fr} ({p.period}, période close le {p.observed_at.isoformat()})"
        label += f", {what}" if what else ""
        path = f"data.periods[period='{p.period}'].{field}"
        if not m.gaap:
            label += f" — mesure non {cf.accounting_standard} de l'émetteur"
            path += f" ; mesure non {cf.accounting_standard} définie par l'émetteur"
        value = p.values[field] if factor == 1.0 else round(p.values[field] * factor, 10)
        self.add(
            field,
            label,
            value,
            unit,
            cur,
            _status(m, converted=factor != 1.0),
            p.observed_at,
            p.published_at,
            path,
            p.source,
        )
        return p

    def balance_metric(self, sheets: list[BalanceSheet], field: str, field_id: str) -> None:
        b = _latest_balance(sheets, field)
        if b is None:
            return
        cf, m = self.cf, BALANCE_METRICS[field]
        unit, cur, factor = fact_unit(m, cf.reporting_currency)
        label = f"{cf.ticker} : {m.label_fr} au {b.observed_at.isoformat()}"
        path = f"data.balance_sheets[observed_at='{b.observed_at.isoformat()}'].{field}"
        if factor != 1.0:
            path += f" × {factor:g} (points de pourcentage → fraction)"
        if not m.gaap:
            label += f" — mesure non {cf.accounting_standard} de l'émetteur"
            path += f" ; mesure non {cf.accounting_standard} définie par l'émetteur"
        value = b.values[field] if factor == 1.0 else round(b.values[field] * factor, 10)
        self.add(
            field_id,
            label,
            value,
            unit,
            cur,
            _status(m, converted=factor != 1.0),
            b.observed_at,
            b.published_at,
            path,
            b.source,
        )


def fundamentals_facts(
    cf: CompanyFundamentals, as_of: date | datetime | str, *, trace_id: str = TRACE_PLACEHOLDER
) -> list[Fact]:
    """Facts ``okf.fund.<TICKER>.<champ>`` connus à ``as_of``, dans un ordre fixe : produits (et leur croissance sur
    un an si la même période a son ``prior_year``), bénéfice d'exploitation, bénéfice net, BPA dilué, levier,
    rendement des capitaux propres, dernier dividende. Chaque champ vient de la dernière entrée admissible qui le
    porte (la période est nommée dans le libellé). Aucun chiffre n'est lu dans le corps Markdown."""
    adm = cf.admissible(as_of)
    b = _Builder(adm, trace_id)
    p = b.period_metric(adm.periods, "revenue")
    if p is not None and p.prior_year is not None and p.prior_year.values.get("revenue"):
        prior = p.prior_year.values["revenue"]
        base = f"data.periods[period='{p.period}']"
        b.add(
            "revenue_growth_yoy",
            f"{adm.ticker} : croissance des produits sur un an ({p.period} contre la même période un an plus tôt)",
            round(p.values["revenue"] / prior - 1, 10),
            "%",
            None,
            "HYPOTHESE",  # valeur dérivée
            p.observed_at,
            p.published_at,
            f"{base}.revenue / {base}.prior_year.revenue - 1 (prior_year publié avec sa période)",
            p.source,
        )
    b.period_metric(adm.periods, "operating_income")
    if b.period_metric(adm.periods, "net_income_attributable") is None:
        b.period_metric(adm.periods, "net_income")
    b.period_metric(adm.periods, "diluted_eps")
    b.balance_metric(adm.balance_sheets, "leverage_ratio", "leverage_ratio")
    b.balance_metric(adm.balance_sheets, "return_on_equity_pct", "return_on_equity")
    if adm.dividends:
        d = max(adm.dividends, key=lambda x: x.declared_at)
        b.add(
            "dividend",
            f"{adm.ticker} : dernier dividende déclaré le {d.declared_at.isoformat()}, en {d.currency} par action",
            d.amount,
            "par action",
            d.currency,
            "FAIT",
            d.declared_at,
            d.declared_at,
            f"data.dividends[declared_at='{d.declared_at.isoformat()}'].amount (devise de l'entrée : {d.currency})",
            d.source,
        )
    return b.out


# ----------------------------------------------------------------------------------------- actualités
class NewsItem(BaseModel):
    """Actualité de la base générale : titre, date, titres concernés. Jamais un chiffre, jamais un sentiment."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    key: StrictStr
    sha256: StrictStr
    title: StrictStr = Field(min_length=1)
    published_at: datetime
    observed_at: date | None = None
    retrieved_at: datetime | None = None
    url: StrictStr | None = None
    source: StrictStr = Field(min_length=1)
    tickers: tuple[str, ...]

    def admissible(self, as_of: date | datetime | str) -> bool:
        return self.published_at.astimezone(UTC).date() <= as_date(as_of)


def parse_news(doc_text: str, key: str, etag: str) -> NewsItem:
    """Lit un document « News » écrit par A6 (``collect.supervisor.news_doc``) ; lève ``OkfFactsError`` sinon."""
    doc = _frontmatter(doc_text, key, NEWS_TYPE)
    data = doc.frontmatter.get("data")
    if not isinstance(data, dict):
        raise OkfFactsError(f"{key} : bloc data absent")
    published = clock.parse_datetime(data.get("published_at"))
    if published is None:
        raise OkfFactsError(f"{key} : data.published_at absent ou illisible ({data.get('published_at')!r})")
    raw_tickers = data.get("tickers")
    if not isinstance(raw_tickers, list):
        raise OkfFactsError(f"{key} : data.tickers doit être une liste")
    try:
        tickers = tuple(dict.fromkeys(canonical_ticker(t) for t in raw_tickers))
    except OkfFactsError as exc:
        raise OkfFactsError(f"{key} : {exc}") from exc
    observed = clock.parse_datetime(data.get("observed_at")) if data.get("observed_at") else None
    try:
        return NewsItem(
            key=key,
            sha256=etag,
            title=doc.title,
            published_at=published,
            observed_at=observed.date() if observed else None,
            retrieved_at=clock.parse_datetime(data.get("retrieved_at")),
            url=data.get("url"),
            source=data.get("source"),
            tickers=tickers,
        )
    except ValidationError as exc:
        raise OkfFactsError(f"{key} : actualité refusée ({_errors(exc)})") from exc


def news_fact(item: NewsItem, ticker: str, n: int, *, trace_id: str = TRACE_PLACEHOLDER) -> Fact:
    """Fact ``okf.news.<TICKER>.<n>`` : le titre de l'article, statut HYPOTHESE (rumeur ≠ fait)."""
    published = item.published_at.astimezone(UTC).date()
    return Fact(
        fact_id=f"{NEWS_FACT_PREFIX}{canonical_ticker(ticker)}.{n}",
        label_fr=f"Actualité du {published.isoformat()} ({item.source}), titre seulement, non vérifié",
        value=item.title[:300],
        unit="texte",
        as_of=item.observed_at or published,
        published=published,
        status="HYPOTHESE",
        trace_id=trace_id,
        sources=[
            Source(
                dataset=f"okf-news:{item.key}",
                url=item.url,
                retrieved_utc=item.retrieved_at,
                sha256=item.sha256,
                processing="frontmatter : title, data.published_at, data.tickers ; aucun chiffre ni sentiment lu",
            )
        ],
    )


def news_facts(
    doc_text: str,
    key: str,
    etag: str,
    as_of: date | datetime | str,
    *,
    ticker: str | None = None,
    n: int = 1,
    trace_id: str = TRACE_PLACEHOLDER,
) -> list[Fact]:
    """Facts d'une actualité admissible à ``as_of`` (``published_at <= as_of``), un par titre concerné (ou pour
    ``ticker`` seulement), numérotés ``n``. Liste vide si l'actualité est publiée après ``as_of``."""
    item = parse_news(doc_text, key, etag)
    if not item.admissible(as_of):
        return []
    wanted = [canonical_ticker(ticker)] if ticker is not None else list(item.tickers)
    return [news_fact(item, t, n, trace_id=trace_id) for t in wanted if t in item.tickers]
