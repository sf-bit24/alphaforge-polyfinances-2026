"""Start-of-window observable signals (information available at the end of the month BEFORE the window).

Sources (read-only, from engine data/raw and data/processed):
  Shiller ie_data.xls (CAPE col 12, long rate col 6; ends 2024-09), FRED GS10 (1953-04+), BAA/AAA (1919+),
  FRED IR3TIB01CAM156N / IRLTLT01CAM156N (Canada 3m / 10y, OECD), processed returns (US_MKT, UST_TBILL,
  CA_EQ, CA_TBILL) and inflation_monthly.parquet.
Caveats: CAPE uses earnings published with a lag (mild look-ahead of a few months); FRED/OECD values are
revised (not vintage); monthly-average yields. SIMULATION ONLY.
"""
from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

BT = Path(__file__).resolve().parent.parent.parent
RAW = BT / "data" / "raw"
PROC = BT / "data" / "processed"


def _me(s):
    return pd.to_datetime(s).dt.to_period("M").dt.to_timestamp(how="end").dt.normalize()


def _fred(name):
    df = pd.read_csv(RAW / "fred" / f"{name}.csv")
    df.columns = ["date", "v"]
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    return pd.Series(df["v"].values, index=_me(df["date"])).dropna()


@lru_cache(maxsize=1)
def table() -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        x = pd.read_excel(RAW / "shiller" / "ie_data.xls", sheet_name="Data", header=None, engine="xlrd")
    x = x.iloc[8:, [0, 6, 12]]
    x = x[pd.to_numeric(x[0], errors="coerce").notna()]
    d = x[0].astype(float)
    yr = np.floor(d).astype(int)
    mo = np.round((d - yr) * 100).astype(int)
    idx = pd.to_datetime(dict(year=yr, month=mo, day=1)).dt.to_period("M").dt.to_timestamp(how="end").dt.normalize()
    sh = pd.DataFrame({"long_shiller": pd.to_numeric(x[6], errors="coerce").values,
                       "cape": pd.to_numeric(x[12], errors="coerce").values}, index=idx.values)
    long = pd.read_parquet(PROC / "monthly_returns.parquet")
    long["date"] = pd.to_datetime(long["date"])
    usd = long.pivot(index="date", columns="asset_id", values="return_usd")
    cad = long.pivot(index="date", columns="asset_id", values="return_cad")
    infl = pd.read_parquet(PROC / "inflation_monthly.parquet")
    infl = infl.set_index(pd.to_datetime(infl["date"]))
    T = pd.DataFrame(index=usd.index)
    gs10 = _fred("GS10")
    T["long_us"] = gs10.reindex(T.index).combine_first(sh["long_shiller"].reindex(T.index))
    T["tbill_us"] = ((1 + usd["UST_TBILL"]) ** 12 - 1) * 100
    T["slope_us"] = T["long_us"] - T["tbill_us"]
    T["infl12_us"] = ((1 + infl["infl_us"]).rolling(12).apply(np.prod, raw=True) - 1).reindex(T.index) * 100
    T["real_short_us"] = T["tbill_us"] - T["infl12_us"]
    T["d_long_12m_us"] = T["long_us"].diff(12)
    T["cape"] = sh["cape"].reindex(T.index)
    T["credit_spread"] = (_fred("BAA") - _fred("AAA")).reindex(T.index)
    eq = usd["US_MKT"]
    lvl = (1 + eq).cumprod()
    T["mom12_us"] = (lvl / lvl.shift(12) - 1) * 100
    ma = lvl.rolling(10).mean()
    T["trend10_us"] = (lvl > ma).astype(float).where(ma.notna())
    T["infl12_ca"] = ((1 + infl["infl_ca"]).rolling(12).apply(np.prod, raw=True) - 1).reindex(T.index) * 100
    T["tbill_ca"] = _fred("IR3TIB01CAM156N").reindex(T.index)
    T["long_ca"] = _fred("IRLTLT01CAM156N").reindex(T.index)
    T["slope_ca"] = T["long_ca"] - T["tbill_ca"]
    T["real_short_ca"] = T["tbill_ca"] - T["infl12_ca"]
    ca = cad["CA_EQ"]
    lc = (1 + ca).cumprod()
    T["mom12_ca"] = (lc / lc.shift(12) - 1) * 100
    return T


def at_start(window_start) -> dict:
    """Signals observed at the end of the month before `window_start` (first month of the window)."""
    T = table()
    t = pd.Timestamp(window_start) - pd.offsets.MonthEnd(1)
    seg = T.loc[:t]
    return {k: (None if pd.isna(v) else float(v)) for k, v in seg.iloc[-1].items()} if len(seg) else {}


if __name__ == "__main__":
    T = table()
    print(T.loc["1926-12":"1927-01"].T)
    print(T.dropna(how="all").tail(2).T)
