"""Données de marché : une seule interface pour les prix, le change et les opérations sur titres.

Remplace les lectures directes du jeu de départ (``alphaforge.starter``) par le code de l'application. Deux sources :

- ``market`` : les parquets quotidiens de ``finance.backtest.build_data`` (``daily_prices.parquet``,
  ``fx_daily.parquet``, ``corporate_actions.parquet``), dans ``finance.backtest.paths.data_dir()``
  (``ALPHAFORGE_BT_DATA``; le runtime ``portfolio`` les télécharge sous ``runtime/data/long/``);
- ``starter`` : le jeu de départ des organisateurs, en repli quand ces parquets sont absents (CI, développement local,
  runtimes qui ne téléchargent pas les données longues), ou quand ``ALPHAFORGE_MARKET_SOURCE=starter``.

L'univers vient toujours de ``data/market/universe.yaml`` (tenu par le volet finance) : les actifs ``proposed`` n'y
entrent qu'avec ``ALPHAFORGE_MARKET_INCLUDE_PROPOSED=1``. Mêmes garanties que le jeu de départ : ``daily`` et les
fonctions « à une date » ne lisent jamais au-delà de ``as_of``. pandas et pyarrow ne sont importés que pour lire les
parquets : ce module reste importable avec la seule bibliothèque standard.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from . import starter
from .finance.backtest.paths import DAILY_PARQUETS, daily_data_available, data_dir
from .starter import Asset, DailyRow, FxRate, LastPrice, normalize_symbol

__all__ = [
    "Asset",
    "DailyRow",
    "FxRate",
    "LastPrice",
    "close_on_or_before",
    "daily",
    "data_version",
    "dividend_yield_ttm",
    "dividends",
    "find_asset",
    "fx_resource",
    "last_fx",
    "last_prices",
    "median_dollar_volume_cad",
    "normalize_symbol",
    "source",
    "source_entry",
    "universe",
    "usdcad_on_or_before",
]

logger = logging.getLogger("alphaforge.market")

UNIVERSE_FILE = Path(__file__).parent / "data" / "market" / "universe.yaml"
_MARKET_FILES = {
    "prices_daily.csv": ("daily_prices.parquet", "Données de marché, daily_prices.parquet (Yahoo Finance)"),
    "fx_usdcad_daily.csv": ("fx_daily.parquet", "Données de marché, fx_daily.parquet (Banque du Canada, FXUSDCAD)"),
    "corporate_actions.csv": ("corporate_actions.parquet", "Données de marché, corporate_actions.parquet (Yahoo)"),
    "assets_universe.csv": ("universe.yaml", "Univers des données de marché, data/market/universe.yaml"),
}
_warned: set[str] = set()


# ----------------------------------------------------------------------------- source
def source() -> str:
    """``market`` si les parquets quotidiens sont lisibles, sinon ``starter`` (repli signalé une fois)."""
    if os.environ.get("ALPHAFORGE_MARKET_SOURCE", "").strip().lower() != "starter" and daily_data_available():
        return "market"
    where = str(data_dir())
    if where not in _warned:
        _warned.add(where)
        logger.info("market: parquets quotidiens absents de %s, repli sur le jeu de départ", where)
    return "starter"


def _dir() -> Path:
    return data_dir()


@lru_cache(maxsize=4)
def _version(where: str) -> dict[str, Any]:
    path = Path(where) / "data_version.json"
    if not path.is_file():
        return {}
    try:
        return (json.loads(path.read_text(encoding="utf-8")) or {}).get("daily") or {}
    except ValueError:
        return {}


def data_version() -> dict[str, Any]:
    """Source et version des données de marché lues, à citer dans une décision."""
    if source() == "starter":
        return {
            "source": "starter",
            "version": "starter-2026-11-13",
            "retrieved_on": starter.retrieved_on("prices_daily.csv"),
        }
    v = _version(str(_dir()))
    return {
        "source": "market",
        "version": v.get("data_sha256"),
        "built_utc": v.get("built_utc"),
        "files": v.get("files"),
    }


# ----------------------------------------------------------------------------- univers
@lru_cache(maxsize=2)
def _universe(include_proposed: bool) -> dict[str, Asset]:
    doc = yaml.safe_load(UNIVERSE_FILE.read_text(encoding="utf-8")) or {}
    out: dict[str, Asset] = {}
    for row in doc.get("assets") or []:
        if row.get("proposed") and not include_proposed:
            continue
        out[str(row["ticker"])] = Asset(
            asset_id=str(row["asset_id"]),
            ticker=str(row["ticker"]),
            name=str(row["name"]),
            asset_class=str(row["asset_class"]),
            market=str(row["market"]),
            currency=str(row["currency"]),
            sector=str(row["sector"]),
        )
    return out


def universe() -> dict[str, Asset]:
    return _universe(os.environ.get("ALPHAFORGE_MARKET_INCLUDE_PROPOSED") == "1")


def find_asset(ticker: str | None, name: str | None = None, currency: str | None = None) -> Asset | None:
    """Cherche un titre de l'univers par symbole (variantes ``.TO``, préfixes de bourse) puis par nom."""
    return starter.find_asset(ticker, name, currency, assets=universe())


# ----------------------------------------------------------------------------- parquets
@lru_cache(maxsize=2)
def _parquet_daily(where: str) -> dict[str, tuple[DailyRow, ...]]:
    import pandas as pd

    df = pd.read_parquet(
        Path(where) / "daily_prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"]
    )
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    out: dict[str, list[DailyRow]] = {}
    for d, t, c, a, v in df.itertuples(index=False, name=None):
        if pd.isna(c) or pd.isna(a):
            continue
        out.setdefault(str(t), []).append(DailyRow(d, float(c), float(a), 0.0 if pd.isna(v) else float(v)))
    return {t: tuple(sorted(rows, key=lambda r: r.date)) for t, rows in out.items()}


@lru_cache(maxsize=2)
def _parquet_actions(where: str) -> tuple[tuple[str, str, str, float], ...]:
    import pandas as pd

    df = pd.read_parquet(Path(where) / "corporate_actions.parquet", columns=["ex_date", "ticker", "action", "value"])
    df["ex_date"] = pd.to_datetime(df["ex_date"]).dt.strftime("%Y-%m-%d")
    return tuple((d, str(t), str(a), float(v)) for d, t, a, v in df.itertuples(index=False, name=None))


@lru_cache(maxsize=2)
def _parquet_fx(where: str) -> tuple[tuple[str, float], ...]:
    import pandas as pd

    df = pd.read_parquet(Path(where) / "fx_daily.parquet", columns=["date", "usdcad"]).dropna()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return tuple(sorted((d, float(v)) for d, v in df.itertuples(index=False, name=None)))


def _daily_map() -> dict[str, tuple[DailyRow, ...]]:
    return _parquet_daily(str(_dir())) if source() == "market" else starter._daily()


def _actions() -> tuple[tuple[str, str, str, float], ...]:
    if source() == "market":
        return _parquet_actions(str(_dir()))
    return tuple((r["ex_date"], r["ticker"], r["action"], float(r["value"])) for r in starter._corporate_actions())


def _fx_series() -> tuple[tuple[str, float], ...]:
    return _parquet_fx(str(_dir())) if source() == "market" else starter._fx_series()


# ----------------------------------------------------------------------------- dernières valeurs
def last_prices() -> dict[str, LastPrice]:
    """Dernière clôture de chaque titre (``close``, ajusté des fractionnements seulement)."""
    if source() == "starter":
        return starter.last_prices()
    assets = universe()
    out: dict[str, LastPrice] = {}
    for ticker, rows in _daily_map().items():
        if rows and ticker in assets:
            r = rows[-1]
            out[ticker] = LastPrice(ticker, r.date, r.close, r.adj_close, assets[ticker].currency)
    return out


def last_fx() -> FxRate:
    if source() == "starter":
        return starter.last_fx()
    d, v = _fx_series()[-1]
    return FxRate(date=d, usdcad=v, cadusd=round(1.0 / v, 6))


def fx_resource() -> str:
    return "market:fx_daily.parquet" if source() == "market" else "starter:fx_usdcad_daily.csv"


def source_entry(file_name: str, title: str, *, observed_at: str | None = None) -> dict[str, Any]:
    """Entrée ``sources`` pour un fichier du jeu de départ, ou pour son équivalent de la couche de marché."""
    if source() == "starter" or file_name not in _MARKET_FILES:
        return starter.source_entry(file_name, title, observed_at=observed_at)
    name, market_title = _MARKET_FILES[file_name]
    built = data_version().get("built_utc")
    entry: dict[str, Any] = {
        "id": "market-" + name.split(".")[0].replace("_", "-"),
        "title": market_title,
        "resource": f"market:{name}",
        "retrieved_at": built,
    }
    if observed_at:
        entry["observed_at"] = observed_at
    return entry


# ----------------------------------------------------------------------------- séries à une date (point-in-time)
def daily(ticker: str, as_of: str | None = None, start: str | None = None) -> tuple[DailyRow, ...]:
    """Lignes quotidiennes du titre, de ``start`` (inclus) à ``as_of`` (inclus), dates ISO."""
    rows = _daily_map().get(ticker, ())
    return tuple(r for r in rows if (start is None or r.date >= start) and (as_of is None or r.date <= as_of))


def close_on_or_before(ticker: str, as_of: str) -> DailyRow | None:
    rows = daily(ticker, as_of)
    return rows[-1] if rows else None


def dividends(ticker: str, start: str, end: str) -> list[tuple[str, float]]:
    """Dividendes par action (ajustés des fractionnements) avec ``start < ex_date <= end``; fractionnements ignorés
    (déjà appliqués aux prix)."""
    return [(d, v) for d, t, a, v in _actions() if t == ticker and a == "dividend" and start < d <= end]


def dividend_yield_ttm(ticker: str, as_of: str) -> float | None:
    """Dividendes avec ex-date dans ]as_of − 365 j, as_of] / clôture à as_of; None si aucun prix."""
    px = close_on_or_before(ticker, as_of)
    if px is None or px.close <= 0:
        return None
    total = sum(v for _, v in dividends(ticker, starter._minus_days(as_of, 365), as_of))
    return total / px.close


def usdcad_on_or_before(iso: str) -> float | None:
    """Dernier taux USD/CAD connu à une date <= ``iso`` (les jours fériés canadiens n'ont pas de ligne)."""
    best = None
    for d, v in _fx_series():
        if d > iso:
            break
        best = v
    return best


def median_dollar_volume_cad(ticker: str, as_of: str, days: int = 63) -> float | None:
    """Valeur médiane échangée par jour (``close × volume``) sur les ``days`` dernières séances, en CAD."""
    rows = daily(ticker, as_of)[-days:]
    asset = universe().get(ticker)
    if not rows or asset is None:
        return None
    vals = []
    for r in rows:
        fx = 1.0 if asset.currency == "CAD" else usdcad_on_or_before(r.date)
        if fx is None:
            continue
        vals.append(r.close * r.volume * fx)
    if not vals:
        return None
    vals.sort()
    n = len(vals)
    return vals[n // 2] if n % 2 else 0.5 * (vals[n // 2 - 1] + vals[n // 2])


def reset_cache() -> None:
    """Oublie les parquets et l'univers lus (tests, ou données remplacées pendant l'exécution)."""
    for fn in (_parquet_daily, _parquet_actions, _parquet_fx, _version, _universe):
        fn.cache_clear()
    _warned.clear()


# Ne lire que les parquets attendus : tout autre fichier du répertoire est ignoré.
assert set(DAILY_PARQUETS) == {v[0] for k, v in _MARKET_FILES.items() if k != "assets_universe.csv"}
