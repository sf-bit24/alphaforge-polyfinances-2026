"""Loading the processed monthly dataset (built by ``python -m alphaforge.finance.backtest.build_data``)."""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from .paths import data_dir

DATA_DIR = data_dir()  # fixed at first import, like ALPHAFORGE_BT_DATA was before

# look-through: which KF industry column measures which exposure tag inside US_MKT
LOOKTHROUGH_TAGS = {
    "tech": "US_IND_BUSEQ",
    "energy": "US_IND_ENRGY",
    "financials": "US_IND_MONEY",
    "utilities": "US_IND_UTILS",
    "healthcare": "US_IND_HLTH",
}


def to_month_end(date) -> pd.Timestamp:
    """'1926-07', '1926-07-15', Timestamp -> month-end Timestamp."""
    return pd.Timestamp(date).to_period("M").to_timestamp(how="end").normalize()


@lru_cache(maxsize=1)
def _long() -> pd.DataFrame:
    frame = pd.read_parquet(DATA_DIR / "monthly_returns.parquet")
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def _tag_list(tags) -> list[str]:
    return [tag for tag in str(tags).split(";") if tag]


def _exposure_map(exposures) -> dict[str, float]:
    return {tag: float(share) for tag, share in (item.split("=") for item in str(exposures).split(";") if "=" in item)}


@lru_cache(maxsize=1)
def load_assets() -> pd.DataFrame:
    """Asset catalogue indexed by asset_id; adds parsed `tag_list` and `exposure_map` columns."""
    catalogue = pd.read_csv(DATA_DIR / "assets.csv", keep_default_na=False)
    catalogue["tag_list"] = catalogue["tags"].apply(_tag_list)
    catalogue["exposure_map"] = catalogue["exposures"].apply(_exposure_map)
    return catalogue.set_index("asset_id")


@lru_cache(maxsize=1)
def data_version() -> dict:
    version = json.loads((DATA_DIR / "data_version.json").read_text())
    return {
        "data_sha256": version["data_sha256"],
        "built_utc": version["built_utc"],
        "last_complete_month": version["last_complete_month"],
    }


def _pivot(column: str) -> pd.DataFrame:
    return _long().pivot(index="date", columns="asset_id", values=column).sort_index()


def load_flags(assets: list[str]) -> pd.DataFrame:
    return _pivot("flag").reindex(columns=assets)


def _check_request(assets: list[str], currency: str, fx_fill: str) -> None:
    if currency not in ("CAD", "USD"):
        raise ValueError("currency must be 'CAD' or 'USD'")
    if fx_fill not in ("none", "flat"):
        raise ValueError("fx_fill must be 'none' or 'flat'")
    catalogue = load_assets()
    unknown = [asset for asset in assets if asset not in catalogue.index]
    if unknown:
        raise KeyError(f"unknown asset_id(s): {unknown}. See {DATA_DIR / 'assets.csv'}")


def _fill_with_local_returns(returns: pd.DataFrame, assets: list[str], currency: str) -> tuple[pd.DataFrame, dict]:
    """fx_fill="flat": where the FX-converted return is missing, use the local-currency return. Also returns the
    first and last filled month of each filled asset."""
    other = _pivot("return_usd" if currency == "CAD" else "return_cad").reindex(columns=assets)
    mask = returns.isna() & other.notna()
    filled = {}
    for asset in assets:
        if mask[asset].any():
            months = mask.index[mask[asset]]
            filled[asset] = [str(months.min().date()), str(months.max().date())]
    return returns.where(~mask, other), filled


@dataclass(frozen=True)
class _Coverage:
    """Period where every requested asset has a return, and the asset that limits each end of it."""

    start_asset: str
    start: pd.Timestamp
    end_asset: str
    end: pd.Timestamp

    def effective_range(self, requested_start, requested_end) -> tuple[pd.Timestamp, pd.Timestamp]:
        effective_start = max(self.start, requested_start) if requested_start is not None else self.start
        effective_end = min(self.end, requested_end) if requested_end is not None else self.end
        return effective_start, effective_end

    def shortening_messages(self, requested_start, requested_end) -> list[str]:
        messages = []
        if requested_start is not None and requested_start < self.start:
            messages.append(f"start shortened {requested_start.date()} -> {self.start.date()} by {self.start_asset}")
        if requested_end is not None and requested_end > self.end:
            messages.append(f"end shortened {requested_end.date()} -> {self.end.date()} by {self.end_asset}")
        return messages

    def info(self) -> dict:
        return {
            "limiting_start_asset": self.start_asset,
            "limiting_start_date": str(self.start.date()),
            "limiting_end_asset": self.end_asset,
            "limiting_end_date": str(self.end.date()),
        }


def _coverage(returns: pd.DataFrame, assets: list[str], currency: str) -> _Coverage:
    first = {asset: returns[asset].first_valid_index() for asset in assets}
    last = {asset: returns[asset].last_valid_index() for asset in assets}
    missing = [asset for asset in assets if first[asset] is None]
    if missing:
        raise ValueError(f"no {currency} data for {missing} (try fx_fill='flat' or the other currency)")
    start_asset = max(assets, key=lambda asset: first[asset])
    end_asset = min(assets, key=lambda asset: last[asset])
    return _Coverage(start_asset, first[start_asset], end_asset, last[end_asset])


def _iso_date(month: pd.Timestamp | None) -> str | None:
    return str(month.date()) if month is not None else None


def load_returns(  # noqa: PLR0913 - frozen public signature (finance/portfolio, calibration scripts, open PR #43)
    assets: list[str],
    start=None,
    end=None,
    currency: str = "CAD",
    fx_fill: str = "none",
    strict: bool = False,  # noqa: FBT001, FBT002 - frozen public signature (see above)
) -> pd.DataFrame:
    """Monthly total-return matrix (rows = month-end dates, columns = assets) in `currency`.

    Only dates where ALL requested assets have a return are returned. The limiting
    asset(s) are reported in `df.attrs["info"]` and with a warning when the requested
    period had to be shortened (strict=True raises instead).

    fx_fill: "none" (default) -> no CAD return before USDCAD data (1971-02), and no USD
             return for CAD assets before 1971-02.
             "flat" -> where the FX-converted return is missing, use the local-currency
             return (assumes a constant exchange rate / perfect hedge). Flagged in attrs.
    """
    currency = currency.upper()
    _check_request(assets, currency, fx_fill)
    returns = _pivot("return_cad" if currency == "CAD" else "return_usd").reindex(columns=assets)
    flat_filled = {}
    if fx_fill == "flat":
        returns, flat_filled = _fill_with_local_returns(returns, assets, currency)
    coverage = _coverage(returns, assets, currency)
    requested_start = to_month_end(start) if start is not None else None
    requested_end = to_month_end(end) if end is not None else None
    effective_start, effective_end = coverage.effective_range(requested_start, requested_end)
    selected = returns.loc[effective_start:effective_end]
    out = selected.dropna(how="any")
    info = {
        "currency": currency,
        "fx_fill": fx_fill,
        "fx_flat_filled": flat_filled,
        "requested": [_iso_date(requested_start), _iso_date(requested_end)],
        "effective": [_iso_date(out.index.min()), _iso_date(out.index.max())] if len(out) else [None, None],
        "n_months": int(len(out)),
        **coverage.info(),
        "dropped_internal_gaps": int(len(selected) - len(out)),
    }
    messages = coverage.shortening_messages(requested_start, requested_end)
    if messages:
        if strict:
            raise ValueError("; ".join(messages))
        warnings.warn("load_returns: " + "; ".join(messages), stacklevel=2)
    info["warnings"] = messages
    out.attrs["info"] = info
    return out


def load_inflation(currency: str = "CAD", start=None, end=None) -> pd.Series:
    """Monthly CPI inflation of the reference currency (US CPI-U NSA or Canada CPI all-items NSA)."""
    frame = pd.read_parquet(DATA_DIR / "inflation_monthly.parquet")
    column = "infl_ca" if currency.upper() == "CAD" else "infl_us"
    inflation = frame.set_index(pd.to_datetime(frame["date"]))[column].dropna()
    if start is not None:
        inflation = inflation[inflation.index >= to_month_end(start)]
    if end is not None:
        inflation = inflation[inflation.index <= to_month_end(end)]
    return inflation


@lru_cache(maxsize=1)
def load_lookthrough() -> pd.DataFrame:
    """Time-varying share of each KF industry in US market cap (proxy look-through for US_MKT)."""
    frame = pd.read_parquet(DATA_DIR / "lookthrough_us_mkt.parquet")
    return frame.set_index(pd.to_datetime(frame["date"])).drop(columns="date")


def _follows_us_market(asset: str, catalogue: pd.DataFrame) -> bool:
    return asset == "US_MKT" or catalogue.at[asset, "proxy_for_ticker"] == "US_MKT"


def _market_lookthrough_share(share: pd.Series, date, window: tuple | None) -> float:
    """Industry share inside US_MKT: its max over `window` when given, else its last value at `date`."""
    if window is not None:
        segment = share.loc[to_month_end(window[0]) - pd.offsets.MonthEnd(1) : to_month_end(window[1])]
        return float(segment.max()) if len(segment) else float(share.iloc[-1])
    segment = share.loc[: to_month_end(date)]
    return float(segment.iloc[-1]) if len(segment) else float(share.iloc[0])


def exposure_vector(
    assets: list[str], tag: str, date=None, overrides: dict | None = None, window: tuple | None = None
) -> np.ndarray:
    """Look-through exposure of each asset to `tag` (0..1).

    Priority: profile overrides > time-varying US_MKT look-through (KF industry cap share at
    `date`, or the MAX over `window` for hindsight/constant-weight problems; also used as an
    approximation for SPY and ESGV whose proxy is US_MKT) > static
    `exposures` column of assets.csv > 1.0 if the asset carries the tag, else 0.
    """
    catalogue = load_assets()
    overrides = overrides or {}
    exposures = np.zeros(len(assets))
    lookthrough = load_lookthrough() if tag in LOOKTHROUGH_TAGS else None
    has_date = date is not None or window is not None
    for i, asset in enumerate(assets):
        if asset in overrides and tag in overrides[asset]:
            exposures[i] = float(overrides[asset][tag])
        elif _follows_us_market(asset, catalogue) and lookthrough is not None and has_date:
            exposures[i] = _market_lookthrough_share(lookthrough[LOOKTHROUGH_TAGS[tag]], date, window)
        elif tag in catalogue.at[asset, "exposure_map"]:
            exposures[i] = catalogue.at[asset, "exposure_map"][tag]
        else:
            exposures[i] = 1.0 if tag in catalogue.at[asset, "tag_list"] else 0.0
    return exposures
