"""Portefeuille existant : résolution des titres, prix, conversion USD/CAD, expositions et constats.

Le modèle (A2) ne fait qu'extraire des lignes brutes. Tout le reste est calculé ici, par le code :
- symbole cherché dans l'univers des données de marché (``data/market/universe.yaml``) : variantes ``.TO``,
  préfixes de bourse, nom;
- prix = dernière clôture (``close``) des données de marché (``alphaforge.market`` : parquets quotidiens, ou
  ``prices_daily.csv`` du jeu de départ en repli), ou graphique Yahoo Finance pour un titre hors univers; chaque
  prix cite sa source et sa date;
- conversion USD vers CAD au dernier taux USD/CAD des mêmes données (Banque du Canada, FXUSDCAD);
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

Les notes et les raisons écrites par le code sont dans la langue de la session (``locale``). Les clés des
expositions restent les valeurs brutes des données (secteur, marché), traduites par l'interface.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .. import clock, market
from ..collect.fetchers import Quote
from ..errors import pick

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
_CASH_NAME = re.compile(r"\b(cash|encaisse|liquidit|comptant)", re.I)
_EXPOSURE_GROUPS = (
    ("by_asset_class", "asset_class"),
    ("by_currency", "currency"),
    ("by_market", "market"),
    ("by_sector", "sector"),
)
_TOP_POSITION_COUNT = 5
# Longueur des notes d'une position, à la lecture comme à l'écriture : une note relue est celle écrite.
MAX_NOTES_CHARS = 300
# Clé d'une exposition sans valeur (secteur ou marché absent). Clé brute du contrat : l'interface affiche
# « Non classé » ou « Unclassified », et ``finance/policy/from_profile_view.py`` l'écarte des secteurs.
UNCLASSIFIED = "Unknown"

# Notes et raisons écrites par le code : (français, anglais).
_TEXTS = {
    "currency_assumed_cad": ("devise supposée CAD (non précisée)", "currency assumed to be CAD (not stated)"),
    "unidentified_declared_value": (
        "titre non identifié; valeur fournie par l'investisseur",
        "security not identified; value given by the investor",
    ),
    "not_found_no_value": ("titre introuvable et aucune valeur fournie", "security not found and no value given"),
    "no_price_no_value": ("prix introuvable et aucune valeur fournie", "price not found and no value given"),
    "quantity_missing": ("quantité manquante", "quantity missing"),
    "cash_amount_missing": ("montant de l'encaisse manquant", "cash amount missing"),
    "unsupported_currency": ("devise non prise en charge ({currency})", "unsupported currency ({currency})"),
}

QuoteFetcher = Callable[[str], Quote]


@dataclass
class RawPosition:
    # Ligne telle qu'écrite, sinon symbole et nom; ``None`` pour une ligne ajoutée sans l'un ni l'autre.
    raw: str | None
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
        # Nombre écrit à la française (« 1 000,50 $ ») : espaces insécables U+00A0 et U+202F, espaces ordinaires.
        text = value.replace("\u00a0", "").replace("\u202f", "").replace(" ", "").replace("$", "")
        # Une seule virgule sans point est une virgule décimale; sinon les virgules séparent les milliers.
        text = text.replace(",", ".") if text.count(",") == 1 and "." not in text else text.replace(",", "")
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
        raw=text("raw", 300) or " ".join(filter(None, [text("ticker"), text("name")])) or None,
        ticker=text("ticker", 30),
        name=text("name"),
        quantity=_number(item.get("quantity")),
        market_value=_number(item.get("market_value")),
        currency=currency,
        account_type=normalize_account(item.get("account_type")),
        asset_class=asset_class if asset_class in ASSET_CLASSES else None,
        notes=text("notes", MAX_NOTES_CHARS),
    )


def _class_from_yahoo(instrument_type: str | None) -> str:
    mapping = {"EQUITY": "equity", "ETF": "etf_equity", "MUTUALFUND": "fund", "CRYPTOCURRENCY": "crypto"}
    return mapping.get((instrument_type or "").upper(), "other")


def _market_from_yahoo(exchange: str | None) -> str | None:
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


def _text(key: str, locale: str, **values: str) -> str:
    return pick(locale, *_TEXTS[key]).format(**values)


def _add_note(position: dict[str, Any], key: str, locale: str) -> None:
    """Ajoute une note du code aux notes de la position, sauf si elle y est déjà, dans l'une ou l'autre langue :
    ``portfolio.confirm`` relit les notes écrites par ``portfolio.submit``. Le tout est tronqué comme à la
    relecture : une note coupée qu'on ajoute à nouveau à une note pleine la laisse inchangée."""
    current = position["notes"]
    if current and any(text in current for text in _TEXTS[key]):
        return
    extra = _text(key, locale)
    position["notes"] = (f"{current}; {extra}" if current else extra)[:MAX_NOTES_CHARS]


def _unresolved_position(position_id: str, raw: RawPosition) -> dict[str, Any]:
    return {
        "id": position_id,
        "raw": raw.raw,
        "ticker": None,
        "name": raw.name,
        "asset_class": raw.asset_class or "other",
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


def _is_cash(raw: RawPosition) -> bool:
    return raw.asset_class == "cash" or bool(not raw.ticker and raw.name and _CASH_NAME.search(raw.name))


def _listing_candidates(symbol: str | None, hint: str | None, currency: str | None) -> list[str]:
    """Symboles à demander à Yahoo Finance, dans l'ordre, pour un titre absent de l'univers."""
    if not symbol:
        return []
    is_bare = "." not in symbol and "-" not in symbol
    if hint == "CA" or (currency == "CAD" and is_bare):
        return [f"{symbol}.TO", symbol]
    if is_bare and currency != "USD":
        # Devise inconnue : la cotation américaine d'abord, puis celle de Toronto (ex. XEQT -> XEQT.TO).
        return [symbol, f"{symbol}.TO"]
    return [symbol]


def _yahoo_chart_source(quote: Quote, locale: str) -> dict[str, Any]:
    return {
        "id": f"yahoo-chart-{quote.symbol.lower()}",
        "title": pick(
            locale, f"Yahoo Finance, cours quotidiens de {quote.symbol}", f"Yahoo Finance, {quote.symbol} daily prices"
        ),
        "resource": quote.url,
        "observed_at": quote.last_date,
        "retrieved_at": clock.iso(),
    }


def _market_value_currency(position: dict[str, Any], raw: RawPosition, locale: str) -> str:
    """Devise de la valeur fournie : celle indiquée par l'investisseur, sinon celle de cotation, sinon le CAD.

    La position reçoit cette devise quand elle n'en a pas, et une note quand le CAD est supposé.
    """
    currency = raw.currency or position["currency"]
    if not currency:
        currency = position["currency"] = "CAD"
        _add_note(position, "currency_assumed_cad", locale)
    elif not position["currency"]:
        position["currency"] = currency
    return currency


def _missing_value_reason(position: dict[str, Any], locale: str) -> str:
    if position["price"] is None and position["ticker"] is None:
        return _text("not_found_no_value", locale)
    if position["price"] is None:
        return _text("no_price_no_value", locale)
    return _text("quantity_missing", locale)


class Resolver:
    """Résout des lignes brutes en positions évaluées, avec leurs sources; notes et raisons dans ``locale``."""

    def __init__(self, quote_fetcher: QuoteFetcher | None = None, *, max_remote_quotes: int = 10, locale: str = "fr"):
        self.quote_fetcher = quote_fetcher
        self.locale = locale
        self.max_remote_quotes = max_remote_quotes
        self.remote_calls = 0
        self.fx_rate = market.last_fx()
        self.sources: dict[str, dict[str, Any]] = {}

    def _source(self, entry: dict[str, Any]) -> str:
        self.sources[entry["id"]] = entry
        return entry["resource"]

    def _fx_to_cad(self, currency: str) -> float | None:
        if currency == "CAD":
            return 1.0
        if currency == "USD":
            self._source(
                market.source_entry(
                    "fx_usdcad_daily.csv",
                    pick(
                        self.locale,
                        "Taux de change USD/CAD (Banque du Canada)",
                        "USD/CAD exchange rate (Bank of Canada)",
                    ),
                    observed_at=self.fx_rate.date,
                )
            )
            return self.fx_rate.usdcad
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
                # Une ligne non résolue garde un texte (contrat) : l'id de la position quand la ligne n'en a pas.
                label = raw.raw or position["id"]
                unresolved.append({"raw": label, "reason": reason, "position_id": position["id"]})
        return positions, unresolved

    def _convert_to_cad(self, position: dict[str, Any], local_value: float, currency: str | None) -> str | None:
        """Inscrit la valeur en CAD sur la position; renvoie la raison quand la devise n'est pas prise en charge."""
        rate = self._fx_to_cad(currency or "")
        if rate is None:
            return _text("unsupported_currency", self.locale, currency=str(currency))
        position["value_cad"] = round(local_value * rate, 2)
        position["resolved"] = True
        return None

    def _resolve_cash(self, position: dict[str, Any], raw: RawPosition) -> str | None:
        position.update(asset_class="cash", market="Cash", sector="Cash", currency=raw.currency or "CAD")
        if raw.market_value is None:
            return _text("cash_amount_missing", self.locale)
        return self._convert_to_cad(position, raw.market_value, position["currency"])

    def _fill_from_universe(self, position: dict[str, Any], asset: market.Asset) -> None:
        position.update(
            ticker=asset.ticker,
            name=asset.name,
            asset_class=asset.asset_class,
            sector=asset.sector,
            market=asset.market,
            currency=asset.currency,
        )
        self._source(
            market.source_entry(
                "assets_universe.csv",
                pick(self.locale, "Liste des titres connus du simulateur", "List of securities known to the simulator"),
            )
        )
        last_price = market.last_prices().get(asset.ticker)
        if last_price is not None:
            position.update(price=round(last_price.close, 4), price_date=last_price.date)
            position["price_source"] = self._source(
                market.source_entry(
                    "prices_daily.csv",
                    pick(
                        self.locale,
                        "Cours de clôture quotidiens (Yahoo Finance)",
                        "Daily closing prices (Yahoo Finance)",
                    ),
                    observed_at=last_price.date,
                )
            )

    def _first_priced_quote(self, symbols: list[str]) -> Quote | None:
        for symbol in symbols:
            quote = self._remote_quote(symbol)
            if quote is not None and quote.last_close is not None:
                return quote
        return None

    def _fill_from_quote(self, position: dict[str, Any], raw: RawPosition, quote: Quote) -> None:
        currency = (quote.currency or "").upper() or raw.currency
        position.update(
            ticker=quote.symbol,
            name=raw.name or quote.name,
            asset_class=raw.asset_class or _class_from_yahoo(quote.instrument_type),
            market=_market_from_yahoo(quote.exchange),
            currency=currency,
            price=round(float(quote.last_close), 4),
            price_date=quote.last_date,
        )
        position["price_source"] = self._source(_yahoo_chart_source(quote, self.locale))

    def _identify_security(self, position: dict[str, Any], raw: RawPosition) -> bool:
        """Complète la position d'après l'univers du jeu de départ, sinon d'après une cotation Yahoo Finance.

        Faux quand le titre n'est trouvé ni dans l'un ni dans l'autre.
        """
        asset = market.find_asset(raw.ticker, raw.name, raw.currency)
        if asset is not None:
            self._fill_from_universe(position, asset)
            return True
        symbol, hint = market.normalize_symbol(raw.ticker)
        quote = self._first_priced_quote(_listing_candidates(symbol, hint, raw.currency))
        if quote is not None:
            self._fill_from_quote(position, raw, quote)
            return True
        if symbol:
            position["ticker"] = symbol
        return False

    def _resolve_security(self, position: dict[str, Any], raw: RawPosition) -> str | None:
        """Identifie le titre, puis l'évalue : quantité × prix, sinon la valeur fournie par l'investisseur."""
        is_identified = self._identify_security(position, raw)
        if position["price"] is not None and raw.quantity is not None:
            local_value, currency = raw.quantity * position["price"], position["currency"]
        elif raw.market_value is not None:
            local_value, currency = raw.market_value, _market_value_currency(position, raw, self.locale)
        else:
            return _missing_value_reason(position, self.locale)
        reason = self._convert_to_cad(position, local_value, currency)
        if reason is None and not is_identified:
            _add_note(position, "unidentified_declared_value", self.locale)
        return reason

    def _resolve_one(self, position_id: str, raw: RawPosition) -> tuple[dict[str, Any], str | None]:
        """Position complétée autant que possible, et la raison quand elle reste sans valeur en CAD."""
        position = _unresolved_position(position_id, raw)
        reason = self._resolve_cash(position, raw) if _is_cash(raw) else self._resolve_security(position, raw)
        return position, reason

    def source_list(self) -> list[dict[str, Any]]:
        return list(self.sources.values())


def _shares(totals: dict[str, float], total: float) -> dict[str, float]:
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return {key: round(value / total, 4) for key, value in ordered}


def _add_value(totals: dict[str, float], position: dict[str, Any], attribute: str) -> None:
    label = position.get(attribute) or UNCLASSIFIED
    totals[label] = totals.get(label, 0.0) + position["value_cad"]


def _value_by_group(valued: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    groups: dict[str, dict[str, float]] = {key: {} for key, _ in _EXPOSURE_GROUPS}
    for position in valued:
        for key, attribute in _EXPOSURE_GROUPS:
            _add_value(groups[key], position, attribute)
    return groups


def _top_positions(valued: list[dict[str, Any]], total: float) -> list[dict[str, Any]]:
    ranked = sorted(valued, key=lambda position: (-position["value_cad"], position["id"]))
    return [
        {"id": position["id"], "weight": round(position["value_cad"] / total, 4)}
        for position in ranked[:_TOP_POSITION_COUNT]
    ]


def _has_concentrated_position(valued: list[dict[str, Any]], total: float) -> bool:
    return any(
        position["asset_class"] in SINGLE_LINE
        and position["value_cad"] / total > THRESHOLDS["concentration_single_position"]
        for position in valued
    )


def _has_concentrated_sector(valued: list[dict[str, Any]]) -> bool:
    equities = [position for position in valued if position["asset_class"] == "equity"]
    equity_total = sum(position["value_cad"] for position in equities)
    if equity_total > 0:
        sectors: dict[str, float] = {}
        for position in equities:
            _add_value(sectors, position, "sector")
        return max(sectors.values()) / equity_total > THRESHOLDS["concentration_sector"] and len(equities) > 1
    return False


def _has_home_bias(non_cash: list[dict[str, Any]]) -> bool:
    non_cash_total = sum(position["value_cad"] for position in non_cash)
    if non_cash_total > 0:
        canadian_value = sum(
            position["value_cad"]
            for position in non_cash
            if position.get("market") == "TSX" or position.get("currency") == "CAD"
        )
        return canadian_value / non_cash_total >= THRESHOLDS["home_bias_canada"]
    return False


def _class_value(valued: list[dict[str, Any]], asset_class: str) -> float:
    return sum(position["value_cad"] for position in valued if position["asset_class"] == asset_class)


def _has_few_holdings(non_cash: list[dict[str, Any]]) -> bool:
    return len(non_cash) < THRESHOLDS["few_holdings"] and not any(
        position["asset_class"] in DIVERSIFIED for position in non_cash
    )


def _exposure_flags(valued: list[dict[str, Any]], total: float, unresolved: list[dict[str, Any]]) -> list[str]:
    """Constats du portefeuille, dans l'ordre de la liste en tête de module."""
    flags = []
    if _has_concentrated_position(valued, total):
        flags.append("concentration_single_position")
    if _has_concentrated_sector(valued):
        flags.append("concentration_sector")
    non_cash = [position for position in valued if position["asset_class"] != "cash"]
    if _has_home_bias(non_cash):
        flags.append("home_bias_canada")
    if _class_value(valued, "crypto") / total > THRESHOLDS["crypto_exposure_high"]:
        flags.append("crypto_exposure_high")
    if _class_value(valued, "cash") / total > THRESHOLDS["cash_heavy"]:
        flags.append("cash_heavy")
    if _has_few_holdings(non_cash):
        flags.append("few_holdings")
    if unresolved:
        flags.append("unvalued_positions")
    return flags


def compute_exposures(positions: list[dict[str, Any]], unresolved: list[dict[str, Any]]) -> dict[str, Any]:
    valued = [position for position in positions if position.get("resolved") and position.get("value_cad") is not None]
    total = round(sum(position["value_cad"] for position in valued), 2)
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
    for key, totals in _value_by_group(valued).items():
        exposures[key] = _shares(totals, total)
    exposures["top_positions"] = _top_positions(valued, total)
    exposures["flags"] = _exposure_flags(valued, total, unresolved)
    return exposures


def build_view(
    raws: list[RawPosition], *, status: str, quote_fetcher: QuoteFetcher | None = None, locale: str = "fr"
) -> dict[str, Any]:
    """Vue du portefeuille; ``locale`` est la langue de la session, celle des notes et des raisons du code."""
    resolver = Resolver(quote_fetcher, locale=locale)
    positions, unresolved = resolver.resolve(raws)
    exposures = compute_exposures(positions, unresolved)
    fx_rate = resolver.fx_rate
    return {
        "positions": positions,
        "unresolved": unresolved,
        "exposures": exposures,
        "status": status,
        "sources": resolver.source_list(),
        "fx": {"pair": "USDCAD", "rate": fx_rate.usdcad, "date": fx_rate.date, "source": market.fx_resource()},
    }


def positions_to_raws(positions: list[dict[str, Any]]) -> list[RawPosition]:
    """Positions corrigées par l'investisseur vers des lignes brutes (prix et valeurs recalculés par le code).

    Une ligne sans symbole, sans nom et sans valeur déclarée (ligne ajoutée puis laissée vide) est ignorée."""
    raws = []
    for item in positions:
        if not isinstance(item, dict):
            continue
        raw = raw_from_dict(item)
        if raw.ticker or raw.name or raw.market_value is not None:
            raws.append(raw)
    return raws
