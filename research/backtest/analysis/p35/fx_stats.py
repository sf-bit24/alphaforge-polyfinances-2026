"""Persona 35 - USDCAD history (no forecast), CAD vs USD decomposition of US assets, and reconciliation (B5)
with the regulatory analysis' daily numbers (analyse/relation-profils-actifs/quant).

Outputs: results/p35_analysis/fx_stats.json
SIMULATION ONLY - describes the past; says nothing about the future exchange rate.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

import common as C
from engine import metrics as M
from engine.data import load_returns

THEIRS = Path("/mnt/c/Users/User/Desktop/ecole/hackoton/analyse/relation-profils-actifs/quant/metriques_titres_cad.csv")


def episodes(fx: pd.Series, months: int, k: int = 5, sign: int = 1) -> list[dict]:
    """k worst non-overlapping `months` changes of USDCAD (sign=+1: USD up = CAD down)."""
    ch = (fx / fx.shift(months) - 1).dropna() * sign
    out, used = [], []
    for d, v in ch.sort_values(ascending=False).items():
        i = fx.index.get_loc(d)
        if any(abs(i - j) < months for j in used):
            continue
        used.append(i)
        out.append({"start": str(fx.index[i - months].date()), "end": str(d.date()), "change": float(v * sign),
                    "usdcad_start": float(fx.iloc[i - months]), "usdcad_end": float(fx.iloc[i])})
        if len(out) == k:
            break
    return out


def fx_history() -> dict:
    fx = C.fx_monthly()
    fx = fx[fx.index >= "1971-01-31"]
    lr = np.log(fx).diff().dropna()
    res = {"source": "data/processed/fx_monthly.parquet (FRED DEXCAUS month-end to 2021-10, starter BoC after)",
           "period": [str(fx.index.min().date()), str(fx.index.max().date())], "n_months": int(len(fx)),
           "level": {"min": float(fx.min()), "min_date": str(fx.idxmin().date()), "max": float(fx.max()),
                     "max_date": str(fx.idxmax().date()), "median": float(fx.median()),
                     "p10": float(fx.quantile(.1)), "p90": float(fx.quantile(.9)), "last": float(fx.iloc[-1]),
                     "last_date": str(fx.index[-1].date())},
           "vol_ann_monthly_log": float(lr.std() * np.sqrt(12)),
           "vol_by_decade": {f"{d}s": float(lr[(lr.index.year >= d) & (lr.index.year < d + 10)].std() * np.sqrt(12))
                             for d in range(1970, 2030, 10)}}
    for h in (1, 6, 12, 24, 60):
        ch = (fx / fx.shift(h) - 1).dropna()
        res[f"change_{h}m"] = {"min": float(ch.min()), "p05": float(ch.quantile(.05)), "median": float(ch.median()),
                               "p95": float(ch.quantile(.95)), "max": float(ch.max()),
                               "share_abs_gt_10pct": float((ch.abs() > .10).mean())}
    res["worst_cad_episodes_12m"] = episodes(fx, 12, 5, +1)     # USD up / CAD down (USD spending dearer)
    res["best_cad_episodes_12m"] = episodes(fx, 12, 5, -1)
    res["worst_cad_episodes_6m"] = episodes(fx, 6, 5, +1)
    cadusd = 1 / fx
    dd = cadusd / cadusd.cummax() - 1
    tr = dd.idxmin()
    pk = cadusd.loc[:tr].idxmax()
    rec = cadusd.loc[tr:][cadusd.loc[tr:] >= cadusd.loc[pk]]
    res["cad_max_drawdown_vs_usd"] = {"depth": float(-dd.min()), "peak": str(pk.date()), "trough": str(tr.date()),
                                      "recovered": str(rec.index[0].date()) if len(rec) else None}
    # range and median of USDCAD per 15-year and 5-year block (anchoring bias: no "good rate")
    res["range_by_window"] = {}
    for y0 in (1971, 1986, 2001, 2016, 2021):
        s = fx[(fx.index.year >= y0) & (fx.index.year < y0 + 15)]
        res["range_by_window"][f"{y0}-{min(y0 + 14, 2026)}"] = {"min": float(s.min()), "median": float(s.median()),
                                                                "max": float(s.max())}
    return res


def starter_daily() -> dict:
    fx = pd.read_csv(C.STARTER / "fx_usdcad_daily.csv", parse_dates=["date"]).set_index("date")["usdcad"]
    px = pd.read_csv(C.STARTER / "prices_daily.csv", parse_dates=["date"], usecols=["date", "ticker"])
    tsx = set(px[px.ticker.str.endswith(".TO")].date)
    us = set(px[~px.ticker.str.endswith(".TO") & ~px.ticker.str.endswith("-USD")].date)
    cal = pd.DatetimeIndex(sorted(tsx | us))
    miss = cal.difference(fx.index)
    fxc = fx.reindex(cal).ffill()
    r = np.log(fxc).diff().dropna()
    return {"source": "starter fx_usdcad_daily.csv (Bank of Canada)", "n_rows": int(len(fx)),
            "first": [str(fx.index[0].date()), float(fx.iloc[0])], "last": [str(fx.index[-1].date()), float(fx.iloc[-1])],
            "change_full": float(fx.iloc[-1] / fx.iloc[0] - 1),
            "trading_calendar_days_union_tsx_us": int(len(cal)),
            "calendar_days_without_boc_rate_ffilled": int(len(miss)),
            "examples_ffilled": [str(d.date()) for d in miss[:8]],
            "min": float(fx.min()), "min_date": str(fx.idxmin().date()), "max": float(fx.max()),
            "max_date": str(fx.idxmax().date()), "median": float(fx.median()),
            "vol_ann_daily_log": float(r.std() * np.sqrt(252))}


def decomposition(start="2021-11", end="2026-09") -> dict:
    """US asset return in CAD = (1 + return in USD) x (1 + USDCAD change) - 1 (monthly engine data)."""
    tick = ["SPY", "AGG", "JNJ", "PG", "GLD", "XIU.TO", "XBB.TO", "ZST.TO"]
    Rc = load_returns(tick, start, end, "CAD")
    Ru = load_returns(tick, start, end, "USD")
    fx = C.fx_monthly()
    fxr = (fx / fx.shift(1) - 1).reindex(Rc.index)
    out = {"period": [str(Rc.index.min().date()), str(Rc.index.max().date())], "n_months": int(len(Rc)),
           "fx_ann_change": M.annualized_return(fxr.values), "fx_cum_change": M.cumulative_growth(fxr.values),
           "assets": {}}
    for t in tick:
        c, u = Rc[t].values, Ru[t].values
        out["assets"][t] = {
            "ann_cad": M.annualized_return(c), "ann_usd": M.annualized_return(u),
            "check_(1+usd)(1+fx)-1": (1 + M.annualized_return(u)) * (1 + M.annualized_return(fxr.values)) - 1,
            "vol_cad": M.volatility(c), "vol_usd": M.volatility(u),
            "maxdd_cad": M.max_drawdown(c), "maxdd_usd": M.max_drawdown(u),
            "corr_usd_return_vs_fx_change": float(np.corrcoef(u, fxr.values)[0, 1]),
            "ret_2022_cad": float(np.prod(1 + Rc[t]["2022"].values) - 1),
            "ret_2022_usd": float(np.prod(1 + Ru[t]["2022"].values) - 1)}
    # long history: US equity (USD) vs USDCAD changes - is the USD a 'safe haven' for a Canadian?
    L = load_returns(["US_MKT", "UST_5Y", "UST_TBILL"], "1971-02", "2026-09", "USD")
    f = (fx / fx.shift(1) - 1).reindex(L.index)
    worst = L["US_MKT"].nsmallest(int(len(L) * 0.05)).index
    out["long_1971"] = {"corr_US_MKT_usd_vs_fx": float(np.corrcoef(L["US_MKT"], f)[0, 1]),
                        "corr_UST_5Y_usd_vs_fx": float(np.corrcoef(L["UST_5Y"], f)[0, 1]),
                        "mean_fx_change_in_worst5pct_US_MKT_months": float(f[worst].mean()),
                        "mean_fx_change_all_months": float(f.mean()),
                        "n_worst_months": int(len(worst))}
    return out


def their_metrics(v: pd.Series) -> dict:
    """Re-implementation of stats_classes.metrics (daily) - CAGR 365.25 d, vol sqrt(252), maxDD on levels."""
    v = v.dropna()
    r = v.pct_change().dropna()
    years = (v.index[-1] - v.index[0]).days / 365.25
    dd = v / v.cummax() - 1
    return {"CAGR": float((v.iloc[-1] / v.iloc[0]) ** (1 / years) - 1), "Vol": float(r.std() * np.sqrt(252)),
            "MaxDD": float(-dd.min())}


def reconciliation() -> dict:
    """B5: their daily numbers vs a daily recomputation (same method) vs engine monthly numbers."""
    th = pd.read_csv(THEIRS).set_index("Ticker")
    px = pd.read_csv(C.STARTER / "prices_daily.csv", parse_dates=["date"])
    adj = px.pivot(index="date", columns="ticker", values="adj_close").sort_index()
    tsx = [t for t in adj.columns if t.endswith(".TO")]
    us = [t for t in adj.columns if t not in tsx and not t.endswith("-USD")]
    cal = pd.DatetimeIndex(sorted(set(adj[tsx].dropna(how="all").index) | set(adj[us].dropna(how="all").index)))
    adjc = adj.reindex(cal).ffill()
    fx = pd.read_csv(C.STARTER / "fx_usdcad_daily.csv", parse_dates=["date"]).set_index("date")["usdcad"]
    fxc = fx.reindex(cal).ffill().bfill()
    out = {}
    for t in ["SPY", "AGG", "GLD", "XBB.TO", "CNQ.TO", "USDCAD"]:
        if t == "USDCAD":
            vd = fxc
        else:
            vd = adjc[t] * (fxc if t in us else 1.0)
        d_full = their_metrics(vd)
        d_sep = their_metrics(vd.loc[:"2026-09-30"])
        d_sep_from_nov30 = their_metrics(vd.loc["2021-11-30":"2026-09-30"])
        # monthly on the same daily series (month-end sampling), same base 2021-11-30 -> isolates frequency
        vm = vd.loc["2021-11-30":"2026-09-30"].resample("ME").last()
        rm = vm.pct_change().dropna().values
        mon_same = {"CAGR": M.annualized_return(rm), "Vol": M.volatility(rm), "MaxDD": M.max_drawdown(rm)}
        # engine monthly (yfinance 2021-11 + starter after; FX month-end; CNQ fix)
        if t == "USDCAD":
            f = C.fx_monthly()
            re = (f / f.shift(1) - 1).loc["2021-11-30":"2026-09-30"].values
            re12 = (f / f.shift(1) - 1).loc["2021-12-31":"2026-09-30"].values
        else:
            Re = load_returns([t], "2021-11", "2026-09", "CAD")
            re = Re[t].values
            re12 = Re[t].loc["2021-12-31":].values
        eng = {"CAGR": M.annualized_return(re), "Vol": M.volatility(re), "MaxDD": M.max_drawdown(re), "n": int(len(re))}
        eng12 = {"CAGR": M.annualized_return(re12), "Vol": M.volatility(re12), "MaxDD": M.max_drawdown(re12),
                 "n": int(len(re12))}
        theirs = None
        if t in th.index:
            theirs = {"CAGR": float(th.at[t, "CAGR"]), "Vol": float(th.at[t, "Vol"]), "MaxDD": float(-th.at[t, "MaxDD"])}
        out[t] = {"theirs_daily_2021-11-12_2026-11-12": theirs, "recomputed_daily_same_method": d_full,
                  "daily_to_2026-09-30": d_sep, "daily_2021-11-30_to_2026-09-30": d_sep_from_nov30,
                  "monthly_sampling_same_daily_series_2021-12_2026-09": mon_same,
                  "engine_monthly_2021-11_2026-09": eng, "engine_monthly_2021-12_2026-09": eng12}
    # CNQ fix effect on August 2022 (engine flag) - daily raw vs engine month
    raw_aug = adj["CNQ.TO"].dropna().loc["2022-07-29":"2022-08-31"]
    out["CNQ.TO"]["aug2022_raw_starter_adj_close"] = float(raw_aug.iloc[-1] / raw_aug.iloc[0] - 1)
    out["CNQ.TO"]["aug2022_engine"] = float(load_returns(["CNQ.TO"], "2022-08", "2022-08", "CAD").iloc[0, 0])
    return out


if __name__ == "__main__":
    payload = {"fx_history": fx_history(), "starter_daily": starter_daily(), "decomposition": decomposition(),
               "reconciliation_B5": reconciliation()}
    p = C.write_trace("fx_stats", payload, {"note": "no FX forecast; describes the past only"}, "fx_stats.py")
    import json
    print(json.dumps(C._clean(payload), indent=1)[:12000])
    print(p)
