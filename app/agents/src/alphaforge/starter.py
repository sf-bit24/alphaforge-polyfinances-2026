"""Jeu de départ des organisateurs (``data/starter``), lu avec la bibliothèque standard.

Fichiers copiés tels quels depuis ``alphaforge_starter`` (fenêtre 2021-11-12 au 2026-11-12, extraction du
2026-11-13); voir ``data/starter/README.md`` et ``sources_metadata.csv`` pour les sources et les limites.
Usage libre dans le cadre du datathon.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data" / "starter"


@dataclass(frozen=True)
class Asset:
    asset_id: str
    ticker: str
    name: str
    asset_class: str
    market: str
    currency: str
    sector: str


@dataclass(frozen=True)
class LastPrice:
    ticker: str
    date: str
    close: float
    adj_close: float
    currency: str


@dataclass(frozen=True)
class FxRate:
    date: str
    usdcad: float
    cadusd: float


def _rows(name: str) -> list[dict[str, str]]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=1)
def universe() -> dict[str, Asset]:
    return {
        row["ticker"]: Asset(
            asset_id=row["asset_id"],
            ticker=row["ticker"],
            name=row["name"],
            asset_class=row["asset_class"],
            market=row["market"],
            currency=row["currency"],
            sector=row["sector"],
        )
        for row in _rows("assets_universe.csv")
    }


@lru_cache(maxsize=1)
def last_prices() -> dict[str, LastPrice]:
    """Dernière clôture de chaque titre (``close``, ajusté des fractionnements seulement)."""
    latest: dict[str, LastPrice] = {}
    with (DATA_DIR / "prices_daily.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ticker = row["ticker"]
            current = latest.get(ticker)
            if current is None or row["date"] >= current.date:
                latest[ticker] = LastPrice(
                    ticker=ticker,
                    date=row["date"],
                    close=float(row["close"]),
                    adj_close=float(row["adj_close"]),
                    currency=row["currency"],
                )
    return latest


@lru_cache(maxsize=1)
def last_fx() -> FxRate:
    rows = _rows("fx_usdcad_daily.csv")
    row = max(rows, key=lambda r: r["date"])
    return FxRate(date=row["date"], usdcad=float(row["usdcad"]), cadusd=float(row["cadusd"]))


@lru_cache(maxsize=1)
def sources_metadata() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in _rows("sources_metadata.csv"):
        out.setdefault(row["file"], row)
    return out


def retrieved_on(file_name: str) -> str:
    return sources_metadata().get(file_name, {}).get("retrieved_on", "2026-11-13")


@lru_cache(maxsize=1)
def macro_series() -> dict[str, dict[str, str]]:
    """Séries macro du jeu de départ : libellé, unité, fréquence et source."""
    out: dict[str, dict[str, str]] = {}
    with (DATA_DIR / "macro_rates.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            out.setdefault(
                row["series_id"],
                {"label": row["label"], "unit": row["unit"], "frequency": row["frequency"], "source": row["source"]},
            )
    return out


def source_entry(file_name: str, title: str, *, observed_at: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": "starter-" + file_name.split(".")[0].replace("_", "-"),
        "title": title,
        "resource": f"starter:{file_name}",
        "retrieved_at": retrieved_on(file_name),
    }
    if observed_at:
        entry["observed_at"] = observed_at
    return entry


# ---------------------------------------------------------------------- résolution des symboles
_PREFIXES = re.compile(r"^(TSX|TSE|TSXV|NYSE|NASDAQ|NYSEARCA|ARCA|AMEX|BATS|CBOE|NEO)\s*[:\-]\s*", re.I)
_CA_SUFFIXES = re.compile(r"(\.TO|\.TSX|:CA|:CN|\s+CN|\s+CA|-CT|\.CA)$", re.I)
_US_SUFFIXES = re.compile(r"(:US|\s+US|\.US)$", re.I)
_CRYPTO = {
    "BTC": "BTC-USD",
    "BTCUSD": "BTC-USD",
    "BTC/USD": "BTC-USD",
    "BTC-CAD": "BTC-USD",
    "XBT": "BTC-USD",
    "BITCOIN": "BTC-USD",
    "ETH": "ETH-USD",
    "ETHUSD": "ETH-USD",
    "ETH/USD": "ETH-USD",
    "ETHER": "ETH-USD",
    "ETHEREUM": "ETH-USD",
}
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,14}$")


def normalize_symbol(raw: str | None) -> tuple[str | None, str | None]:
    """Nettoie un symbole saisi librement; renvoie (symbole, indice de marché ``CA``/``US``/``None``)."""
    if not raw:
        return None, None
    text = raw.strip().upper().replace(" ", " ")
    if text in _CRYPTO:
        return _CRYPTO[text], None
    hint = None
    match = _PREFIXES.match(text)
    if match:
        exchange = match.group(1).upper()
        hint = "CA" if exchange in {"TSX", "TSE", "TSXV", "NEO"} else "US"
        text = text[match.end() :]
    if _CA_SUFFIXES.search(text):
        hint = "CA"
        text = _CA_SUFFIXES.sub("", text)
    elif _US_SUFFIXES.search(text):
        hint = "US"
        text = _US_SUFFIXES.sub("", text)
    text = text.strip().replace(" ", "")
    if text in _CRYPTO:
        return _CRYPTO[text], None
    if not SYMBOL_PATTERN.match(text):
        return None, hint
    return text, hint


def _norm_name(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", value.lower()).strip()


def find_asset(ticker: str | None, name: str | None = None, currency: str | None = None) -> Asset | None:
    """Cherche un titre de l'univers par symbole (variantes ``.TO``, préfixes de bourse) puis par nom."""
    assets = universe()
    symbol, hint = normalize_symbol(ticker)
    if symbol:
        if symbol in assets:
            return assets[symbol]
        candidates = []
        if hint != "US":
            candidates.append(f"{symbol}.TO")
        if hint == "CA" and symbol.endswith(".TO"):
            candidates.append(symbol)
        if hint != "CA":
            candidates.append(symbol.split(".")[0])
        for candidate in candidates:
            asset = assets.get(candidate)
            if asset and (currency is None or asset.currency == currency.upper() or hint is None):
                return asset
    if name:
        wanted = _norm_name(name)
        if len(wanted) >= 4:
            for asset in assets.values():
                known = _norm_name(asset.name)
                if wanted == known or (len(wanted) >= 6 and (wanted in known or known in wanted)):
                    return asset
    return None
