"""Observable variables at the START of each window (known at the end of the month BEFORE the window).

Sources (already downloaded by data/build_data.py, read-only):
  - Shiller ie_data.xls (CAPE, long rate GS10; 1871-2024-09). CAPE is lagged 3 extra months because
    the earnings in it are published with a delay (avoid look-ahead).
  - processed/inflation_monthly.parquet (US CPI-U NSA, Canada CPI) -> trailing 12 m inflation, lagged 1 extra
    month (CPI of month t is released in t+1).
  - processed/monthly_returns.parquet via engine (UST_TBILL, US_MKT, US_IND_BUSEQ, CA_EQ) -> T-bill rate,
    12 m market trend, 10 m moving-average flag, 3 y tech-vs-market relative return.
  - processed/lookthrough_us_mkt.parquet -> BusEq share of US market cap (a 'tech bubble' gauge).
  - raw/fred/IRLTLT01CAM156N.csv (OECD Canada long rate), processed/fx_monthly.parquet (USDCAD).
SIMULATION / RESEARCH ONLY.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amira_common import BT  # noqa: E402
from engine.data import load_lookthrough, load_returns  # noqa: E402

RAW = BT / "data" / "raw"
PROC = BT / "data" / "processed"


def _me(idx):
    return pd.DatetimeIndex(pd.to_datetime(idx)).to_period("M").to_timestamp(how="end").normalize()


def shiller() -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        x = pd.read_excel(RAW / "shiller" / "ie_data.xls", sheet_name="Data", header=None, skiprows=8)
    x = x[[0, 6, 12]].dropna(subset=[0])
    x = x[pd.to_numeric(x[0], errors="coerce").notna()]
    d = x[0].astype(float)
    yr = np.floor(d).astype(int)
    mo = np.round((d - yr) * 100).astype(int)
    idx = _me(pd.to_datetime(dict(year=yr, month=mo, day=1)))
    out = pd.DataFrame({"long_rate_shiller": pd.to_numeric(x[6], errors="coerce").values / 100,
                        "cape": pd.to_numeric(x[12], errors="coerce").values}, index=idx)
    out["cape"] = out["cape"].shift(3)  # publication lag of earnings
    return out


def monthly_signals() -> pd.DataFrame:
    """One row per month-end t = information available at the END of month t (use t = month before window)."""
    sh = shiller()
    R = load_returns(["UST_TBILL", "US_MKT", "US_IND_BUSEQ"], currency="USD")
    infl = pd.read_parquet(PROC / "inflation_monthly.parquet")
    infl.index = _me(infl["date"])
    lt = load_lookthrough()
    df = pd.DataFrame(index=R.index)
    df["tbill"] = R["UST_TBILL"] * 12
    df["long_rate"] = sh["long_rate_shiller"].reindex(df.index)
    gs10 = pd.read_csv(RAW / "fred" / "GS10.csv")
    gs10.index = _me(gs10["observation_date"])
    df["long_rate"] = df["long_rate"].where(df["long_rate"].notna(), gs10["GS10"].reindex(df.index) / 100)
    df["slope"] = df["long_rate"] - df["tbill"]
    df["d_long_rate_12m"] = df["long_rate"] - df["long_rate"].shift(12)
    cpi_us = (1 + infl["infl_us"]).rolling(12).apply(np.prod, raw=True) - 1
    df["infl_us_12m"] = cpi_us.shift(1).reindex(df.index)
    df["real_tbill"] = df["tbill"] - df["infl_us_12m"]
    mkt = (1 + R["US_MKT"]).cumprod()
    df["mkt_12m"] = mkt / mkt.shift(12) - 1
    df["mkt_above_ma10"] = (mkt > mkt.rolling(10).mean()).astype(float)
    tech = (1 + R["US_IND_BUSEQ"]).cumprod()
    df["tech_rel_36m"] = (tech / tech.shift(36)) / (mkt / mkt.shift(36)) - 1
    df["buseq_share"] = lt["US_IND_BUSEQ"].reindex(df.index)
    df["cape"] = sh["cape"].reindex(df.index)
    # Canada
    ca = pd.read_csv(RAW / "fred" / "IRLTLT01CAM156N.csv")
    ca.index = _me(ca["observation_date"])
    df["ca_long_rate"] = ca["IRLTLT01CAM156N"].reindex(df.index) / 100
    cpi_ca = (1 + infl["infl_ca"]).rolling(12).apply(np.prod, raw=True) - 1
    df["infl_ca_12m"] = cpi_ca.shift(1).reindex(df.index)
    fx = pd.read_parquet(PROC / "fx_monthly.parquet")
    fx.index = _me(fx["date"])
    df["usdcad_12m"] = (fx["usdcad"] / fx["usdcad"].shift(12) - 1).reindex(df.index)
    return df


def at_window_starts(labels: list[str], sig: pd.DataFrame | None = None) -> pd.DataFrame:
    sig = monthly_signals() if sig is None else sig
    rows = []
    for lab in labels:
        s = pd.Timestamp(lab.split("..")[0] + "-01").to_period("M").to_timestamp(how="end").normalize()
        prev = s - pd.offsets.MonthEnd(1)
        r = sig.loc[:prev].iloc[-1] if len(sig.loc[:prev]) else pd.Series(dtype=float)
        rows.append({"window": lab, "obs_date": str(prev.date()), **r.to_dict()})
    return pd.DataFrame(rows).set_index("window")
