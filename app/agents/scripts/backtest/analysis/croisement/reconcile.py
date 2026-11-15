"""Item 6 - reconcile analyse/relation-profils-actifs/quant (daily, CAD, 2021-11-12 -> 2026-11-12, READ ONLY) with
the engine (monthly, CAD) for every asset of the 3 robust strategies (Robert eq20_gold10 -> XIU.TO SPY GLD XBB.TO
ZST.TO ; Mateo risk_parity_iv36 -> ESGV XIU.TO XBB.TO AGG GLD ; Amira Mom_etf_top3 -> SPY XIU.TO AGG TLT XBB.TO
GLD ZST.TO, optional BTC-USD) + CNQ.TO, and for their 3 BNC strategy proxies.
Step by step, one factor at a time:
  (1) theirs (metriques_titres_cad.csv / metriques_strategies_cad.csv);
  (2) their method re-implemented (calendar = union TSX/US days, ffill, adj_close x usdcad ffill), same dates;
  (3) same, end 2026-09-30 (engine end);  (4) same, start 2021-11-30;  (5) month-end sampling of (4);
  (6) engine monthly returns 2021-12 -> 2026-09 (58 months, base 2021-11-30);  (7) engine with 2021-11 (59 months).
CAGR on calendar time (daily) or n/12 (monthly); vol daily x sqrt(252) or monthly x sqrt(12); maxDD; 2022 return.
SIMULATION ONLY.
"""
from __future__ import annotations

import sys
from pathlib import Path
from alphaforge.finance.backtest.paths import DEFAULT_DATA_DIR
from alphaforge.finance.backtest.paths import starter_dir

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
from alphaforge.finance.backtest import metrics as M  # noqa: E402
from alphaforge.finance.backtest.data import load_returns  # noqa: E402

STARTER = starter_dir()  # official starter, committed in the app
TICKERS = ["XIU.TO", "SPY", "ESGV", "XBB.TO", "ZST.TO", "AGG", "TLT", "GLD", "BTC-USD", "CNQ.TO"]
MIXES = {"conservateur": {"XBB.TO": .70, "XIU.TO": .09, "SPY": .21}, "equilibre": {"XBB.TO": .40, "XIU.TO": .18, "SPY": .42},
         "actions": {"XIU.TO": .30, "SPY": .70}}
THEIR_MIX = {"conservateur": "Défensive (Conservateur 70/9/21)", "equilibre": "Dynamique (Équilibré 40/18/42)",
             "actions": "Offensive (Actions 0/30/70)"}
USED_BY = {"XIU.TO": "Robert, Mateo, Amira", "SPY": "Robert, Amira", "ESGV": "Mateo", "XBB.TO": "Robert, Mateo, Amira",
           "ZST.TO": "Robert, Amira (encaisse)", "AGG": "Mateo, Amira", "TLT": "Amira (candidat momentum)",
           "GLD": "Robert, Mateo, Amira", "BTC-USD": "Amira (poche optionnelle 3 %)", "CNQ.TO": "contrôle de données"}


def m_daily(v: pd.Series, freq: int) -> dict:
    v = v.dropna()
    r = v.pct_change().dropna().values
    yrs = (v.index[-1] - v.index[0]).days / 365.25
    ye = v.resample("YE").last()
    return {"cagr": float((v.iloc[-1] / v.iloc[0]) ** (1 / yrs) - 1), "vol": float(np.std(r, ddof=1) * np.sqrt(freq)),
            "maxdd": float(M.max_drawdown(r)), "ret_2022": float(ye.loc["2022"].iloc[0] / ye.loc["2021"].iloc[0] - 1),
            "start": str(v.index[0].date()), "end": str(v.index[-1].date()), "n": int(len(r))}


def m_monthly(r: pd.Series) -> dict:
    x = r.values
    return {"cagr": float(np.prod(1 + x) ** (12 / len(x)) - 1), "vol": float(np.std(x, ddof=1) * np.sqrt(12)),
            "maxdd": float(M.max_drawdown(x)), "ret_2022": float(np.prod(1 + r.loc["2022-01":"2022-12"].values) - 1),
            "start": str(r.index[0].date()), "end": str(r.index[-1].date()), "n": int(len(x))}


def monthly_rebal(prices: pd.DataFrame, w: dict) -> pd.Series:
    """their portfolio(): value rebalanced on the last trading day of each month (re-implemented)."""
    p = prices[list(w)]
    wv = np.array([w[k] for k in p.columns])
    me = p.groupby(p.index.to_period("M")).tail(1).index
    out = pd.Series(index=p.index, dtype=float)
    val, b = 1.0, 0
    reb = [p.index.get_loc(x) for x in me]
    if reb[-1] != len(p) - 1:
        reb.append(len(p) - 1)
    for j in reb:
        seg = p.iloc[b:j + 1].to_numpy()
        out.iloc[b:j + 1] = val * ((seg / seg[0]) @ wv)
        val, b = out.iloc[j], j
    return out


def main():
    px = pd.read_csv(STARTER / "prices_daily.csv", usecols=["date", "ticker", "adj_close", "close", "currency"], parse_dates=["date"])
    fx = pd.read_csv(STARTER / "fx_usdcad_daily.csv", parse_dates=["date"]).set_index("date")["usdcad"]
    th_t = pd.read_csv(c.REG / "quant" / "metriques_titres_cad.csv").set_index("Ticker")
    th_s = pd.read_csv(c.REG / "quant" / "metriques_strategies_cad.csv").set_index(px.columns[0] if False else "Stratégie (proxy XBB.TO/XIU.TO/SPY)")
    adj = px.pivot(index="date", columns="ticker", values="adj_close").sort_index()
    ccy = px.drop_duplicates("ticker").set_index("ticker")["currency"]
    non_crypto = [t for t in adj.columns if t not in ("BTC-USD", "ETH-USD")]
    cal = pd.DatetimeIndex(sorted(set(adj[non_crypto].dropna(how="all").index)))
    adj_c = adj.reindex(cal).ffill()
    fx_c = fx.reindex(cal).ffill().bfill()
    cad = adj_c.copy()
    for t in cad.columns:
        if ccy[t] == "USD":
            cad[t] = cad[t] * fx_c
    eng58 = load_returns(TICKERS, start="2021-12", end="2026-09", currency="CAD")
    eng59 = load_returns(TICKERS, start="2021-11", end="2026-09", currency="CAD")
    out = {"n_calendar_days": int(len(cal)), "fx_days_filled": int(fx.reindex(cal).isna().sum()), "assets": {}, "mixes": {}}
    for t in TICKERS:
        v = cad[t]
        o = th_t.loc[t]
        steps = {"1_theirs": {"cagr": float(o.CAGR), "vol": float(o.Vol), "maxdd": float(-o.MaxDD), "ret_2022": float(o["Rdt 2022"])},
                 "2_their_method_recomputed": m_daily(v, 252),
                 "3_end_2026_09_30": m_daily(v[:"2026-09-30"], 252),
                 "4_start_2021_11_30": m_daily(v["2021-11-30":"2026-09-30"], 252)}
        vm = v["2021-11-30":"2026-09-30"].resample("ME").last()
        steps["5_month_end_sampling"] = m_daily(vm, 12)
        steps["6_engine_58m"] = m_monthly(eng58[t])
        steps["7_engine_59m"] = m_monthly(eng59[t])
        aug = {"engine_2022_08": float(eng58.loc["2022-08-31", t]), "starter_month_end_2022_08": float(vm.loc["2022-08-31"] / vm.loc["2022-07-31"] - 1)}
        out["assets"][t] = {"used_by": USED_BY[t], "steps": steps, "aug_2022": aug}
    # CNQ.TO 2022-08-22 detail
    cl = px[px.ticker == "CNQ.TO"].set_index("date")
    d = pd.Timestamp("2022-08-22")
    out["cnq_2022_08_22"] = {"adj_close_return": float(cl.adj_close.pct_change().loc[d]), "close_return": float(cl.close.pct_change().loc[d]),
                             "engine_qa": json.loads((DEFAULT_DATA_DIR / "data_version.json").read_text())["qa"].get("cnq_2022_08_month_return_starter")
                             if (DEFAULT_DATA_DIR / "data_version.json").exists() else None}
    # their BNC strategies
    for k, w in MIXES.items():
        v = monthly_rebal(cad, w)
        o = th_s.loc[THEIR_MIX[k]]
        er = sum(x * eng58[a] for a, x in w.items())
        out["mixes"][k] = {"1_theirs": {"cagr": float(o.CAGR), "vol": float(o.Vol), "maxdd": float(-o.MaxDD), "ret_2022": float(o["Rdt 2022"])},
                           "2_their_method_recomputed": m_daily(v, 252),
                           "3_end_2026_09_30": m_daily(v[:"2026-09-30"], 252),
                           "6_engine_58m_monthly_rebal": m_monthly(er)}
    for t, d_ in out["assets"].items():
        s = d_["steps"]
        print(f"{t:8s}", " | ".join(f"{k[:2]} {v['cagr']:.4f}/{v['vol']:.4f}/{v['maxdd']:.4f}/{v['ret_2022']:+.4f}" for k, v in s.items()), d_["aug_2022"])
    for k, d_ in out["mixes"].items():
        print(k, " | ".join(f"{kk[:2]} {v['cagr']:.4f}/{v['vol']:.4f}/{v['maxdd']:.4f}/{v['ret_2022']:+.4f}" for kk, v in d_.items()))
    print(out["cnq_2022_08_22"], out["n_calendar_days"], out["fx_days_filled"])
    print(c.write("reconcile", out, ["source/.../alphaforge_starter/prices_daily.csv", "source/.../alphaforge_starter/fx_usdcad_daily.csv",
                                     "analyse/relation-profils-actifs/quant/metriques_titres_cad.csv",
                                     "analyse/relation-profils-actifs/quant/metriques_strategies_cad.csv",
                                     "data/long/monthly_returns.parquet"], {"doc": __doc__}))


if __name__ == "__main__":
    main()
