"""Persona 14 - threshold derivation by sensitivity (stage A). SIMULATION ONLY - not financial advice.

All portfolios are constant-mix, rebalanced monthly, no costs (pure policy comparison). Metrics = engine.metrics.
Windows = engine.windows (rolling, step 12 months unless stated).

A  capacity grid: equity share 0..100 % of an ex-energy core, per era. Full-sample max drawdown and longest
   peak->recovery (underwater) duration; rolling-window p90 max DD and p10 real return for H = 10 and 16 years.
B  direct energy weight e (US_IND_ENRGY) added to a base ex-energy mix, with an implicit HUMAN-CAPITAL energy
   position (SCENARIO): total wealth T = (1-h) * financial + h * HC, HC monthly return = US_IND_ENRGY return
   (beta 1 on the energy-linked part of household human capital), h in {0, 1/3, 1/2, 2/3}
   (HC_at_risk / financial = 0, 0.5, 1, 2). Constant h = simplification (HC is not marked to market).
C  Canadian equity share c (CA_EQ, contains energy) in the same base, CAD 1977+.
D  employer stock CNQ.TO weight k, CAD 1995-02+, rolling 5 and 10 years, step 3 months: added max drawdown vs k = 0
   in the same window (financial and total wealth), and the same k in US_IND_ENRGY (sector) for comparison.
Outputs: results/p14_analysis/sweep_*.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as K  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alphaforge.finance.backtest import metrics as M  # noqa: E402
from alphaforge.finance.backtest.data import load_inflation, load_returns  # noqa: E402
from alphaforge.finance.backtest.windows import windows  # noqa: E402

H_LIST = [0.0, 1 / 3, 0.5, 2 / 3]


def mix(R, w: dict) -> pd.Series:
    return sum(R[a] * x for a, x in w.items() if x)


def win_stats(r: pd.Series, infl: pd.Series, H: float, step=12) -> pd.DataFrame:
    ws = windows(H, r.index.min(), r.index.max(), "rolling", step, index=r.index)
    out = []
    for w in ws:
        x = r.loc[w.start:w.end]
        out.append({"window": w.label, "maxdd": M.max_drawdown(x),
                    "real": M.annualized_real_return(x.values, infl.reindex(x.index).values)})
    return pd.DataFrame(out)


def eras():
    U = load_returns(["US_MKT_XEN", "US_MKT", "UST_10Y", "US_IND_ENRGY", "UST_TBILL"], "1926-08", "2026-09", "USD")
    C = load_returns(["US_MKT_XEN", "US_MKT", "CA_EQ", "CA_GOV_10Y", "US_IND_ENRGY", "CA_TBILL", "GOLD"], "1977-01", "2026-09", "CAD")
    return {"USD 1926+": (U, load_inflation("USD"), {"eq": {"US_MKT_XEN": 1.0}, "bd": "UST_10Y"}),
            "CAD 1977+": (C, load_inflation("CAD"), {"eq": {"CA_EQ": 0.3, "US_MKT_XEN": 0.7}, "bd": "CA_GOV_10Y"})}


def base_w(spec, s):
    w = {a: s * x for a, x in spec["eq"].items()}
    w[spec["bd"]] = 1 - s
    return w


def part_a():
    rows = []
    for era, (R, infl, spec) in eras().items():
        for s in np.round(np.arange(0, 1.01, 0.1), 2):
            r = mix(R, base_w(spec, s))
            row = {"era": era, "equity": s, "full_maxdd": M.max_drawdown(r), "full_underwater_months": M.max_underwater_months(r),
                   "full_real_maxdd": M.max_drawdown(M.real_returns(r.values, infl.reindex(r.index).values)),
                   "full_real_underwater_months": M.max_underwater_months(M.real_returns(r.values, infl.reindex(r.index).values)),
                   "full_real": M.annualized_real_return(r.values, infl.reindex(r.index).values), "vol": M.volatility(r)}
            for H in (10, 16):
                st = win_stats(r, infl, H)
                row.update({f"h{H}_n": len(st), f"h{H}_maxdd_p90": st.maxdd.quantile(0.9), f"h{H}_maxdd_worst": st.maxdd.max(),
                            f"h{H}_real_p10": st.real.quantile(0.1), f"h{H}_real_median": st.real.median()})
            rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(K.OUT / "sweep_A_capacity.csv", index=False)
    return df


def part_b(base_share=0.6):
    rows = []
    E = [0, 0.025, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30, 0.45]
    for era, (R, infl, spec) in eras().items():
        en = R["US_IND_ENRGY"]
        stress = en <= en.quantile(0.10)
        b = base_w(spec, base_share)
        for e in E:
            fin = mix(R, {a: (1 - e) * x for a, x in b.items()}) + e * en
            for h in H_LIST:
                tot = (1 - h) * fin + h * en
                for H in (10, 16):
                    sf, stt = win_stats(fin, infl, H), win_stats(tot, infl, H)
                    rows.append({"era": era, "base_equity": base_share, "energy_w": e, "h": round(h, 3), "H": H,
                                 "fin_real_p10": sf.real.quantile(0.1), "fin_real_median": sf.real.median(),
                                 "fin_maxdd_p90": sf.maxdd.quantile(0.9), "fin_maxdd_worst": sf.maxdd.max(),
                                 "tot_maxdd_p90": stt.maxdd.quantile(0.9), "tot_maxdd_worst": stt.maxdd.max(),
                                 "tot_full_maxdd": M.max_drawdown(tot),
                                 "fin_mean_in_energy_stress": fin[stress].mean(), "fin_corr_energy": fin.corr(en),
                                 "n_windows": len(sf)})
    df = pd.DataFrame(rows)
    df.to_csv(K.OUT / f"sweep_B_energy_eq{int(base_share*100)}.csv", index=False)
    return df


def part_c(base_share=0.6):
    R, infl, spec = eras()["CAD 1977+"]
    en = R["US_IND_ENRGY"]
    stress = en <= en.quantile(0.10)
    rows = []
    for c in [0, 0.06, 0.1, 0.15, 0.18, 0.2, 0.3, 0.4, 0.5, 0.6]:
        c = min(c, base_share)
        w = {"CA_EQ": c, "US_MKT_XEN": base_share - c, "CA_GOV_10Y": 1 - base_share}
        fin = mix(R, w)
        for h in H_LIST:
            tot = (1 - h) * fin + h * en
            for H in (10, 16):
                sf, stt = win_stats(fin, infl, H), win_stats(tot, infl, H)
                rows.append({"era": "CAD 1977+", "base_equity": base_share, "ca_eq_w": c, "h": round(h, 3), "H": H,
                             "fin_real_p10": sf.real.quantile(0.1), "fin_real_median": sf.real.median(),
                             "fin_maxdd_p90": sf.maxdd.quantile(0.9), "tot_maxdd_p90": stt.maxdd.quantile(0.9),
                             "tot_maxdd_worst": stt.maxdd.max(), "fin_mean_in_energy_stress": fin[stress].mean(),
                             "fin_corr_energy": fin.corr(en)})
    df = pd.DataFrame(rows)
    df.to_csv(K.OUT / f"sweep_C_ca_eq{int(base_share*100)}.csv", index=False)
    return df


def part_d(base_share=0.6):
    R = load_returns(["CNQ.TO", "US_MKT_XEN", "CA_GOV_10Y", "US_IND_ENRGY", "CA_TBILL"], "1995-02", "2026-09", "CAD")
    infl = load_inflation("CAD")
    b = {"US_MKT_XEN": base_share, "CA_GOV_10Y": 1 - base_share}
    en = R["US_IND_ENRGY"]
    rows = []
    for H in (5, 10):
        ref = {}
        for asset in ("CNQ.TO", "US_IND_ENRGY"):
            for k in [0, 0.025, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30, 0.45]:
                fin = mix(R, {a: (1 - k) * x for a, x in b.items()}) + k * R[asset]
                for h in H_LIST:
                    tot = (1 - h) * fin + h * en
                    sf, stt = win_stats(fin, infl, H, step=3), win_stats(tot, infl, H, step=3)
                    key = (H, h)
                    if k == 0 and asset == "CNQ.TO":
                        ref[key] = (sf.maxdd.values, stt.maxdd.values)
                    add_f = sf.maxdd.values - ref[key][0]
                    add_t = stt.maxdd.values - ref[key][1]
                    rows.append({"asset": asset, "H": H, "k": k, "h": round(h, 3), "n_windows": len(sf),
                                 "fin_maxdd_worst": sf.maxdd.max(), "fin_add_dd_worst": add_f.max(), "fin_add_dd_p90": np.quantile(add_f, 0.9),
                                 "tot_add_dd_worst": add_t.max(), "tot_maxdd_worst": stt.maxdd.max(),
                                 "fin_real_p10": sf.real.quantile(0.1), "fin_real_median": sf.real.median(),
                                 "worst_window_fin": sf.loc[add_f.argmax(), "window"]})
    df = pd.DataFrame(rows)
    df.to_csv(K.OUT / f"sweep_D_cnq_eq{int(base_share*100)}.csv", index=False)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 500)
    what = sys.argv[1:] or ["A", "B", "C", "D"]
    share = 0.6
    for a in what:
        if a.startswith("eq="):
            share = float(a[3:])
    if "A" in what:
        print(part_a().round(4).to_string())
    if "B" in what:
        print(part_b(share).round(4).to_string())
    if "C" in what:
        print(part_c(share).round(4).to_string())
    if "D" in what:
        print(part_d(share).round(4).to_string())
