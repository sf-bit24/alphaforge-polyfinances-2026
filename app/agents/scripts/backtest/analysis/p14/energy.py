"""Persona 14 - energy factor diagnostics (no portfolio optimisation here). SIMULATION ONLY.

E1 correlations of the energy sector with the rest, all months vs stress months
   stress = months where the energy asset is in its worst decile (rule: worst 10 % of monthly returns of the sample),
   co-move = mean return of the other asset in those months; also "energy deep drawdown" regime (energy DD < -30 %).
E2 drawdown episodes (depth >= 30 %) of US_IND_ENRGY (USD 1926+), XOM (USD 1962+), CNQ.TO / ENB.TO (CAD 1995+)
E3 statistical (return-based) estimate of the energy loading of CA_EQ and XIU.TO: non-negative least squares of
   USD returns on the 12 KF US industries, weights summing to 1, by 10-year block. NOT holdings data.
Outputs: results/p14_analysis/energy_*.csv / .json
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as K  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.optimize import minimize  # noqa: E402

from alphaforge.finance.backtest.data import load_returns  # noqa: E402

IND = ["US_IND_NODUR", "US_IND_DURBL", "US_IND_MANUF", "US_IND_ENRGY", "US_IND_CHEMS", "US_IND_BUSEQ",
       "US_IND_TELCM", "US_IND_UTILS", "US_IND_SHOPS", "US_IND_HLTH", "US_IND_MONEY", "US_IND_OTHER"]


def co_moves(R: pd.DataFrame, en: str, others: list[str], era: str) -> list[dict]:
    q = R[en].quantile(0.10)
    stress = R[en] <= q
    dd = K.drawdown(R[en])
    deep = dd < -0.30
    rows = []
    for o in others:
        rows.append({"era": era, "energy": en, "other": o, "start": R.index.min().date(), "end": R.index.max().date(),
                     "n_months": len(R), "corr_all": R[en].corr(R[o]),
                     "corr_stress_decile": R.loc[stress, en].corr(R.loc[stress, o]),
                     "n_stress": int(stress.sum()), "energy_mean_stress": R.loc[stress, en].mean(),
                     "other_mean_stress": R.loc[stress, o].mean(), "other_mean_all": R[o].mean(),
                     "other_share_neg_stress": float((R.loc[stress, o] < 0).mean()),
                     "n_deep_dd_months": int(deep.sum()),
                     "other_mean_deep_dd": R.loc[deep, o].mean() if deep.any() else np.nan})
    return rows


def nnls_sum1(y, X):
    k = X.shape[1]
    f = lambda w: float(((y - X @ w) ** 2).sum())
    res = minimize(f, np.full(k, 1 / k), bounds=[(0, 1)] * k, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   method="SLSQP", options={"maxiter": 500, "ftol": 1e-12})
    w = res.x
    r2 = 1 - ((y - X @ w) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return w, r2


def main():
    rows = []
    U = load_returns(["US_IND_ENRGY", "US_MKT_XEN", "US_MKT", "UST_10Y", "UST_2Y", "CORP_AAA", "UST_TBILL"],
                     "1926-07", None, "USD")
    rows += co_moves(U, "US_IND_ENRGY", ["US_MKT_XEN", "US_MKT", "UST_10Y", "UST_2Y", "CORP_AAA", "UST_TBILL"], "USD 1926+")
    G = load_returns(["US_IND_ENRGY", "US_MKT_XEN", "GOLD", "UST_10Y"], "1975-01", None, "USD")
    rows += co_moves(G, "US_IND_ENRGY", ["GOLD"], "USD 1975+")
    C = load_returns(["US_IND_ENRGY", "CA_EQ", "US_MKT_XEN", "CA_GOV_10Y", "CA_TBILL", "GOLD", "UST_5Y"], "1977-01", None, "CAD")
    rows += co_moves(C, "US_IND_ENRGY", ["CA_EQ", "US_MKT_XEN", "CA_GOV_10Y", "CA_TBILL", "GOLD", "UST_5Y"], "CAD 1977+")
    # real tickers, CAD, long sample of each pair (yfinance before 2021-12, starter after)
    tick_o = ["SPY", "XIU.TO", "XBB.TO", "GLD", "AGG", "QQQ", "ZST.TO", "ESGV", "JNJ", "PG"]
    for en in ["CNQ.TO", "ENB.TO", "XOM"]:
        for o in tick_o:
            R = load_returns([en, o], None, "2026-09", "CAD")
            rows += co_moves(R, en, [o], f"CAD tickers {R.index.min():%Y-%m}+")
    for en in ["CNQ.TO", "ENB.TO", "XOM"]:
        others = [o for o in ["CNQ.TO", "ENB.TO", "XOM"] + tick_o if o != en]
        R = load_returns([en] + others, "2021-11", "2026-09", "CAD")
        rows += co_moves(R, en, others, "CAD 2021-12..2026-09")
    co = pd.DataFrame(rows)
    co.to_csv(K.OUT / "energy_comoves.csv", index=False)

    # E2 episodes
    ep = []
    for a, cur, st in [("US_IND_ENRGY", "USD", "1926-07"), ("US_IND_ENRGY", "CAD", "1971-02"), ("XOM", "USD", None),
                       ("CNQ.TO", "CAD", None), ("ENB.TO", "CAD", None), ("XIU.TO", "CAD", None), ("CA_EQ", "CAD", None)]:
        r = load_returns([a], st, "2026-09", cur)[a]
        e = K.episodes(r, 0.30)
        e.insert(0, "asset", f"{a} ({cur})")
        ep.append(e)
    ep = pd.concat(ep, ignore_index=True)
    ep.to_csv(K.OUT / "energy_episodes.csv", index=False)

    # E3 style estimate of the energy loading
    st = []
    for target, start in [("CA_EQ", "1977-01"), ("XIU.TO", "1999-12")]:
        R = load_returns([target] + IND, start, "2026-09", "USD")
        blocks = list(range(R.index.min().year, 2027, 10))
        for b in blocks:
            seg = R[(R.index.year >= b) & (R.index.year < b + 10)]
            if len(seg) < 36:
                continue
            w, r2 = nnls_sum1(seg[target].values, seg[IND].values)
            st.append({"target": target, "block": f"{seg.index.min():%Y-%m}..{seg.index.max():%Y-%m}", "n": len(seg),
                       "energy_loading": round(float(w[IND.index("US_IND_ENRGY")]), 4), "r2": round(float(r2), 3),
                       "top3": "; ".join(f"{IND[i]} {w[i]:.2f}" for i in np.argsort(-w)[:3])})
        w, r2 = nnls_sum1(R[target].values, R[IND].values)
        st.append({"target": target, "block": f"full {R.index.min():%Y-%m}..{R.index.max():%Y-%m}", "n": len(R),
                   "energy_loading": round(float(w[IND.index("US_IND_ENRGY")]), 4), "r2": round(float(r2), 3),
                   "top3": "; ".join(f"{IND[i]} {w[i]:.2f}" for i in np.argsort(-w)[:3])})
    st = pd.DataFrame(st)
    st.to_csv(K.OUT / "energy_style_ca_eq.csv", index=False)
    pd.set_option("display.width", 220, "display.max_columns", 30, "display.max_rows", 200)
    print(co[co.era.isin(["USD 1926+", "USD 1975+", "CAD 1977+"])].round(4).to_string())
    print(co[co.era.str.startswith("CAD tickers")].round(3)[["era", "energy", "other", "n_months", "corr_all", "other_mean_stress", "energy_mean_stress", "other_share_neg_stress"]].to_string())
    print(co[co.era == "CAD 2021-12..2026-09"].round(3)[["energy", "other", "corr_all", "other_mean_stress", "energy_mean_stress"]].to_string())
    print(ep.to_string())
    print(st.to_string())


if __name__ == "__main__":
    main()
