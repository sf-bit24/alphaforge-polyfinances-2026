"""Daily market data for ``alphaforge.market`` (built by ``build_data``, never by an agent).

Inputs, in ``<data dir>/raw/`` (untrusted DATA, each with its manifest.json: url, retrieval time, sha256):
    yfinance_daily/<ticker>.csv   date, close, adj_close, volume, dividends, stock_splits
                                  (``yfinance.download(..., auto_adjust=False, actions=True)``)
    bankofcanada/FXUSDCAD.csv     Bank of Canada Valet, daily USD/CAD (FXUSDCAD)

Outputs, in ``<data dir>/``:
    daily_prices.parquet       date, ticker, close, adj_close, volume, currency
    fx_daily.parquet           date, usdcad, cadusd
    corporate_actions.parquet  ex_date, ticker, action (dividend | split), value, unit
and a ``daily`` block in ``data_version.json`` (data_sha256, built_utc, sha256 of each file, raw manifests).

Conventions, as in the starter dataset: ``close`` is split-adjusted only, ``adj_close`` is also dividend-adjusted,
dividends are per share and split-adjusted (Yahoo), splits are ratios already applied to the prices.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .paths import ALPHAFORGE_DIR, DAILY_PARQUETS

UNIVERSE_FILE = ALPHAFORGE_DIR / "data" / "market" / "universe.yaml"
FX_URL = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/csv?start_date=2017-01-01"


def universe_rows(*, include_proposed: bool = True) -> list[dict[str, Any]]:
    """Assets of ``data/market/universe.yaml``; proposed ones are downloaded too, so the finance side can try them."""
    doc = yaml.safe_load(UNIVERSE_FILE.read_text(encoding="utf-8")) or {}
    return [a for a in doc.get("assets") or [] if include_proposed or not a.get("proposed")]


def download_yfinance_daily(raw: Path, tickers: list[str], *, refresh: bool, now: str | None = None) -> None:
    d = raw / "yfinance_daily"
    d.mkdir(parents=True, exist_ok=True)
    man_path = d / "manifest.json"
    man = json.loads(man_path.read_text()) if man_path.exists() else {}
    todo = [t for t in tickers if refresh or not (d / f"{t}.csv").exists()]
    if not todo:
        return
    import yfinance as yf  # imported lazily: only needed when downloading

    for t in todo:
        print(f"[download] yfinance_daily/{t}")
        df = yf.download(
            t,
            period="max",
            interval="1d",
            auto_adjust=False,
            actions=True,
            progress=False,
            threads=False,
            multi_level_index=False,
        )
        if df is None or df.empty:
            raise RuntimeError(f"yfinance returned no data for {t}")
        df = df.reindex(columns=["Close", "Adj Close", "Volume", "Dividends", "Stock Splits"])
        df.columns = ["close", "adj_close", "volume", "dividends", "stock_splits"]
        df.index.name = "date"
        b = df.to_csv().encode()
        (d / f"{t}.csv").write_bytes(b)
        man[f"{t}.csv"] = {
            "url": f"yfinance.download('{t}', period='max', interval='1d', auto_adjust=False, actions=True)",
            "retrieved_utc": now or dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "sha256": hashlib.sha256(b).hexdigest(),
            "bytes": len(b),
        }
    man_path.write_text(json.dumps(man, indent=1))


def _read_valet(path: Path, series: str) -> pd.DataFrame:
    txt = path.read_text()
    body = txt.split('"OBSERVATIONS"', 1)[1] if '"OBSERVATIONS"' in txt else txt
    df = pd.read_csv(io.StringIO(body.strip()))
    out = pd.DataFrame({"date": pd.to_datetime(df["date"]), "usdcad": pd.to_numeric(df[series], errors="coerce")})
    return out.dropna().sort_values("date").reset_index(drop=True)


def daily_tables(raw: Path, assets: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(prices, fx, corporate actions) from the raw files; assets without a raw file are skipped, and reported."""
    prices, actions, missing = [], [], []
    for a in assets:
        t, cur = str(a["ticker"]), str(a["currency"])
        path = raw / "yfinance_daily" / f"{t}.csv"
        if not path.is_file():
            missing.append(t)
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        df = df.dropna(subset=["close", "adj_close"])
        prices.append(
            pd.DataFrame(
                {
                    "date": df["date"],
                    "ticker": t,
                    "close": df["close"].astype(float),
                    "adj_close": df["adj_close"].astype(float),
                    "volume": df["volume"].fillna(0).astype(float),
                    "currency": cur,
                }
            )
        )
        div = df[df["dividends"].fillna(0) > 0]
        actions.append(
            pd.DataFrame(
                {
                    "ex_date": div["date"],
                    "ticker": t,
                    "action": "dividend",
                    "value": div["dividends"].astype(float),
                    "unit": f"{cur} per share",
                }
            )
        )
        spl = df[df["stock_splits"].fillna(0) > 0]
        actions.append(
            pd.DataFrame(
                {
                    "ex_date": spl["date"],
                    "ticker": t,
                    "action": "split",
                    "value": spl["stock_splits"].astype(float),
                    "unit": "ratio",
                }
            )
        )
    if missing:
        print(f"[daily] no raw daily file for: {', '.join(missing)}")
    px = (
        pd.concat(prices, ignore_index=True)
        if prices
        else pd.DataFrame(columns=["date", "ticker", "close", "adj_close", "volume", "currency"])
    )
    ca = (
        pd.concat(actions, ignore_index=True)
        if actions
        else pd.DataFrame(columns=["ex_date", "ticker", "action", "value", "unit"])
    )
    fx_path = raw / "bankofcanada" / "FXUSDCAD.csv"
    fx = _read_valet(fx_path, "FXUSDCAD") if fx_path.is_file() else pd.DataFrame(columns=["date", "usdcad"])
    fx["cadusd"] = (1.0 / fx["usdcad"]).round(6) if len(fx) else pd.Series(dtype=float)
    px = px.sort_values(["ticker", "date"]).reset_index(drop=True)
    ca = ca.sort_values(["ticker", "ex_date", "action"]).reset_index(drop=True)
    return px, fx, ca


def build_daily(out: Path, raw: Path, assets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Write the three daily parquets and the ``daily`` block of data_version.json; returns that block."""
    px, fx, ca = daily_tables(raw, assets if assets is not None else universe_rows())
    if px.empty or fx.empty:
        raise RuntimeError("daily build: no prices or no FXUSDCAD in raw/ (run build_data without --offline first)")
    out.mkdir(parents=True, exist_ok=True)
    tables = dict(zip(DAILY_PARQUETS, (px, fx, ca), strict=True))
    files = {}
    for name, df in tables.items():
        df.to_parquet(out / name, index=False)
        files[name] = hashlib.sha256((out / name).read_bytes()).hexdigest()
    canon = b"".join(df.to_csv(index=False, float_format="%.8f").encode() for df in tables.values())
    block = {
        "data_sha256": hashlib.sha256(canon).hexdigest()[:16],
        "built_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "last_date": str(px["date"].max().date()),
        "n_tickers": int(px["ticker"].nunique()),
        "files": files,
        "raw_manifests": {
            name: json.loads((raw / name / "manifest.json").read_text())
            for name in ("yfinance_daily", "bankofcanada")
            if (raw / name / "manifest.json").is_file()
        },
    }
    version_path = out / "data_version.json"
    version = json.loads(version_path.read_text()) if version_path.is_file() else {}
    version["daily"] = block
    version_path.write_text(json.dumps(version, indent=2, default=str))
    print(
        f"[daily] {len(px)} rows, {block['n_tickers']} tickers, up to {block['last_date']}, "
        f"version {block['data_sha256']}"
    )
    return block
