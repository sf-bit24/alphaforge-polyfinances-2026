"""Item 5 - put the regulatory analysis' 2022 finding ("défensive -11,2 % ~ offensive -10,7 %", 10-synthese.md
constat 4) in the long history, with the engine data (data/long, monthly total returns):
  - calendar years where equities AND bonds both lose (USD 1926+: US_MKT vs UST_10Y / UST_5Y;
    CAD 1977+: CA_EQ vs CA_GOV_10Y; and US_MKT in CAD);
  - monthly stock/bond correlation by decade, and share of 36-month rolling windows with a positive correlation;
  - BNC Conservateur (70/9/21) vs Actions (0/30/70) on CA_GOV_10Y / CA_EQ / US_MKT, CAD, calendar years:
    how often the defensive mix lost about as much as (or more than) the offensive one.
Constant mixes rebalanced monthly here (same convention as quant/stats_classes.py), declared. SIMULATION ONLY.
Caveat: synthetic bonds from monthly-AVERAGE yields (pre-1962 US, CA_GOV_10Y) understate volatility; correlations
are descriptive.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
from alphaforge.finance.backtest.data import load_returns  # noqa: E402


def cal_years(R: pd.DataFrame) -> pd.DataFrame:
    Y = (1 + R).groupby(R.index.year).prod() - 1
    n = R.groupby(R.index.year).size()
    return Y[n == 12]


def both_down(Y, eq, bd):
    m = (Y[eq] < 0) & (Y[bd] < 0)
    return {"n_years": int(len(Y)), "first": int(Y.index.min()), "last": int(Y.index.max()),
            "n_both_negative": int(m.sum()), "share": float(m.mean()),
            "years": {int(y): {"equity": round(float(Y.loc[y, eq]), 4), "bonds": round(float(Y.loc[y, bd]), 4)}
                      for y in Y.index[m]},
            "n_equity_negative": int((Y[eq] < 0).sum()),
            "bonds_negative_given_equity_negative": float(((Y[bd] < 0) & (Y[eq] < 0)).sum() / max(1, (Y[eq] < 0).sum()))}


def decade_corr(R, eq, bd):
    out = {}
    for d0 in range(int(R.index.year.min()) // 10 * 10, 2030, 10):
        s = R[(R.index.year >= d0) & (R.index.year < d0 + 10)]
        if len(s) >= 24:
            out[f"{d0}s"] = {"corr": round(float(s[eq].corr(s[bd])), 3), "n_months": int(len(s))}
    roll = R[eq].rolling(36).corr(R[bd]).dropna()
    for k, v in out.items():
        d0 = int(k[:4])
        rr = roll[(roll.index.year >= d0) & (roll.index.year < d0 + 10)]
        v["share_36m_corr_positive"] = round(float((rr > 0).mean()), 3) if len(rr) else None
    return out


def main():
    res, inputs = {}, ["data/long/monthly_returns.parquet"]
    U = load_returns(["US_MKT", "UST_10Y", "UST_5Y", "UST_TBILL"], start="1926-08", currency="USD")
    YU = cal_years(U)
    res["usd_1926"] = {"period": [str(U.index.min().date()), str(U.index.max().date())],
                       "both_down_10y": both_down(YU, "US_MKT", "UST_10Y"),
                       "both_down_5y": both_down(YU, "US_MKT", "UST_5Y"),
                       "decade_corr_10y": decade_corr(U, "US_MKT", "UST_10Y"),
                       "y2022": {k: round(float(YU.loc[2022, k]), 4) for k in YU.columns}}
    C = load_returns(["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL"], start="1977-01", currency="CAD")
    YC = cal_years(C)
    res["cad_1977"] = {"period": [str(C.index.min().date()), str(C.index.max().date())],
                       "both_down_ca": both_down(YC, "CA_EQ", "CA_GOV_10Y"),
                       "both_down_us_in_cad": both_down(YC, "US_MKT", "CA_GOV_10Y"),
                       "decade_corr_ca": decade_corr(C, "CA_EQ", "CA_GOV_10Y"),
                       "y2022": {k: round(float(YC.loc[2022, k]), 4) for k in YC.columns}}
    # BNC defensive vs offensive (monthly rebalanced constant mixes)
    mix = {"conservateur": {"CA_GOV_10Y": .70, "CA_EQ": .09, "US_MKT": .21},
           "equilibre": {"CA_GOV_10Y": .40, "CA_EQ": .18, "US_MKT": .42},
           "actions": {"CA_GOV_10Y": .0, "CA_EQ": .30, "US_MKT": .70}}
    P = pd.DataFrame({k: sum(x * C[a] for a, x in w.items()) for k, w in mix.items()})
    YP = cal_years(P)
    down = YP[YP.actions < 0]
    close_ = (YP.conservateur - YP.actions).abs() <= 0.01
    worse = YP.conservateur <= YP.actions
    res["bnc_cad_1977"] = {
        "n_years": int(len(YP)), "n_actions_negative": int(len(down)),
        "actions_negative_years": {int(y): {k: round(float(down.loc[y, k]), 4) for k in YP.columns} for y in down.index},
        "conservateur_loss_over_actions_loss_in_down_years_median":
            float((down.conservateur.clip(upper=0) / down.actions).median()) if len(down) else None,
        "n_years_conservateur_within_1pt_of_actions": int(close_.sum()),
        "years_within_1pt": [int(y) for y in YP.index[close_]],
        "n_years_conservateur_le_actions_and_both_negative": int((worse & (YP.actions < 0) & (YP.conservateur < 0)).sum()),
        "years_conservateur_le_actions_and_both_negative": [int(y) for y in YP.index[worse & (YP.actions < 0) & (YP.conservateur < 0)]],
        "y2022": {k: round(float(YP.loc[2022, k]), 4) for k in YP.columns}}
    # real tickers, 2022 calendar year (monthly, engine data) to compare with their daily -11,2 / -10,9 / -10,7
    T = load_returns(["XBB.TO", "XIU.TO", "SPY"], start="2021-12", end="2022-12", currency="CAD")
    tm = {"conservateur": {"XBB.TO": .70, "XIU.TO": .09, "SPY": .21}, "equilibre": {"XBB.TO": .40, "XIU.TO": .18, "SPY": .42},
          "actions": {"XBB.TO": 0, "XIU.TO": .30, "SPY": .70}}
    T22 = T.loc["2022-01":"2022-12"]
    res["tickers_2022_monthly_rebal"] = {k: round(float(np.prod(1 + sum(x * T22[a] for a, x in w.items())) - 1), 4)
                                        for k, w in tm.items()}
    res["tickers_2022_corr_xbb_spy_monthly"] = round(float(T22["XBB.TO"].corr(T22["SPY"])), 3)
    res["theirs_2022"] = {"conservateur": -0.112123, "equilibre": -0.108981, "actions": -0.106932,
                          "source": "analyse/relation-profils-actifs/quant/metriques_strategies_cad.csv (daily)"}
    print(pd.Series({k: v["n_both_negative"] for k, v in
                     {"usd10": res["usd_1926"]["both_down_10y"], "usd5": res["usd_1926"]["both_down_5y"],
                      "ca": res["cad_1977"]["both_down_ca"], "uscad": res["cad_1977"]["both_down_us_in_cad"]}.items()}))
    print(res["usd_1926"]["both_down_10y"]["years"])
    print(res["cad_1977"]["both_down_ca"]["years"])
    print(res["usd_1926"]["decade_corr_10y"])
    print(res["cad_1977"]["decade_corr_ca"])
    print({k: v for k, v in res["bnc_cad_1977"].items() if k != "actions_negative_years"})
    print(res["bnc_cad_1977"]["actions_negative_years"])
    print(res["tickers_2022_monthly_rebal"], res["tickers_2022_corr_xbb_spy_monthly"])
    print(c.write("hist2022", res, inputs + ["analyse/relation-profils-actifs/quant/metriques_strategies_cad.csv"],
                  {"doc": __doc__}))


if __name__ == "__main__":
    main()
