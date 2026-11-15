"""B5 - reconcile engine monthly metrics (CAD) with analyse/relation-profils-actifs/quant (daily, CAD, to 2026-11-12).

Decomposition of the gap for each ticker, step by step:
  (1) theirs: published value (metriques_titres_cad.csv, READ ONLY);
  (2) daily, recomputed here from the starter (adj_close x usdcad, ffill), 2021-11-12 -> 2026-11-12 (should match 1);
  (3) daily, same start, end 2026-09-30 (effect of the end date);
  (4) monthly month-end from the same daily series, 2021-11-30 -> 2026-09-30 (effect of frequency + start);
  (5) engine monthly returns (data/long, CNQ.TO Aug-2022 corrected), returns 2021-12 -> 2026-09.
Metrics: CAGR (calendar), vol (daily x sqrt 252 / monthly x sqrt 12), max drawdown, 2022 return. SIMULATION ONLY.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from alphaforge.finance.backtest.paths import starter_dir

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

from common import write_trace
from alphaforge.finance.backtest import metrics as M
from alphaforge.finance.backtest.data import load_returns

STARTER = starter_dir()  # official starter, committed in the app
THEIRS = Path(os.environ.get("ALPHAFORGE_REG_DIR", "relation-profils-actifs")) / "quant" / "metriques_titres_cad.csv"
TICKERS = ["XIU.TO", "SPY", "XBB.TO", "ZST.TO", "GLD", "CNQ.TO"]


def daily_metrics(v: pd.Series, freq: int) -> dict:
    r = v.pct_change().dropna().values
    yrs = (v.index[-1] - v.index[0]).days / 365.25
    y21 = v[v.index.year == 2021].iloc[-1]
    y22 = v[v.index.year == 2022].iloc[-1]
    return {"cagr": float((v.iloc[-1] / v.iloc[0]) ** (1 / yrs) - 1), "vol": float(np.std(r, ddof=1) * np.sqrt(freq)),
            "max_dd": float(M.max_drawdown(r)), "ret_2022": float(y22 / y21 - 1),
            "start": str(v.index[0].date()), "end": str(v.index[-1].date()), "n": len(r)}


def main():
    px = pd.read_csv(STARTER / "prices_daily.csv", usecols=["date", "ticker", "adj_close", "currency"], parse_dates=["date"])
    fx = pd.read_csv(STARTER / "fx_usdcad_daily.csv", parse_dates=["date"]).set_index("date")["usdcad"]
    th = pd.read_csv(THEIRS).set_index("Ticker")
    piv = px.pivot(index="date", columns="ticker", values="adj_close")
    cal = pd.DatetimeIndex(sorted(px.loc[~px.ticker.isin(["BTC-USD", "ETH-USD"]), "date"].unique()))
    piv = piv.reindex(cal)   # TSX or US trading days (crypto weekends excluded), like quant/stats_classes.py
    fxa = fx.reindex(cal).ffill()
    eng = load_returns(TICKERS, start="2021-12", end="2026-09", currency="CAD")
    out = {}
    for t in TICKERS:
        cur = px.loc[px.ticker == t, "currency"].iloc[0]
        v = piv[t].ffill()
        if cur == "USD":
            v = v * fxa
        v = v.dropna()
        d_full = daily_metrics(v, 252)
        d_sep = daily_metrics(v[:"2026-09-30"], 252)
        vm = v[:"2026-09-30"].resample("ME").last()
        vm = vm[vm.index >= "2021-11-30"]
        m_from_daily = daily_metrics(vm, 12)
        r = eng[t].values
        yrs = len(r) / 12
        e = {"cagr": float(np.prod(1 + r) ** (1 / yrs) - 1), "vol": float(np.std(r, ddof=1) * np.sqrt(12)),
             "max_dd": float(M.max_drawdown(r)),
             "ret_2022": float(np.prod(1 + eng[t]["2022-01":"2022-12"].values) - 1), "n": len(r),
             "aug_2022_return": float(eng.loc["2022-08-31", t])}
        o = th.loc[t]
        out[t] = {"theirs": {"cagr": float(o["CAGR"]), "vol": float(o["Vol"]), "max_dd": float(-o["MaxDD"]), "ret_2022": float(o["Rdt 2022"])},
                  "daily_full_recomputed": d_full, "daily_to_2026_09": d_sep, "monthly_from_daily": m_from_daily, "engine_monthly": e}
        if t == "CNQ.TO":
            vm2 = v.resample("ME").last()
            out[t]["starter_aug_2022_month_return_raw"] = float(vm2["2022-08-31"] / vm2["2022-07-31"] - 1)
            print("CNQ Aug-2022 raw starter", out[t]["starter_aug_2022_month_return_raw"], "engine", e["aug_2022_return"])
        print(t, {k: {kk: round(vv, 4) for kk, vv in val.items() if isinstance(vv, float)} for k, val in out[t].items() if isinstance(val, dict)})
    out["n_calendar_days"] = int(len(cal))
    print("calendar days", len(cal))
    print(write_trace("reconcile", out, {"doc": __doc__}))


if __name__ == "__main__":
    main()
