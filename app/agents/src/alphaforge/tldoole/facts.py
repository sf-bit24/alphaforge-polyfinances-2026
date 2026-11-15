"""Faits chiffrés des vidéos tldoole : calculés par le code, datés, cités, formatés dans la langue.

Le modèle (A8) ne tape aucun chiffre : il demande un fait par un outil, reçoit son identifiant (``f1``) et
ses valeurs déjà formatées, puis y renvoie dans son scénario (``f1.max_drawdown``). Le code dessine les
chiffres à partir de ce registre, et refuse un scénario dont la narration contient un nombre qui n'en vient pas.

Sources : le jeu de départ du Datathon (prix ajustés Yahoo Finance, change et taux de la Banque du Canada,
séries FRED), le portefeuille confirmé de l'investisseur, ou un calcul illustratif dont l'hypothèse est dite.
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from .. import starter

MAX_POINTS = 140
CALC_SOURCE = {
    "id": "calc-alphaforge",
    "title": "Calcul AlphaForge, à titre d'illustration (hypothèse indiquée)",
    "resource": "code:alphaforge.tldoole.facts",
}
_MONTHS = {
    "fr": ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
    "en": ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."],
}
MACRO_LABELS = {
    "BD.CDN.10YR.DQ.YLD": ("Taux des obligations du Canada à 10 ans", "Government of Canada 10-year bond yield"),
    "BD.CDN.2YR.DQ.YLD": ("Taux des obligations du Canada à 2 ans", "Government of Canada 2-year bond yield"),
    "V39079": ("Taux directeur de la Banque du Canada", "Bank of Canada policy rate"),
    "STATIC_TOTALCPICHANGE": ("Inflation au Canada (IPC, sur un an)", "Canada inflation (CPI, year over year)"),
    "CPIAUCSL": ("Indice des prix aux États-Unis (IPC)", "U.S. consumer price index (CPI)"),
    "DFF": ("Taux directeur effectif américain", "U.S. effective federal funds rate"),
    "DGS10": ("Taux du Trésor américain à 10 ans", "U.S. Treasury 10-year yield"),
    "DGS2": ("Taux du Trésor américain à 2 ans", "U.S. Treasury 2-year yield"),
    "UNRATE": ("Taux de chômage aux États-Unis", "U.S. unemployment rate"),
}
METRIC_LABELS = {
    "total_return": ("Rendement total", "Total return"),
    "cagr": ("Rendement annuel moyen", "Average annual return"),
    "annualized_volatility": ("Volatilité annualisée", "Annualized volatility"),
    "max_drawdown": ("Baisse maximale", "Maximum drawdown"),
    "value_of_100": ("Valeur de 100 $ investis", "Value of $100 invested"),
}
COMPARABLE = tuple(METRIC_LABELS)


class FactError(ValueError):
    """Demande de fait impossible (titre inconnu, série absente, paramètre hors bornes)."""


# --------------------------------------------------------------------------- formats
def _decimal(value: float, decimals: int, locale: str) -> str:
    text = f"{abs(value):,.{decimals}f}"
    if locale == "fr":
        text = text.replace(",", "\u00a0").replace(".", ",")
    return text


def fmt_pct(value: float, locale: str, *, signed: bool = False, decimals: int = 1) -> str:
    """0.642 -> « 64,2 % » (fr) ou « 64.2% » (en); signe moins typographique."""
    body = _decimal(value * 100, decimals, locale)
    sign = "\u2212" if value < 0 and round(abs(value) * 100, decimals) else ("+" if signed and value > 0 else "")
    return f"{sign}{body}\u00a0%" if locale == "fr" else f"{sign}{body}%"


def fmt_points(value: float, locale: str) -> str:
    """Variation d'un taux en points de pourcentage, signée."""
    sign = "\u2212" if value < 0 else "+"
    body = _decimal(value, 2, locale)
    return f"{sign}{body}\u00a0points" if locale == "fr" else f"{sign}{body} percentage points"


def fmt_rate(value: float, locale: str) -> str:
    """Taux déjà en pour cent : 3.78 -> « 3,78 % »."""
    return fmt_pct(value / 100, locale, decimals=2)


def fmt_money(value: float, locale: str, currency: str = "CAD") -> str:
    body = _decimal(value, 0, locale)
    sign = "\u2212" if value < 0 and round(abs(value)) else ""
    if locale == "fr":
        return f"{sign}{body}\u00a0$" + ("\u00a0US" if currency == "USD" else "")
    return f"{sign}{'US$' if currency == 'USD' else '$'}{body}"


def fmt_number(value: float, locale: str, decimals: int = 2) -> str:
    sign = "\u2212" if value < 0 else ""
    return sign + _decimal(value, decimals, locale)


def fmt_month(date: str, locale: str) -> str:
    year, month = int(date[:4]), int(date[5:7])
    return f"{_MONTHS.get(locale, _MONTHS['fr'])[month - 1]} {year}"


def fmt_ratio(value: float, locale: str) -> str:
    return _decimal(value, 1, locale)


_NUMBER = re.compile(
    r"(?P<fr>\d{1,3}(?:[\u00a0\u202f ]\d{3})+(?!\d)(?:,\d+)?)"  # 61 960 ou 1 234,5 (fr)
    r"|(?P<en>\d{1,3}(?:,\d{3})+(?!\d)(?:\.\d+)?)"  # 1,234.5 (en)
    r"|(?P<plain>\d+(?:[.,]\d+)?)"  # 2022, 16,4 ou 13.1
)


def number_tokens(text: str) -> set[str]:
    """Nombres d'un texte, normalisés : séparateurs de milliers retirés, décimale en point, zéros finaux ôtés."""
    tokens = set()
    for match in _NUMBER.finditer(text or ""):
        if match.group("fr"):
            value = re.sub(r"[\u00a0\u202f ]", "", match.group("fr")).replace(",", ".")
        elif match.group("en"):
            value = match.group("en").replace(",", "")
        else:
            value = match.group("plain").replace(",", ".")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        tokens.add(value)
    return tokens


def _variants(value: float) -> set[str]:
    """Écritures acceptées d'une valeur citée oralement : arrondie à l'unité, au dixième, au centième."""
    out = set()
    for digits in (0, 1, 2):
        text = f"{abs(value):.{digits}f}"
        out.add(text.rstrip("0").rstrip(".") if "." in text else text)
    out.add(str(int(abs(value))))
    return out


# --------------------------------------------------------------------------- données du jeu de départ
@lru_cache(maxsize=1)
def _prices() -> dict[str, list[tuple[str, float]]]:
    series: dict[str, list[tuple[str, float]]] = {}
    with (starter.DATA_DIR / "prices_daily.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                value = float(row["adj_close"])
            except (TypeError, ValueError):
                continue
            if value > 0:
                series.setdefault(row["ticker"], []).append((row["date"], value))
    for points in series.values():
        points.sort()
    return series


@lru_cache(maxsize=1)
def _macro() -> dict[str, list[tuple[str, float]]]:
    series: dict[str, list[tuple[str, float]]] = {}
    with (starter.DATA_DIR / "macro_rates.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                series.setdefault(row["series_id"], []).append((row["date"], float(row["value"])))
            except (TypeError, ValueError):
                continue
    for points in series.values():
        points.sort()
    return series


@lru_cache(maxsize=1)
def _fx() -> list[tuple[str, float]]:
    with (starter.DATA_DIR / "fx_usdcad_daily.csv").open(newline="", encoding="utf-8") as handle:
        points = [(row["date"], float(row["usdcad"])) for row in csv.DictReader(handle) if row.get("usdcad")]
    return sorted(points)


def _downsample(points: list[tuple[str, float]], limit: int = MAX_POINTS) -> list[tuple[int, str, float]]:
    """Garde au plus ``limit`` points, dont le premier et le dernier (avec leur rang d'origine)."""
    if len(points) <= limit:
        return [(i, d, v) for i, (d, v) in enumerate(points)]
    step = (len(points) - 1) / (limit - 1)
    picked = sorted({round(k * step) for k in range(limit)})
    return [(i, points[i][0], points[i][1]) for i in picked]


def asset_metrics(points: list[tuple[str, float]], *, periods_per_year: int) -> dict[str, Any]:
    """Rendement total et annuel, volatilité annualisée, baisse maximale et sa récupération."""
    if len(points) < 30:
        raise FactError("not enough prices")
    first_date, first = points[0]
    last_date, last = points[-1]
    returns = [math.log(b / a) for (_, a), (_, b) in zip(points, points[1:], strict=False)]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    days = max(1, (_ordinal(last_date) - _ordinal(first_date)))
    peak_value, peak_index = points[0][1], 0
    worst, worst_peak, worst_trough = 0.0, 0, 0
    for index, (_, value) in enumerate(points):
        if value > peak_value:
            peak_value, peak_index = value, index
        drawdown = value / peak_value - 1
        if drawdown < worst:
            worst, worst_peak, worst_trough = drawdown, peak_index, index
    recovery = None
    if worst < 0:
        target = points[worst_peak][1]
        for date, value in points[worst_trough:]:
            if value >= target:
                recovery = date
                break
    return {
        "first_date": first_date,
        "last_date": last_date,
        "total_return": last / first - 1,
        "cagr": (last / first) ** (365.25 / days) - 1,
        "annualized_volatility": math.sqrt(variance) * math.sqrt(periods_per_year),
        "max_drawdown": worst,
        "peak_index": worst_peak,
        "trough_index": worst_trough,
        "peak_date": points[worst_peak][0],
        "trough_date": points[worst_trough][0],
        "recovery_date": recovery,
        "value_of_100": 100 * last / first,
    }


def _ordinal(date: str) -> int:
    from datetime import date as _date

    return _date.fromisoformat(date[:10]).toordinal()


# --------------------------------------------------------------------------- registre
class FactBook:
    """Faits calculés pendant l'écriture d'un scénario, adressés par ``f1``, ``f2``…"""

    def __init__(
        self,
        locale: str = "fr",
        *,
        client_portfolio: dict[str, Any] | None = None,
        client_portfolio_key: str | None = None,
    ):
        self.locale = locale
        self.facts: dict[str, dict[str, Any]] = {}
        self._series: dict[str, dict[str, Any]] = {}
        self._portfolio = client_portfolio
        self._portfolio_key = client_portfolio_key

    def t(self, pair: tuple[str, str]) -> str:
        return pair[1] if self.locale == "en" else pair[0]

    def _metric(self, key: str, value: float, text: str) -> dict[str, Any]:
        return {"value": value, "text": text, "label": self.t(METRIC_LABELS[key])}

    def _add(self, fact: dict[str, Any], series: dict[str, Any] | None = None) -> dict[str, Any]:
        key = _fact_key(fact)
        for existing in self.facts.values():
            if _fact_key(existing) == key:
                return existing
        fact_id = f"f{len(self.facts) + 1}"
        fact = {"fact_id": fact_id, **fact}
        self.facts[fact_id] = fact
        if series:
            self._series[fact_id] = series
        return fact

    # ------------------------------------------------------------------ faits sur le jeu de départ
    def asset_stats(self, ticker: str) -> dict[str, Any]:
        ticker = (ticker or "").strip().upper()
        points = _prices().get(ticker)
        asset = starter.universe().get(ticker)
        if not points or asset is None:
            raise FactError(f"unknown ticker {ticker!r}; use a ticker of the starter universe")
        per_year = 365 if asset.asset_class == "crypto" else 252
        m = asset_metrics(points, periods_per_year=per_year)
        loc = self.locale
        metrics = {
            "total_return": self._metric(
                "total_return", m["total_return"], fmt_pct(m["total_return"], loc, signed=True)
            ),
            "cagr": self._metric("cagr", m["cagr"], fmt_pct(m["cagr"], loc, signed=True)),
            "annualized_volatility": self._metric(
                "annualized_volatility", m["annualized_volatility"], fmt_pct(m["annualized_volatility"], loc)
            ),
            "max_drawdown": self._metric("max_drawdown", m["max_drawdown"], fmt_pct(m["max_drawdown"], loc)),
            "value_of_100": self._metric(
                "value_of_100", m["value_of_100"], fmt_money(m["value_of_100"], loc, asset.currency)
            ),
            "drawdown_peak": {"text": fmt_month(m["peak_date"], loc), "date": m["peak_date"]},
            "drawdown_trough": {"text": fmt_month(m["trough_date"], loc), "date": m["trough_date"]},
            "recovery": {
                "text": fmt_month(m["recovery_date"], loc) if m["recovery_date"] else self.t(("pas encore", "not yet")),
                "date": m["recovery_date"],
            },
        }
        sampled = _downsample(points)
        rank = {original: position for position, (original, _, _) in enumerate(sampled)}
        series = {
            "values": [round(100 * v / points[0][1], 2) for _, _, v in sampled],
            "start_label": fmt_month(m["first_date"], loc),
            "end_label": fmt_month(m["last_date"], loc),
            "end_text": metrics["value_of_100"]["text"],
            "title": self.t(("Valeur de 100 $ investis", "Value of $100 invested"))
            + (" (USD)" if asset.currency == "USD" else ""),
            "highlight": _nearest_pair(rank, m["peak_index"], m["trough_index"]),
        }
        return self._add(
            {
                "kind": "asset",
                "entity": ticker,
                "name": asset.name,
                "currency": asset.currency,
                "asset_class": asset.asset_class,
                "period": {"start": m["first_date"], "end": m["last_date"]},
                "metrics": metrics,
                "chart": True,
                "note": self.t(
                    (
                        "Prix ajustés des distributions et fractionnements; le passé ne garantit pas l'avenir.",
                        "Prices adjusted for distributions and splits; the past does not guarantee the future.",
                    )
                ),
                "source": starter.source_entry(
                    "prices_daily.csv",
                    self.t(
                        (
                            "Jeu de départ, prix quotidiens ajustés (Yahoo Finance)",
                            "Starter dataset, adjusted daily prices (Yahoo Finance)",
                        )
                    ),
                    observed_at=m["last_date"],
                ),
            },
            series,
        )

    def compare_assets(self, tickers: Iterable[str], metric: str) -> dict[str, Any]:
        if metric not in COMPARABLE:
            raise FactError(f"metric must be one of {', '.join(COMPARABLE)}")
        tickers = [str(t).strip().upper() for t in tickers][:3]
        if len(tickers) < 2 or len(set(tickers)) != len(tickers):
            raise FactError("compare 2 or 3 distinct tickers")
        items = []
        for ticker in tickers:
            fact = self.asset_stats(ticker)
            value = fact["metrics"][metric]
            items.append(
                {
                    "entity": ticker,
                    "name": fact["name"],
                    "value": value["value"],
                    "text": value["text"],
                    "of": fact["fact_id"],
                }
            )
        first, last = abs(items[0]["value"]), abs(items[-1]["value"])
        ratio = first / last if last else None
        metrics: dict[str, Any] = {}
        if ratio:
            metrics["ratio_first_last"] = {
                "value": ratio,
                "text": fmt_ratio(ratio, self.locale),
                "label": self.t(("Rapport entre le premier et le dernier", "Ratio of the first to the last")),
            }
        return self._add(
            {
                "kind": "compare",
                "metric": metric,
                "label": self.t(METRIC_LABELS[metric]),
                "items": items,
                "metrics": metrics,
                "period": self.facts[items[0]["of"]]["period"],
                "source": self.facts[items[0]["of"]]["source"],
            }
        )

    def macro_series(self, series_id: str) -> dict[str, Any]:
        points = _macro().get(series_id)
        meta = starter.macro_series().get(series_id)
        if not points or meta is None:
            raise FactError(f"unknown series {series_id!r}; use one of {', '.join(sorted(_macro()))}")
        loc = self.locale
        labels = MACRO_LABELS.get(series_id, (meta["label"], meta["label"]))
        is_rate = meta.get("unit") == "percent"
        fmt = (lambda v: fmt_rate(v, loc)) if is_rate else (lambda v: fmt_number(v, loc, 1))
        low = min(points, key=lambda p: p[1])
        high = max(points, key=lambda p: p[1])
        first, last = points[0], points[-1]
        metrics = {
            "first": {"value": first[1], "text": fmt(first[1]), "date": first[0], "month": fmt_month(first[0], loc)},
            "last": {"value": last[1], "text": fmt(last[1]), "date": last[0], "month": fmt_month(last[0], loc)},
            "min": {"value": low[1], "text": fmt(low[1]), "date": low[0], "month": fmt_month(low[0], loc)},
            "max": {"value": high[1], "text": fmt(high[1]), "date": high[0], "month": fmt_month(high[0], loc)},
        }
        if is_rate:
            metrics["change"] = {"value": last[1] - first[1], "text": fmt_points(last[1] - first[1], loc)}
        sampled = _downsample(points)
        series = {
            "values": [v for _, _, v in sampled],
            "start_label": fmt_month(first[0], loc),
            "end_label": fmt_month(last[0], loc),
            "end_text": metrics["last"]["text"],
            "title": self.t(labels),
        }
        return self._add(
            {
                "kind": "series",
                "entity": series_id,
                "name": self.t(labels),
                "period": {"start": first[0], "end": last[0]},
                "metrics": metrics,
                "chart": True,
                "source": starter.source_entry(
                    "macro_rates.csv", f"{self.t(labels)} ({meta['source']})", observed_at=last[0]
                ),
            },
            series,
        )

    def fx_usdcad(self) -> dict[str, Any]:
        points = _fx()
        loc = self.locale
        first, last = points[0], points[-1]
        low = min(points, key=lambda p: p[1])
        high = max(points, key=lambda p: p[1])
        change = last[1] / first[1] - 1
        metrics = {
            "first": {"value": first[1], "text": fmt_number(first[1], loc, 4), "month": fmt_month(first[0], loc)},
            "last": {"value": last[1], "text": fmt_number(last[1], loc, 4), "month": fmt_month(last[0], loc)},
            "min": {"value": low[1], "text": fmt_number(low[1], loc, 4), "month": fmt_month(low[0], loc)},
            "max": {"value": high[1], "text": fmt_number(high[1], loc, 4), "month": fmt_month(high[0], loc)},
            "usd_change": {
                "value": change,
                "text": fmt_pct(change, loc, signed=True),
                "label": self.t(
                    (
                        "Variation du dollar américain face au dollar canadien",
                        "Change of the US dollar against the Canadian dollar",
                    )
                ),
            },
            "swing": {
                "value": high[1] / low[1] - 1,
                "text": fmt_pct(high[1] / low[1] - 1, loc),
                "label": self.t(("Écart entre le plus bas et le plus haut", "Gap between the low and the high")),
            },
        }
        sampled = _downsample(points)
        series = {
            "values": [v for _, _, v in sampled],
            "start_label": fmt_month(first[0], loc),
            "end_label": fmt_month(last[0], loc),
            "end_text": metrics["last"]["text"],
            "title": self.t(("Combien de $ CA pour 1 $ US", "Canadian dollars for one US dollar")),
        }
        return self._add(
            {
                "kind": "fx",
                "entity": "USDCAD",
                "name": "USD/CAD",
                "period": {"start": first[0], "end": last[0]},
                "metrics": metrics,
                "chart": True,
                "source": starter.source_entry(
                    "fx_usdcad_daily.csv",
                    self.t(("Taux de change USD/CAD (Banque du Canada)", "USD/CAD exchange rate (Bank of Canada)")),
                    observed_at=last[0],
                ),
            },
            series,
        )

    # ------------------------------------------------------------------ calculs illustratifs
    def compound_growth(
        self, initial_cad: float, monthly_cad: float, annual_rate_pct: float, years: int
    ) -> dict[str, Any]:
        initial, monthly, rate, years = (
            _bounded(initial_cad, 0, 1e7),
            _bounded(monthly_cad, 0, 1e5),
            _bounded(annual_rate_pct, -10, 15),
            int(_bounded(years, 1, 50)),
        )
        monthly_rate = (1 + rate / 100) ** (1 / 12) - 1
        values, value = [initial], initial
        for _month in range(years * 12):
            value = value * (1 + monthly_rate) + monthly
            if (_month + 1) % 12 == 0:
                values.append(value)
        contributions = initial + monthly * 12 * years
        loc = self.locale
        metrics = {
            "final_value": {"value": value, "text": fmt_money(value, loc)},
            "contributions": {"value": contributions, "text": fmt_money(contributions, loc)},
            "growth": {"value": value - contributions, "text": fmt_money(value - contributions, loc)},
        }
        inputs = {
            "initial": fmt_money(initial, loc),
            "monthly": fmt_money(monthly, loc),
            "rate": fmt_pct(rate / 100, loc),
            "years": str(years),
        }
        series = {
            "values": [round(v, 2) for v in values],
            "start_label": self.t(("Aujourd'hui", "Today")),
            "end_label": self.t((f"Dans {years} ans", f"In {years} years")),
            "end_text": metrics["final_value"]["text"],
            "title": self.t(("Valeur du placement (hypothèse)", "Value of the investment (assumption)")),
        }
        return self._add(
            {
                "kind": "calc",
                "entity": "compound_growth",
                "name": self.t(("Intérêts composés", "Compound growth")),
                "inputs": inputs,
                "metrics": metrics,
                "chart": True,
                "assumption": self.t(
                    (
                        f"Rendement constant de {inputs['rate']} par année, versements mensuels de "
                        f"{inputs['monthly']}, sans frais ni impôt : une illustration, pas une prévision.",
                        f"Constant {inputs['rate']} yearly return, monthly deposits of {inputs['monthly']}, no fees or "
                        "taxes: an illustration, not a forecast.",
                    )
                ),
                "source": dict(CALC_SOURCE),
            },
            series,
        )

    def fee_drag(self, amount_cad: float, annual_return_pct: float, fee_pct: float, years: int) -> dict[str, Any]:
        amount = _bounded(amount_cad, 100, 1e7)
        gross = _bounded(annual_return_pct, -5, 15) / 100
        fee = _bounded(fee_pct, 0, 5) / 100
        years = int(_bounded(years, 1, 50))
        without_fees = amount * (1 + gross) ** years
        with_fees = amount * (1 + gross - fee) ** years
        loc = self.locale
        metrics = {
            "without_fees": {"value": without_fees, "text": fmt_money(without_fees, loc)},
            "with_fees": {"value": with_fees, "text": fmt_money(with_fees, loc)},
            "difference": {"value": without_fees - with_fees, "text": fmt_money(without_fees - with_fees, loc)},
            "share_lost": {"value": 1 - with_fees / without_fees, "text": fmt_pct(1 - with_fees / without_fees, loc)},
        }
        inputs = {
            "amount": fmt_money(amount, loc),
            "return": fmt_pct(gross, loc),
            "fee": fmt_pct(fee, loc),
            "years": str(years),
        }
        return self._add(
            {
                "kind": "calc",
                "entity": "fee_drag",
                "name": self.t(("Effet des frais", "Effect of fees")),
                "inputs": inputs,
                "metrics": metrics,
                "assumption": self.t(
                    (
                        f"{inputs['amount']} placés {years} ans à {inputs['return']} par année, avec ou sans "
                        f"{inputs['fee']} de frais annuels : une illustration, pas une prévision.",
                        f"{inputs['amount']} invested for {years} years at {inputs['return']} a year, with or without "
                        f"{inputs['fee']} of yearly fees: an illustration, not a forecast.",
                    )
                ),
                "source": dict(CALC_SOURCE),
            }
        )

    # ------------------------------------------------------------------ portefeuille de l'investisseur
    def client_portfolio(self) -> dict[str, Any]:
        exposures = (self._portfolio or {}).get("exposures") if isinstance(self._portfolio, dict) else None
        if not isinstance(exposures, dict) or not exposures.get("total_value_cad"):
            raise FactError("no confirmed existing portfolio for this investor")
        loc = self.locale
        positions = {p.get("id"): p for p in (self._portfolio or {}).get("positions") or [] if isinstance(p, dict)}
        top = (exposures.get("top_positions") or [{}])[0]
        top_position = positions.get(top.get("id"), {})
        by_currency = exposures.get("by_currency") or {}
        by_market = exposures.get("by_market") or {}
        canada = sum(float(v) for k, v in by_market.items() if str(k).upper() in {"TSX", "TSXV", "TSX-V", "NEO"})
        metrics = {
            "total_value": {
                "value": float(exposures["total_value_cad"]),
                "text": fmt_money(float(exposures["total_value_cad"]), loc),
            },
            "positions": {"value": len(positions), "text": str(len(positions))},
        }
        if top.get("weight") is not None:
            metrics["top_weight"] = {
                "value": float(top["weight"]),
                "text": fmt_pct(float(top["weight"]), loc),
                "label": self.t(("Poids de la plus grosse position", "Weight of the largest position")),
                "entity": top_position.get("ticker") or top_position.get("name"),
            }
        if by_currency:
            metrics["cad_share"] = {
                "value": float(by_currency.get("CAD", 0)),
                "text": fmt_pct(float(by_currency.get("CAD", 0)), loc),
                "label": self.t(("Part en dollars canadiens", "Share in Canadian dollars")),
            }
        if by_market:
            metrics["canada_share"] = {
                "value": canada,
                "text": fmt_pct(canada, loc),
                "label": self.t(("Part cotée au Canada", "Share listed in Canada")),
            }
        bars = [
            {
                "label": str(p.get("ticker") or p.get("name") or p.get("id")),
                "value": float(w.get("weight") or 0),
                "text": fmt_pct(float(w.get("weight") or 0), loc),
            }
            for w in (exposures.get("top_positions") or [])[:3]
            for p in [positions.get(w.get("id"), {})]
        ]
        return self._add(
            {
                "kind": "portfolio",
                "entity": "client_portfolio",
                "name": self.t(("Votre portefeuille existant", "Your existing portfolio")),
                "metrics": metrics,
                "top_positions": bars,
                "flags": list(exposures.get("flags") or []),
                "source": {
                    "id": "client-existing-portfolio",
                    "title": self.t(
                        (
                            "Votre portefeuille existant, confirmé par vous",
                            "Your existing portfolio, as you confirmed it",
                        )
                    ),
                    "resource": self._portfolio_key or "clients/<client_id>/portefeuille-existant.md",
                },
            }
        )

    # ------------------------------------------------------------------ lecture par le code
    def resolve(self, ref: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """``f2`` -> (fait, None); ``f2.max_drawdown`` -> (fait, métrique)."""
        if not isinstance(ref, str) or not re.fullmatch(r"f\d+(\.[a-z_0-9]+)?", ref):
            raise FactError(f"invalid fact reference {ref!r}; use f<n> or f<n>.<metric>")
        fact_id, _, metric = ref.partition(".")
        fact = self.facts.get(fact_id)
        if fact is None:
            raise FactError(f"unknown fact {fact_id}; call a fact tool first")
        if not metric:
            return fact, None
        value = (fact.get("metrics") or {}).get(metric)
        if value is None or "text" not in value:
            raise FactError(f"{fact_id} has no metric {metric!r}; available: {', '.join(fact.get('metrics') or {})}")
        return fact, value

    def series(self, fact_id: str) -> dict[str, Any] | None:
        return self._series.get(fact_id)

    def allowed_numbers(self, fact_ids: Iterable[str]) -> set[str]:
        """Nombres qu'un texte peut citer à partir de ces faits (valeurs formatées et leurs arrondis)."""
        allowed: set[str] = set()
        for fact_id in fact_ids:
            fact = self.facts.get(fact_id)
            if not fact:
                continue
            for item in _walk(fact):
                if isinstance(item, str):
                    allowed |= number_tokens(item)
                elif isinstance(item, int | float) and not isinstance(item, bool):
                    allowed |= _variants(item * 100 if abs(item) < 5 else item)
                    allowed |= _variants(item)
        return allowed

    def public(self, fact: dict[str, Any]) -> dict[str, Any]:
        """Fait renvoyé au modèle : sans la série brute."""
        return {k: v for k, v in fact.items() if k != "series"}


def _walk(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _walk(item)
    else:
        yield value


def _fact_key(fact: dict[str, Any]) -> tuple[Any, ...]:
    return (
        fact.get("kind"),
        fact.get("entity"),
        fact.get("metric"),
        tuple(i.get("entity") for i in fact.get("items") or []),
        str(fact.get("inputs")),
    )


def _nearest_pair(rank: dict[int, int], peak: int, trough: int) -> list[int] | None:
    if trough <= peak:
        return None
    keys = sorted(rank)

    def nearest(index: int) -> int:
        return rank[min(keys, key=lambda k: abs(k - index))]

    a, b = nearest(peak), nearest(trough)
    return [a, b] if a < b else None


def _bounded(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FactError(f"{value!r} is not a number") from exc
    if math.isnan(number) or not low <= number <= high:
        raise FactError(f"{number} is outside [{low}, {high}]")
    return number
