"""Persona 35 - pocket B (patrimoine 15-20 ans): derived thresholds (PROPOSALS to validate by the team).

1. CAPACITY of loss (rule, readable): a static mix is admissible if its longest underwater period (nominal TWR,
   peak -> recovery, annual rebalancing) over the whole era is <= 96 months = 8 years, the LOWER bound of the
   remaining Florida winters ("sejours prevus encore ~8-10 ans"): a loss must be recovered while the USD
   spending still runs. L_cap = max drawdown of the deepest admissible mix. Grid: e = 0..100 % equity (step 5),
   currency-matched u = 50 % (half CA / half US on each leg), bond legs 10y, 5y-US/10y-CA, T-bills.
   Eras: CAD 1977+ (real USDCAD) and USD 1926+ (US-only legs: robustness of asset classes, says nothing on FX).
   Sensitivity: 120 months (10 winters) and 180 months (15-year horizon).
2. WILLINGNESS: AMF Q10 inferred "15 %" [inf] (personas-lot3.md, poche B) -> L_will = 0.15.
   Final limit = min(L_will, L_cap) (31-103CP: lower of tolerance and capacity).
3. GOLD cap (status 'limite'): base e40/u50 (CA_EQ, US_MKT, CA_GOV_10Y, UST_5Y), gold g = 0..25 % pro-rata,
   rolling 15y windows step 12m (1977+), 4 %/yr basket-real withdrawals (s = 0.5).
   Rule: g_cap = largest g such that p10 of final basket-real wealth improves at every 5-pt step up to g
   AND the drawdown-limit breach rate is not above the g = 0 rate.
4. SECTOR satellite (proxy of 'titres connus' defensifs: US_IND_NODUR + US_IND_HLTH, US side) - same rule.
5. SEQUENCE: P(depletion) and worst final real wealth for withdrawal rates 3 / 4 / 5 / 6.9 % over 15 and 20 y.
Outputs results/p35_analysis/derive_b.json. SIMULATION ONLY.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

import common as C
from alphaforge.finance.backtest import metrics as M
from alphaforge.finance.backtest.data import load_returns

L_WILL = 0.15


def sim(R: pd.DataFrame, w: dict, rebal: int = 12) -> np.ndarray:
    """Static mix, rebalanced every `rebal` months (drift in between), 10 bps per unit traded."""
    a = list(w)
    X = R[a].values
    tgt = np.array([w[k] for k in a])
    cur = tgt.copy()
    out = np.empty(len(X))
    for i in range(len(X)):
        cost = 0.0
        if i % rebal == 0 and i > 0:
            cost = 1e-3 * np.abs(tgt - cur).sum()
            cur = tgt.copy()
        g = float(cur @ X[i])
        out[i] = g - cost
        cur = cur * (1 + X[i]) / (1 + g)
    return out


def longest_underwater(r: np.ndarray) -> int:
    dd = M.drawdown_series(r)
    best = cur = 0
    for x in dd:
        cur = cur + 1 if x > 1e-12 else 0
        best = max(best, cur)
    return best


def capacity(era: str) -> dict:
    if era == "cad_1977":
        R = load_returns(["CA_EQ", "US_MKT", "CA_GOV_10Y", "UST_10Y", "UST_5Y", "CA_TBILL", "UST_TBILL"],
                         "1977-01", "2026-09", "CAD")
        legs = {"10y": {"CA_GOV_10Y": .5, "UST_10Y": .5}, "ca10_us5": {"CA_GOV_10Y": .5, "UST_5Y": .5},
                "tbills": {"CA_TBILL": .5, "UST_TBILL": .5}}
        eq = {"CA_EQ": .5, "US_MKT": .5}
    else:
        R = load_returns(["US_MKT", "UST_10Y", "UST_5Y", "UST_TBILL"], "1926-07", "2026-09", "USD")
        legs = {"10y": {"UST_10Y": 1.0}, "5y": {"UST_5Y": 1.0}, "tbills": {"UST_TBILL": 1.0}}
        eq = {"US_MKT": 1.0}
    grid = []
    for leg, lw in legs.items():
        for e in np.round(np.arange(0, 1.0001, 0.05), 2):
            w = {k: e * v for k, v in eq.items()}
            for k, v in lw.items():
                w[k] = w.get(k, 0) + (1 - e) * v
            r = sim(R, w)
            grid.append({"leg": leg, "equity": float(e), "max_dd": M.max_drawdown(r),
                         "longest_underwater_months": longest_underwater(r)})
    g = pd.DataFrame(grid)
    res = {"period": [str(R.index.min().date()), str(R.index.max().date())], "grid": grid, "rules": {}}
    for lim in (96, 120, 180):
        ok = g[g.longest_underwater_months <= lim]
        if len(ok):
            fr = ok.loc[ok.max_dd.idxmax()]
            res["rules"][f"underwater_le_{lim}m"] = {
                "L_cap": float(fr.max_dd), "frontier_mix": {"leg": fr.leg, "equity": float(fr.equity)},
                "frontier_underwater": int(fr.longest_underwater_months),
                "max_equity_admissible_by_leg": {l: float(ok[ok.leg == l].equity.max()) if (ok.leg == l).any() else None
                                                 for l in legs}}
    return res


def rolling_wealth(r: np.ndarray, b: np.ndarray, H: int, rate: float, step: int = 12):
    n = 12 * H
    fw, dep, dd = [], [], []
    for i in range(0, len(r) - n + 1, step):
        w = C.wealth_with_withdrawals(r[i:i + n], b[i:i + n], rate)
        fw.append(w[-1])
        dep.append(w[-1] <= 0)
        dd.append(M.max_drawdown(r[i:i + n]))
    return np.array(fw), np.array(dep), np.array(dd)


def sweep(R, b, base: dict, add: dict, label: str, limit: float) -> dict:
    rows = []
    for g in np.round(np.arange(0, 0.2501, 0.05), 2):
        w = {k: v * (1 - g) for k, v in base.items()}
        for k, v in add.items():
            w[k] = w.get(k, 0) + g * v
        r = sim(R, w)
        fw, dep, dd = rolling_wealth(r, b, 15, 0.04)
        rows.append({"share": float(g), "final_real_wealth_p10": float(np.quantile(fw, .1)),
                     "final_real_wealth_worst": float(fw.min()), "final_real_wealth_median": float(np.median(fw)),
                     "breach_rate_maxdd": float(np.mean(dd > limit)), "worst_maxdd": float(dd.max()),
                     "n_windows": int(len(fw))})
    cap = 0.0
    for i in range(1, len(rows)):
        if rows[i]["final_real_wealth_p10"] >= rows[i - 1]["final_real_wealth_p10"] and \
                rows[i]["breach_rate_maxdd"] <= rows[0]["breach_rate_maxdd"] + 1e-9:
            cap = rows[i]["share"]
        else:
            break
    return {"label": label, "rows": rows, "derived_cap": cap}


def main() -> dict:
    out = {"L_will": L_WILL, "L_will_source": "personas-lot3.md, persona 35 poche B: Q10 moderee ~15 % [inf] -> 3"}
    out["capacity"] = {"cad_1977": capacity("cad_1977"), "usd_1926": capacity("usd_1926")}
    caps = [out["capacity"][e]["rules"]["underwater_le_96m"]["L_cap"] for e in out["capacity"]]
    L_cap = min(caps)
    out["L_cap_most_prudent_96m"] = L_cap
    out["L_final"] = min(L_WILL, L_cap)
    out["binding"] = "willingness (AMF Q10)" if L_WILL <= L_cap else "capacity"
    R = load_returns(["CA_EQ", "US_MKT", "CA_GOV_10Y", "UST_5Y", "GOLD", "US_IND_NODUR", "US_IND_HLTH", "CA_TBILL",
                      "UST_TBILL"], "1977-01", "2026-09", "CAD")
    b = C.basket_inflation(0.5, "CAD").reindex(R.index).values
    base = {"CA_EQ": .2, "US_MKT": .2, "CA_GOV_10Y": .3, "UST_5Y": .3}
    out["gold"] = sweep(R, b, base, {"GOLD": 1.0}, "gold pro-rata into e40/u50", out["L_final"])
    out["sectors"] = sweep(R, b, base, {"US_IND_NODUR": .5, "US_IND_HLTH": .5}, "US defensive sectors pro-rata",
                           out["L_final"])
    # sequence risk for a few mixes
    seq = {}
    mixes = {"e20_u50": {"CA_EQ": .1, "US_MKT": .1, "CA_GOV_10Y": .4, "UST_5Y": .4},
             "e30_u50": {"CA_EQ": .15, "US_MKT": .15, "CA_GOV_10Y": .35, "UST_5Y": .35},
             "e40_u50": base, "e60_u50": {"CA_EQ": .3, "US_MKT": .3, "CA_GOV_10Y": .2, "UST_5Y": .2},
             "cash_u50": {"CA_TBILL": .5, "UST_TBILL": .5}}
    for name, w in mixes.items():
        r = sim(R, w)
        seq[name] = {}
        for H in (15, 20):
            for rate in (0.03, 0.04, 0.05, 0.069):
                fw, dep, dd = rolling_wealth(r, b, H, rate)
                seq[name][f"H{H}_w{rate:g}"] = {"p_depletion": float(dep.mean()), "final_real_wealth_worst": float(fw.min()),
                                                "final_real_wealth_p10": float(np.quantile(fw, .1)),
                                                "final_real_wealth_median": float(np.median(fw)), "n": int(len(fw))}
            fw, dep, dd = rolling_wealth(r, b, H, 0.04)
            seq[name][f"H{H}_maxdd_worst"] = float(dd.max())
            seq[name][f"H{H}_breach_rate_Lfinal"] = float(np.mean(dd > out["L_final"]))
    out["sequence"] = seq
    out["withdrawal_scenarios"] = {"base": 0.04, "note": "share of initial pocket B per year, indexed to the "
                                   "spending basket (s=0.5); 0.069 = all USD spending (32 000 USD x USDCAD 1.396 "
                                   "2026-10 / pocket B 645 300 CAD) funded by the portfolio (scenario)"}
    return out


if __name__ == "__main__":
    res = main()
    p = C.write_trace("derive_b", res, {"L_will": L_WILL, "underwater_rules_months": [96, 120, 180],
                                        "basket_s": 0.5, "withdrawal_base": 0.04}, "derive_b.py")
    for e, c in res["capacity"].items():
        print(e, c["period"], {k: v for k, v in c["rules"].items()})
    print("L_cap", res["L_cap_most_prudent_96m"], "L_final", res["L_final"], res["binding"])
    for k in ("gold", "sectors"):
        print(k, "cap", res[k]["derived_cap"])
        for r in res[k]["rows"]:
            print("   ", {a: round(b, 4) if isinstance(b, float) else b for a, b in r.items()})
    for n, d in res["sequence"].items():
        print(n, {k: (round(v['p_depletion'], 3), round(v['final_real_wealth_worst'], 3), round(v['final_real_wealth_median'], 3)) if isinstance(v, dict) else round(v, 3) for k, v in d.items()})
    print(p)
