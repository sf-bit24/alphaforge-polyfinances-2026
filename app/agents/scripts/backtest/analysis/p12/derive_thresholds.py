"""Derive persona-12 risk thresholds from the data (PROPOSALS to be validated by the team).

Rules (readable):
 A. Accumulation capacity (H_acc = 6 y, retirement at 42): a static mix "e% equity + (1-e)% bond leg" is
    admissible if its longest NOMINAL underwater period on the era <= 12*H_acc months (real underwater is
    reported: in USD 1926+ even T-bills stay below their real peak for decades, so a real rule admits nothing).
    L*_acc = max drawdown of the deepest admissible mix.
 B. Sequence window k*: on every rolling decumulation window (60/40 mix), Spearman correlation between the
    perfect withdrawal rate (PWR) and the real return of the first k years, k = 1..25.
    k* = smallest k whose correlation reaches 90 % of the maximum. k* of the USD era (H=50, 51 yearly starts,
    2 independent windows) is used for both eras: the CAD 40 y estimate rests on ~1 independent window.
 C. Decumulation capacity: C1 = max drawdown of the deepest mix whose longest REAL underwater period <= 12*k*;
    C2 = max drawdown of the mix that maximises the worst-case (min) PWR over the longest horizon of the era.
    Capacity = min(C1, C2). Proposal = the most prudent value across eras (capacity belongs to the person).
 D. Willingness (AMF Q10, inferred [inf] "elevee" -> palier 4 '30 %' or 5 '> 30 %'): 0.30 (lowest inferred).
    Effective limit = min(willingness, capacity) (31-103CP).
SIMULATION ONLY.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from scipy.stats import spearmanr

from common import ERA_CAD, ERA_USD, era_data, first_k_real, longest_underwater, port_returns, pwr_all, write_trace
from alphaforge.finance.backtest import metrics as M

H_ACC = 6
WILL = 0.30


def mixes(era):
    out = []
    for leg in era["legs"]:
        for e in range(0, 101, 10):
            w = {a: x * e / 100 for a, x in era["eq"].items()}
            if e < 100:
                w[leg] = w.get(leg, 0) + 1 - e / 100
            out.append((f"eq{e}_{leg}", e, leg, w))
    return out


def main():
    res, params = {}, {"H_acc": H_ACC, "willingness_Q10_inferred": WILL, "grid": "equity 0..100 step 10 x legs"}
    for era, Hd in ((ERA_USD, 50), (ERA_CAD, 40)):
        assets = list(era["eq"]) + era["legs"]
        R, infl = era_data(assets, era["currency"], era["start"])
        iv = infl.values
        grid = []
        for name, e, leg, w in mixes(era):
            r = port_returns(R, w)
            real = (1 + r) / (1 + iv) - 1
            uw_n, cen_n = longest_underwater(r)
            uw_r, cen_r = longest_underwater(real)
            p = pwr_all(r, iv, 12 * Hd)
            grid.append({"mix": name, "equity": e, "leg": leg, "max_dd": M.max_drawdown(r),
                         "max_dd_real": M.max_drawdown(real), "uw_nominal_m": uw_n, "uw_real_m": uw_r,
                         "uw_real_censored": cen_r, "pwr_min": float(p.min()), "pwr_p10": float(np.quantile(p, .1)),
                         "pwr_median": float(np.median(p)), "n_windows": len(p)})
        # A
        adm = [g for g in grid if g["uw_nominal_m"] <= 12 * H_ACC]
        a_front = max(adm, key=lambda g: g["max_dd"]) if adm else None
        # B (60/40 on the first leg that is a bond: UST_10Y / CA_GOV_10Y)
        leg = "UST_10Y" if era is ERA_USD else "CA_GOV_10Y"
        w6040 = {a: x * .6 for a, x in era["eq"].items()}
        w6040[leg] = .4
        r = port_returns(R, w6040)
        seq = {}
        for H in (30, 40, 50):
            if len(r) < 12 * H + 24:
                continue
            p = pwr_all(r, iv, 12 * H)
            cors = [float(spearmanr(first_k_real(r, iv, 12 * H, 12 * k), p)[0]) for k in range(1, 26)]
            mx = max(cors)
            kstar = next(k + 1 for k, c in enumerate(cors) if c >= .9 * mx)
            seq[H] = {"corr_by_k": cors, "k_star": kstar, "max_corr": mx, "k_at_max": int(np.argmax(cors) + 1),
                      "n_windows": len(p), "independent_windows": len(r) // (12 * H)}
        if era is ERA_USD:
            KSTAR = seq[Hd]["k_star"]
        kstar = KSTAR
        c1_adm = [g for g in grid if g["uw_real_m"] <= 12 * kstar]
        c1 = max(c1_adm, key=lambda g: g["max_dd"]) if c1_adm else None
        c2 = max(grid, key=lambda g: (g["pwr_min"], -g["max_dd"]))
        cap = min(x["max_dd"] for x in (c1, c2) if x)
        res[era["name"]] = {"period": [str(R.index[0].date()), str(R.index[-1].date())], "n_months": len(R),
                            "H_decum_tested": Hd, "grid": grid,
                            "A_accumulation": {"L_star": a_front["max_dd"] if a_front else None, "frontier_mix": a_front,
                                               "admissible": [g["mix"] for g in adm]},
                            "B_sequence": seq, "k_star_used": kstar,
                            "C_decumulation": {"C1": c1, "C2_max_min_pwr": c2, "capacity": cap},
                            "D": {"willingness": WILL,
                                  "effective_accumulation": min(WILL, a_front["max_dd"]) if a_front else WILL,
                                  "effective_decumulation": min(WILL, cap)}}
        print(era["name"], "L*acc", a_front and (a_front["mix"], round(a_front["max_dd"], 3)),
              "k*", {h: s["k_star"] for h, s in seq.items()}, "C1", c1 and (c1["mix"], round(c1["max_dd"], 3)),
              "C2", (c2["mix"], round(c2["max_dd"], 3), round(c2["pwr_min"], 4)))
    acc = min(r["A_accumulation"]["L_star"] for r in res.values())
    dec = min(r["C_decumulation"]["capacity"] for r in res.values())
    res["proposal"] = {"k_star_years": KSTAR,
                       "accumulation": {"capacity": acc, "willingness": WILL, "effective": min(acc, WILL),
                                        "binding": "capacity" if acc < WILL else "willingness"},
                       "decumulation": {"capacity": dec, "willingness": WILL, "effective": min(dec, WILL),
                                        "binding": "capacity" if dec < WILL else "willingness"}}
    print(res["proposal"])
    p = write_trace("derive_thresholds", res, params)
    print(p)


if __name__ == "__main__":
    main()
