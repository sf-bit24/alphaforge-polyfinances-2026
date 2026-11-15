"""Persona 14 - household view: layoff buffer under energy busts + total-wealth (human capital) scenario.
SIMULATION ONLY - not financial advice. All personal amounts are FICTIONAL persona facts; the human-capital model is a
declared SCENARIO, not a measurement.

H1 buffer assets during energy busts: return and max drawdown of each buffer candidate over every energy drawdown
   episode (peak -> trough, depth >= 30 %, energy_episodes.csv) and in the worst-decile energy months.
H2 buffer sizing table: episode duration D (months peak -> trough) x share phi of household spending no longer
   covered by income during the bust (scenario 0.25 / 0.5 / 1.0). Household spending itself is MISSING INFO.
H3 cost of holding the buffer in cash: real return of CA_TBILL / ZST.TO per year (inflation cost).
H4 total wealth T = (1-h) * F + h * HC with HC return = US_IND_ENRGY (beta 1 on the energy-linked part of human
   capital), h in {1/3, 1/2, 2/3}. Financial states F (monthly rebalanced, CAD 1995-02+):
   S0 current (CNQ.TO 45 % = 140k / 310k persona fact, rest = ex-energy 60/40 core), S0+request (+10 % ENB.TO +10 % XOM),
   S1 CNQ 20 %, S2 CNQ 5 %, S3 CNQ 2.5 %, S4 CNQ 0. Long-history twin (USD 1926+): US_IND_ENRGY stands in for CNQ.
Outputs: results/p14_analysis/household_*.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as K  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import metrics as M  # noqa: E402
from engine.data import load_inflation, load_returns  # noqa: E402

CORE_CAD = {"CA_EQ": 0.18, "US_MKT_XEN": 0.42, "CA_GOV_10Y": 0.40}
CORE_USD = {"US_MKT_XEN": 0.60, "UST_5Y": 0.20, "UST_10Y": 0.20}


def seg_stats(r: pd.Series, a, b):
    x = r.loc[a:b]
    if len(x) == 0 or x.isna().any():
        return np.nan, np.nan
    return float((1 + x).prod() - 1), M.max_drawdown(x.values)


def h1_h2_h3():
    ep = pd.read_csv(K.OUT / "energy_episodes.csv")
    ep = ep[ep.asset.isin(["US_IND_ENRGY (CAD)", "CNQ.TO (CAD)"])]
    cands = ["CA_TBILL", "CA_GOV_10Y", "UST_TBILL", "UST_2Y", "ZST.TO", "XBB.TO", "CA_EQ", "US_MKT_XEN"]
    rows = []
    for c in cands:
        r = load_returns([c], "1971-02", "2026-09", "CAD")[c]
        for _, e in ep.iterrows():
            ret, dd = seg_stats(r, pd.Timestamp(e.peak) + pd.offsets.MonthEnd(1), e.trough)
            rows.append({"asset": c, "episode": f"{e.asset} {e.peak[:7]}..{e.trough[:7]}", "depth_energy": e.depth,
                         "months": e.months_peak_to_trough, "cum_return": ret, "max_dd": dd})
    h1 = pd.DataFrame(rows)
    h1.to_csv(K.OUT / "household_buffer_episodes.csv", index=False)
    # worst-decile energy months (CAD 1977+ for proxies, own sample for ZST.TO/XBB.TO)
    rows = []
    for c in cands:
        R = load_returns(["US_IND_ENRGY", c], "1971-02", "2026-09", "CAD")
        s = R.US_IND_ENRGY <= R.US_IND_ENRGY.quantile(0.10)
        rows.append({"asset": c, "start": R.index.min().date(), "n_stress": int(s.sum()), "mean_stress": R.loc[s, c].mean(),
                     "worst_stress": R.loc[s, c].min(), "share_neg_stress": float((R.loc[s, c] < 0).mean())})
    pd.DataFrame(rows).to_csv(K.OUT / "household_buffer_stress_months.csv", index=False)
    # H2 sizing
    D = ep.months_peak_to_trough
    stats = {"median": float(D.median()), "p75": float(D.quantile(0.75)), "max": float(D.max()), "min": float(D.min()), "n": int(len(D))}
    rows = [{"duration_stat": k, "D_months": v, **{f"phi={p}": round(v * p, 1) for p in (0.25, 0.5, 1.0)}}
            for k, v in stats.items() if k != "n"]
    h2 = pd.DataFrame(rows)
    h2.to_csv(K.OUT / "household_buffer_sizing.csv", index=False)
    # H3 inflation cost
    rows = []
    infl = load_inflation("CAD")
    for c, a, b in [("CA_TBILL", "1977-01", "2026-09"), ("CA_TBILL", "2021-12", "2026-09"), ("ZST.TO", "2011-04", "2026-09"),
                    ("ZST.TO", "2021-12", "2026-09")]:
        r = load_returns([c], a, b, "CAD")[c]
        rr = M.real_returns(r.values, infl.reindex(r.index).values)
        rows.append({"asset": c, "period": f"{a}..{b}", "ann_nominal": M.annualized_return(r.values),
                     "ann_real": M.annualized_real_return(r.values, infl.reindex(r.index).values),
                     "real_max_dd": M.max_drawdown(rr), "n_months": len(r)})
    h3 = pd.DataFrame(rows)
    h3.to_csv(K.OUT / "household_buffer_inflation.csv", index=False)
    return h1, stats, h2, h3


def states_cad():
    def st(cnq, extra=None):
        extra = extra or {}
        rest = 1 - cnq - sum(extra.values())
        w = {a: rest * x for a, x in CORE_CAD.items()}
        w["CNQ.TO"] = cnq
        w.update(extra)
        return w
    return {"S0_actuel_cnq45": st(0.45), "S0_plus_demande_enb10_xom10": st(0.45, {"ENB.TO": 0.10, "XOM": 0.10}),
            "S1_cnq20": st(0.20), "S2_cnq5": st(0.05), "S3_cnq2.5": st(0.025), "S4_cnq0": st(0.0)}


def h4():
    R = load_returns(["CNQ.TO", "ENB.TO", "XOM", "US_IND_ENRGY"] + list(CORE_CAD), "1995-02", "2026-09", "CAD")
    eps = [("2008-07", "2009-02"), ("2014-07", "2015-09"), ("2018-08", "2020-03"), ("2022-01", "2022-12")]
    rows = []
    for name, w in states_cad().items():
        F = sum(R[a] * x for a, x in w.items() if x)
        for h in (0.0, 1 / 3, 0.5, 2 / 3):
            T = (1 - h) * F + h * R["US_IND_ENRGY"]
            row = {"era": "CAD 1995-02..2026-09", "state": name, "h": round(h, 3), "fin_maxdd": M.max_drawdown(F.values),
                   "tot_maxdd": M.max_drawdown(T.values), "fin_ann_real": M.annualized_real_return(F.values, load_inflation("CAD").reindex(F.index).values),
                   "fin_corr_energy": F.corr(R["US_IND_ENRGY"])}
            for a, b in eps:
                row[f"fin_{a[:4]}"] = seg_stats(F, a, b)[0]
                row[f"tot_{a[:4]}"] = seg_stats(T, a, b)[0]
            rows.append(row)
    # long twin: US_IND_ENRGY stands in for the employer stock
    U = load_returns(["US_IND_ENRGY"] + list(CORE_USD), "1926-08", "2026-09", "USD")
    for e in (0.45, 0.20, 0.05, 0.025, 0.0):
        F = (1 - e) * sum(U[a] * x for a, x in CORE_USD.items()) + e * U["US_IND_ENRGY"]
        for h in (0.0, 1 / 3, 0.5, 2 / 3):
            T = (1 - h) * F + h * U["US_IND_ENRGY"]
            rows.append({"era": "USD 1926-08..2026-09 (energy sector stands in for CNQ)", "state": f"energy{e}", "h": round(h, 3),
                         "fin_maxdd": M.max_drawdown(F.values), "tot_maxdd": M.max_drawdown(T.values),
                         "fin_ann_real": M.annualized_real_return(F.values, load_inflation("USD").reindex(F.index).values),
                         "fin_corr_energy": F.corr(U["US_IND_ENRGY"])})
    df = pd.DataFrame(rows)
    df.to_csv(K.OUT / "household_total_wealth.csv", index=False)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 300)
    h1, stats, h2, h3 = h1_h2_h3()
    print(h1.pivot_table(index="episode", columns="asset", values="cum_return").round(4).to_string())
    print(h1.groupby("asset")[["cum_return", "max_dd"]].agg(["min", "max"]).round(4))
    print(pd.read_csv(K.OUT / "household_buffer_stress_months.csv").round(4).to_string())
    print(stats); print(h2.to_string()); print(h3.round(4).to_string())
    print(h4().round(4).to_string())
