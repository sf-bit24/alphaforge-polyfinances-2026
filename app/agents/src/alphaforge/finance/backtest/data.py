"""Loading the processed monthly dataset (built by ``python -m alphaforge.finance.backtest.build_data``)."""
from __future__ import annotations

import json
import warnings
from functools import lru_cache

import numpy as np
import pandas as pd

from .paths import data_dir

DATA_DIR = data_dir()  # fixed at first import, like ALPHAFORGE_BT_DATA was before

# look-through: which KF industry column measures which exposure tag inside US_MKT
LOOKTHROUGH_TAGS = {"tech": "US_IND_BUSEQ", "energy": "US_IND_ENRGY", "financials": "US_IND_MONEY",
                    "utilities": "US_IND_UTILS", "healthcare": "US_IND_HLTH"}


def to_month_end(d) -> pd.Timestamp:
    """'1926-07', '1926-07-15', Timestamp -> month-end Timestamp."""
    return pd.Timestamp(d).to_period("M").to_timestamp(how="end").normalize()


@lru_cache(maxsize=1)
def _long() -> pd.DataFrame:
    df = pd.read_parquet(DATA_DIR / "monthly_returns.parquet")
    df["date"] = pd.to_datetime(df["date"])
    return df


@lru_cache(maxsize=1)
def load_assets() -> pd.DataFrame:
    """Asset catalogue indexed by asset_id; adds parsed `tag_list` and `exposure_map` columns."""
    a = pd.read_csv(DATA_DIR / "assets.csv", keep_default_na=False)
    a["tag_list"] = a["tags"].apply(lambda s: [t for t in str(s).split(";") if t])
    a["exposure_map"] = a["exposures"].apply(
        lambda s: {k: float(v) for k, v in (kv.split("=") for kv in str(s).split(";") if "=" in kv)})
    return a.set_index("asset_id")


@lru_cache(maxsize=1)
def data_version() -> dict:
    v = json.loads((DATA_DIR / "data_version.json").read_text())
    return {
        "data_sha256": v["data_sha256"],
        "built_utc": v["built_utc"],
        "last_complete_month": v["last_complete_month"],
    }


def _pivot(col: str) -> pd.DataFrame:
    return _long().pivot(index="date", columns="asset_id", values=col).sort_index()


def load_flags(assets: list[str]) -> pd.DataFrame:
    return _pivot("flag").reindex(columns=assets)


def load_returns(
    assets: list[str], start=None, end=None, currency: str = "CAD", fx_fill: str = "none", strict: bool = False
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
    if currency not in ("CAD", "USD"):
        raise ValueError("currency must be 'CAD' or 'USD'")
    if fx_fill not in ("none", "flat"):
        raise ValueError("fx_fill must be 'none' or 'flat'")
    cat = load_assets()
    unknown = [a for a in assets if a not in cat.index]
    if unknown:
        raise KeyError(f"unknown asset_id(s): {unknown}. See {DATA_DIR / 'assets.csv'}")
    main = _pivot("return_cad" if currency == "CAD" else "return_usd").reindex(columns=assets)
    filled_cols = {}
    if fx_fill == "flat":
        other = _pivot("return_usd" if currency == "CAD" else "return_cad").reindex(columns=assets)
        mask = main.isna() & other.notna()
        for a in assets:
            if mask[a].any():
                filled_cols[a] = [str(mask.index[mask[a]].min().date()), str(mask.index[mask[a]].max().date())]
        main = main.where(~mask, other)
    first = {a: main[a].first_valid_index() for a in assets}
    last = {a: main[a].last_valid_index() for a in assets}
    missing = [a for a in assets if first[a] is None]
    if missing:
        raise ValueError(f"no {currency} data for {missing} (try fx_fill='flat' or the other currency)")
    lim_start = max(assets, key=lambda a: first[a])
    lim_end = min(assets, key=lambda a: last[a])
    s, e = first[lim_start], last[lim_end]
    req_s = to_month_end(start) if start is not None else None
    req_e = to_month_end(end) if end is not None else None
    eff_s = max(s, req_s) if req_s is not None else s
    eff_e = min(e, req_e) if req_e is not None else e
    out = main.loc[eff_s:eff_e].dropna(how="any")
    info = {
        "currency": currency,
        "fx_fill": fx_fill,
        "fx_flat_filled": filled_cols,
        "requested": [
            str(req_s.date()) if req_s is not None else None,
            str(req_e.date()) if req_e is not None else None,
        ],
        "effective": [
            str(out.index.min().date()) if len(out) else None,
            str(out.index.max().date()) if len(out) else None,
        ],
        "n_months": int(len(out)),
        "limiting_start_asset": lim_start,
        "limiting_start_date": str(s.date()),
        "limiting_end_asset": lim_end,
        "limiting_end_date": str(e.date()),
        "dropped_internal_gaps": int(len(main.loc[eff_s:eff_e]) - len(out)),
    }
    msgs = []
    if req_s is not None and req_s < s:
        msgs.append(f"start shortened {req_s.date()} -> {s.date()} by {lim_start}")
    if req_e is not None and req_e > e:
        msgs.append(f"end shortened {req_e.date()} -> {e.date()} by {lim_end}")
    if msgs:
        if strict:
            raise ValueError("; ".join(msgs))
        warnings.warn("load_returns: " + "; ".join(msgs), stacklevel=2)
    info["warnings"] = msgs
    out.attrs["info"] = info
    return out


def load_inflation(currency: str = "CAD", start=None, end=None) -> pd.Series:
    """Monthly CPI inflation of the reference currency (US CPI-U NSA or Canada CPI all-items NSA)."""
    df = pd.read_parquet(DATA_DIR / "inflation_monthly.parquet")
    s = df.set_index(pd.to_datetime(df["date"]))["infl_ca" if currency.upper() == "CAD" else "infl_us"].dropna()
    if start is not None:
        s = s[s.index >= to_month_end(start)]
    if end is not None:
        s = s[s.index <= to_month_end(end)]
    return s


@lru_cache(maxsize=1)
def load_lookthrough() -> pd.DataFrame:
    """Time-varying share of each KF industry in US market cap (proxy look-through for US_MKT)."""
    df = pd.read_parquet(DATA_DIR / "lookthrough_us_mkt.parquet")
    return df.set_index(pd.to_datetime(df["date"])).drop(columns="date")


def exposure_vector(
    assets: list[str], tag: str, date=None, overrides: dict | None = None, window: tuple | None = None
) -> np.ndarray:
    """Look-through exposure of each asset to `tag` (0..1).

    Priority: profile overrides > time-varying US_MKT look-through (KF industry cap share at
    `date`, or the MAX over `window` for hindsight/constant-weight problems; also used as an
    approximation for SPY and ESGV whose proxy is US_MKT) > static
    `exposures` column of assets.csv > 1.0 if the asset carries the tag, else 0.
    """
    cat = load_assets()
    overrides = overrides or {}
    v = np.zeros(len(assets))
    lt = load_lookthrough() if tag in LOOKTHROUGH_TAGS else None
    for i, a in enumerate(assets):
        if a in overrides and tag in overrides[a]:
            v[i] = float(overrides[a][tag])
        elif (
            (a == "US_MKT" or cat.at[a, "proxy_for_ticker"] == "US_MKT")
            and lt is not None
            and (date is not None or window is not None)
        ):
            col = lt[LOOKTHROUGH_TAGS[tag]]
            if window is not None:
                seg = col.loc[to_month_end(window[0]) - pd.offsets.MonthEnd(1) : to_month_end(window[1])]
                v[i] = float(seg.max()) if len(seg) else float(col.iloc[-1])
            else:
                seg = col.loc[: to_month_end(date)]
                v[i] = float(seg.iloc[-1]) if len(seg) else float(col.iloc[0])
        elif tag in cat.at[a, "exposure_map"]:
            v[i] = cat.at[a, "exposure_map"][tag]
        else:
            v[i] = 1.0 if tag in cat.at[a, "tag_list"] else 0.0
    return v
