"""Portefeuille existant : résolution des titres, prix, conversion USD/CAD, expositions et constats.

Le modèle (A2) ne fait qu'extraire des lignes brutes. Tout le reste est calculé ici, par le code :
- symbole cherché dans ``assets_universe.csv`` (variantes ``.TO``, préfixes de bourse, nom);
- prix = dernière clôture (``close``) de ``prices_daily.csv``, ou graphique Yahoo Finance pour un titre hors
  univers; chaque prix cite sa source et sa date;
- conversion USD vers CAD au dernier taux de ``fx_usdcad_daily.csv`` (Banque du Canada, via le jeu de départ);
- expositions en parts de 0 à 1 de ``total_value_cad``, sur les positions évaluées seulement.

Constats (seuils à relire par le volet finance de l'équipe larpathon) :
- ``concentration_single_position`` : un titre individuel (action, obligation, cryptoactif ou autre, hors FNB,
  fonds et encaisse) dépasse 20 % du total;
- ``concentration_sector`` : un secteur dépasse 40 % des actions individuelles;
- ``home_bias_canada`` : au moins 60 % du total hors encaisse est coté au Canada ou libellé en CAD;
- ``crypto_exposure_high`` : plus de 10 % en cryptoactifs;
- ``cash_heavy`` : plus de 30 % en encaisse;
- ``few_holdings`` : moins de cinq positions évaluées hors encaisse et aucun FNB ni fonds;
- ``unvalued_positions`` : au moins une ligne n'a pas pu être évaluée.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .. import clock, starter
from ..collect.fetchers import Quote

ASSET_CLASSES = ("equity", "etf_equity", "etf_bond", "etf_commodity", "bond", "cash", "crypto", "fund", "other")
ACCOUNT_TYPES = ("tfsa", "rrsp", "resp", "rrif", "non_registered", "unknown")
DIVERSIFIED = ("etf_equity", "etf_bond", "etf_commodity", "fund")
SINGLE_LINE = ("equity", "bond", "crypto", "other")
SUPPORTED_CURRENCIES = ("CAD", "USD")

THRESHOLDS = {
    "concentration_single_position": 0.20,
    "concentration_sector": 0.40,
    "home_bias_canada": 0.60,
    "crypto_exposure_high": 0.10,
    "cash_heavy": 0.30,
    "few_holdings": 5,
}

_ACCOUNT_ALIASES = {
    "celi": "tfsa",
    "tfsa": "tfsa",
    "reer": "rrsp",
    "rrsp": "rrsp",
    "reee": "resp",
    "resp": "resp",
    "ferr": "rrif",
    "rrif": "rrif",
    "non_registered": "non_registered",
    "non-registered": "non_registered",
    "non enregistré": "non_registered",
    "non-enregistré": "non_registered",
    "cash account": "non_registered",
    "margin": "non_registered",
    "unknown": "unknown",
}

QuoteFetcher = Callable[[str], Quote]


@dataclass
class RawPosition:
    raw: str
    ticker: str | None = None
    name: str | None = None
    quantity: float | None = None
    market_value: float | None = None
    currency: str | None = None
    account_type: str | None = None
    asset_class: str | None = None
    notes: str | None = None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.replace(" ", "").replace(" ", "").replace(" ", "").replace("$", "")
        if text.count(",") == 1 and "." not in text:
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
        try:
            return float(text)
        except ValueError:
            return None
    return None


def normalize_account(value: Any) -> str | None:
    if not value or not isinstance(value, str):
        return None
    key = value.strip().lower()
    return _ACCOUNT_ALIASES.get(key, "unknown" if key else None)


def raw_from_dict(item: dict[str, Any]) -> RawPosition:
    """Ligne brute à partir d'un dictionnaire (outil d'A2 ou position corrigée par l'investisseur)."""

    def text(name: str, limit: int = 200) -> str | None:
        value = item.get(name)
        if value is None:
            return None
        value = str(value).strip()
        return value[:limit] or None

    currency = (text("currency", 8) or "").upper() or None
    asset_class = text("asset_class", 20) or text("asset_class_hint", 20)
    return RawPosition(
        raw=text("raw", 300) or " ".join(filter(None, [text("ticker"), text("name")])) or "?",
        ticker=text("ticker", 30),
        name=text("name"),
        quantity=_number(item.get("quantity")),
        market_value=_number(item.get("market_value")),
        currency=currency,
        account_type=normalize_account(item.get("account_type")),
        asset_class=asset_class if asset_class in ASSET_CLASSES else None,
        notes=text("notes", 300),
    )


def _class_from_yahoo(instrument_type: str | None) -> str:
    mapping = {"EQUITY": "equity", "ETF": "etf_equity", "MUTUALFUND": "fund", "CRYPTOCURRENCY": "crypto"}
    return mapping.get((instrument_type or "").upper(), "other")


def _market_from_yahoo(exchange: str | None, currency: str | None) -> str | None:
    if not exchange:
        return None
    upper = exchange.upper()
    if "TORONTO" in upper or upper in {"TOR", "TSX"}:
        return "TSX"
    if "NASDAQ" in upper or upper in {"NMS", "NGM", "NCM"}:
        return "NASDAQ"
    if "NYSE" in upper or upper in {"NYQ", "PCX"}:
        return "NYSE"
    if "CCC" in upper or "CRYPTO" in upper:
        return "Crypto (24/7)"
    return exchange


class Resolver:
    """Résout des lignes brutes en positions évaluées, avec leurs sources."""

    def __init__(self, quote_fetcher: QuoteFetcher | None = None, *, max_remote_quotes: int = 10):
        self.quote_fetcher = quote_fetcher
        self.max_remote_quotes = max_remote_quotes
        self.remote_calls = 0
        self.fx = starter.last_fx()
        self.sources: dict[str, dict[str, Any]] = {}

    def _source(self, entry: dict[str, Any]) -> str:
        self.sources[entry["id"]] = entry
        return entry["resource"]

    def _fx_to_cad(self, currency: str) -> float | None:
        if currency == "CAD":
            return 1.0
        if currency == "USD":
            self._source(
                starter.source_entry(
                    "fx_usdcad_daily.csv",
                    "Jeu de départ, fx_usdcad_daily.csv (Banque du Canada, série FXUSDCAD)",
                    observed_at=self.fx.date,
                )
            )
            return self.fx.usdcad
        return None

    def _remote_quote(self, symbol: str) -> Quote | None:
        if self.quote_fetcher is None or self.remote_calls >= self.max_remote_quotes:
            return None
        self.remote_calls += 1
        try:
            return self.quote_fetcher(symbol)
        except Exception:
            return None

    def resolve(self, raws: list[RawPosition]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        positions: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for index, raw in enumerate(raws, start=1):
            position, reason = self._resolve_one(f"p{index}", raw)
            positions.append(position)
            if reason:
                unresolved.append({"raw": raw.raw, "reason": reason, "position_id": position["id"]})
        return positions, unresolved

    def _resolve_one(self, position_id: str, raw: RawPosition) -> tuple[dict[str, Any], str | None]:
        asset_class = raw.asset_class
        position: dict[str, Any] = {
            "id": position_id,
            "raw": raw.raw,
            "ticker": None,
            "name": raw.name,
            "asset_class": asset_class or "other",
            "sector": None,
            "market": None,
            "currency": raw.currency,
            "quantity": raw.quantity,
            "market_value": raw.market_value,
            "account_type": raw.account_type,
            "price": None,
            "price_date": None,
            "price_source": None,
            "value_cad": None,
            "resolved": False,
            "notes": raw.notes,
        }
        is_cash = asset_class == "cash" or (
            not raw.ticker and raw.name and re.search(r"\b(cash|encaisse|liquidit|comptant)", raw.name, re.I)
        )
        if is_cash:
            position.update(asset_class="cash", market="Cash", sector="Cash", currency=raw.currency or "CAD")
            if raw.market_value is None:
                return position, "montant de l'encaisse manquant"
            rate = self._fx_to_cad(position["currency"])
            if rate is None:
                return position, f"devise non prise en charge ({position['currency']})"
            position["value_cad"] = round(raw.market_value * rate, 2)
            position["resolved"] = True
            return position, None

        asset = starter.find_asset(raw.ticker, raw.name, raw.currency)
        quote: Quote | None = None
        if asset is not None:
            position.update(
                ticker=asset.ticker,
                name=asset.name,
                asset_class=asset.asset_class,
                sector=asset.sector,
                market=asset.market,
                currency=asset.currency,
            )
            self._source(starter.source_entry("assets_universe.csv", "Jeu de départ, assets_universe.csv"))
            last = starter.last_prices().get(asset.ticker)
            if last is not None:
                position.update(price=round(last.close, 4), price_date=last.date)
                position["price_source"] = self._source(
                    starter.source_entry(
                        "prices_daily.csv", "Jeu de départ, prices_daily.csv (Yahoo Finance)", observed_at=last.date
                    )
                )
        else:
            symbol, hint = starter.normalize_symbol(raw.ticker)
            candidates = []
            if symbol:
                bare = "." not in symbol and "-" not in symbol
                if hint == "CA" or (raw.currency == "CAD" and bare):
                    candidates = [f"{symbol}.TO", symbol]
                elif bare and raw.currency != "USD":
                    # Devise inconnue : la cotation américaine d'abord, puis celle de Toronto (ex. XEQT -> XEQT.TO).
                    candidates = [symbol, f"{symbol}.TO"]
                else:
                    candidates = [symbol]
            for candidate in candidates:
                quote = self._remote_quote(candidate)
                if quote is not None and quote.last_close is not None:
                    break
                quote = None
            if quote is not None:
                currency = (quote.currency or "").upper() or raw.currency
                position.update(
                    ticker=quote.symbol,
                    name=raw.name or quote.name,
                    asset_class=asset_class or _class_from_yahoo(quote.instrument_type),
                    market=_market_from_yahoo(quote.exchange, currency),
                    currency=currency,
                    price=round(float(quote.last_close), 4),
                    price_date=quote.last_date,
                )
                position["price_source"] = self._source(
                    {
                        "id": f"yahoo-chart-{quote.symbol.lower()}",
                        "title": f"Yahoo Finance, graphique quotidien de {quote.symbol}",
                        "resource": quote.url,
                        "observed_at": quote.last_date,
                        "retrieved_at": clock.iso(),
                    }
                )
            elif symbol:
                position["ticker"] = symbol

        if position["price"] is not None and raw.quantity is not None:
            local_value = raw.quantity * position["price"]
            currency = position["currency"]
        elif raw.market_value is not None:
            # La valeur fournie est dans la devise indiquée par l'investisseur, sinon dans celle de cotation.
            local_value = raw.market_value
            currency = raw.currency or position["currency"]
            if not currency:
                currency = position["currency"] = "CAD"
                position["notes"] = _join_notes(position["notes"], "devise supposée CAD (non précisée)")
            elif not position["currency"]:
                position["currency"] = currency
        else:
            if position["price"] is None and position["ticker"] is None:
                return position, "titre introuvable et aucune valeur fournie"
            if position["price"] is None:
                return position, "prix introuvable et aucune valeur fournie"
            return position, "quantité manquante"
        rate = self._fx_to_cad(currency or "")
        if rate is None:
            return position, f"devise non prise en charge ({currency})"
        position["value_cad"] = round(local_value * rate, 2)
        position["resolved"] = True
        if asset is None and quote is None:
            position["notes"] = _join_notes(position["notes"], "titre non identifié; valeur fournie par l'investisseur")
        return position, None

    def source_list(self) -> list[dict[str, Any]]:
        return list(self.sources.values())


def _join_notes(current: str | None, extra: str) -> str:
    return f"{current}; {extra}" if current else extra


def _shares(totals: dict[str, float], total: float) -> dict[str, float]:
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return {key: round(value / total, 4) for key, value in ordered}


def compute_exposures(positions: list[dict[str, Any]], unresolved: list[dict[str, Any]]) -> dict[str, Any]:
    valued = [p for p in positions if p.get("resolved") and p.get("value_cad") is not None]
    total = round(sum(p["value_cad"] for p in valued), 2)
    exposures: dict[str, Any] = {
        "total_value_cad": total,
        "by_asset_class": {},
        "by_currency": {},
        "by_market": {},
        "by_sector": {},
        "top_positions": [],
        "flags": [],
    }
    if total <= 0:
        if unresolved:
            exposures["flags"] = ["unvalued_positions"]
        return exposures
    groups: dict[str, dict[str, float]] = {"by_asset_class": {}, "by_currency": {}, "by_market": {}, "by_sector": {}}
    for p in valued:
        for key, attr in (
            ("by_asset_class", "asset_class"),
            ("by_currency", "currency"),
            ("by_market", "market"),
            ("by_sector", "sector"),
        ):
            label = p.get(attr) or "Unknown"
            groups[key][label] = groups[key].get(label, 0.0) + p["value_cad"]
    for key, totals in groups.items():
        exposures[key] = _shares(totals, total)
    ranked = sorted(valued, key=lambda p: (-p["value_cad"], p["id"]))
    exposures["top_positions"] = [{"id": p["id"], "weight": round(p["value_cad"] / total, 4)} for p in ranked[:5]]

    flags = []
    if any(
        p["asset_class"] in SINGLE_LINE and p["value_cad"] / total > THRESHOLDS["concentration_single_position"]
        for p in valued
    ):
        flags.append("concentration_single_position")
    equities = [p for p in valued if p["asset_class"] == "equity"]
    equity_total = sum(p["value_cad"] for p in equities)
    if equity_total > 0:
        sectors: dict[str, float] = {}
        for p in equities:
            sectors[p.get("sector") or "Unknown"] = sectors.get(p.get("sector") or "Unknown", 0.0) + p["value_cad"]
        if max(sectors.values()) / equity_total > THRESHOLDS["concentration_sector"] and len(equities) > 1:
            flags.append("concentration_sector")
    non_cash = [p for p in valued if p["asset_class"] != "cash"]
    non_cash_total = sum(p["value_cad"] for p in non_cash)
    if non_cash_total > 0:
        canada = sum(p["value_cad"] for p in non_cash if p.get("market") == "TSX" or p.get("currency") == "CAD")
        if canada / non_cash_total >= THRESHOLDS["home_bias_canada"]:
            flags.append("home_bias_canada")
    crypto = sum(p["value_cad"] for p in valued if p["asset_class"] == "crypto")
    if crypto / total > THRESHOLDS["crypto_exposure_high"]:
        flags.append("crypto_exposure_high")
    cash = sum(p["value_cad"] for p in valued if p["asset_class"] == "cash")
    if cash / total > THRESHOLDS["cash_heavy"]:
        flags.append("cash_heavy")
    if len(non_cash) < THRESHOLDS["few_holdings"] and not any(p["asset_class"] in DIVERSIFIED for p in non_cash):
        flags.append("few_holdings")
    if unresolved:
        flags.append("unvalued_positions")
    exposures["flags"] = flags
    return exposures


def build_view(raws: list[RawPosition], *, status: str, quote_fetcher: QuoteFetcher | None = None) -> dict[str, Any]:
    resolver = Resolver(quote_fetcher)
    positions, unresolved = resolver.resolve(raws)
    exposures = compute_exposures(positions, unresolved)
    fx = resolver.fx
    return {
        "positions": positions,
        "unresolved": unresolved,
        "exposures": exposures,
        "status": status,
        "sources": resolver.source_list(),
        "fx": {"pair": "USDCAD", "rate": fx.usdcad, "date": fx.date, "source": "starter:fx_usdcad_daily.csv"},
    }


def positions_to_raws(positions: list[dict[str, Any]]) -> list[RawPosition]:
    """Positions corrigées par l'investisseur vers des lignes brutes (prix et valeurs recalculés par le code)."""
    raws = []
    for item in positions:
        if not isinstance(item, dict):
            continue
        raw = raw_from_dict(item)
        if raw.ticker or raw.name or raw.market_value is not None:
            raws.append(raw)
    return raws
