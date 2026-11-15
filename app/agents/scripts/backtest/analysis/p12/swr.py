"""Persona 12 decumulation: withdrawal sustainability, sequence risk, bootstrap, flexibility, stress 2022,
retirement-age sensitivity and a withdrawal-aware hindsight ORACLE (hindsight=True, non investable).

Withdrawals: annual rate x initial wealth, paid monthly at month end, indexed to the era CPI. Exhaustion =
wealth <= 0 before the end of the horizon. Portfolios = constant mixes rebalanced monthly (declared simplification)
unless stated. Every number goes to results/p12_analysis/swr.json. SIMULATION ONLY - model, not a forecast.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np

from common import BNC, bnc_weights, era_data, port_returns, pwr_all, simulate, write_trace
from alphaforge.finance.backtest.data import load_inflation, load_returns

RATES = [0.025, 0.03, 0.035, 0.04, 0.045, 0.05]
SEED = 42
K_STAR = 11   # results/p12_analysis/derive_thresholds.json -> proposal.k_star_years


def eras():
    usd_assets = ["US_MKT", "UST_TBILL", "UST_2Y", "UST_5Y", "UST_10Y"]
    cad_assets = ["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL", "UST_5Y", "GOLD"]
    usd = {"name": "usd_1926", "R": era_data(usd_assets, "USD", "1926-08"), "H": [30, 40, 48, 50, 52, 55]}
    cad = {"name": "cad_1977", "R": era_data(cad_assets, "CAD", "1977-01"), "H": [30, 40]}
    pf_usd = {f"eq{e}_{leg}": ({"US_MKT": e / 100, leg: 1 - e / 100} if e < 100 else {"US_MKT": 1.0})
              for e in range(0, 101, 10) for leg in ["UST_TBILL", "UST_5Y", "UST_10Y"]}
    pf_usd.update({f"bnc_{k.lower()}": {"UST_10Y": f, "US_MKT": c + g} for k, (f, c, g) in BNC.items()})
    pf_cad = {}
    for e in range(0, 101, 10):
        for leg in ["CA_GOV_10Y", "CA_TBILL", "UST_5Y"]:
            w = {"CA_EQ": .3 * e / 100, "US_MKT": .7 * e / 100}
            if e < 100:
                w[leg] = 1 - e / 100
            pf_cad[f"eq{e}_{leg}"] = w
    pf_cad.update({f"bnc_{k.lower()}": bnc_weights(k, "CA_GOV_10Y", "CA_EQ", "US_MKT") for k in BNC})
    pf_cad["eq60_gold5_bond35"] = {"CA_EQ": .18, "US_MKT": .42, "GOLD": .05, "CA_GOV_10Y": .35}
    pf_cad["eq100_us"] = {"US_MKT": 1.0}
    usd["pf"], cad["pf"] = pf_usd, pf_cad
    return [usd, cad]


def stats(p, R, months):
    jan = np.array([i for i, d in enumerate(R.index[:len(p)]) if d.month == 1])
    out = {"n_windows_monthly": len(p), "n_windows_annual": len(jan), "n_independent": len(R) // months,
           "pwr_min": float(p.min()), "pwr_p05": float(np.quantile(p, .05)), "pwr_p10": float(np.quantile(p, .10)),
           "pwr_median": float(np.median(p)), "worst_start": str(R.index[int(np.argmin(p))].date()),
           "fail": {str(r): float(np.mean(p < r)) for r in RATES},
           "fail_annual_starts": {str(r): float(np.mean(p[jan] < r)) for r in RATES}}
    return out


def stationary_bootstrap(n_obs, n_paths, length, mean_block, rng):
    idx = np.empty((n_paths, length), dtype=int)
    p = 1.0 / mean_block
    cur = rng.integers(0, n_obs, n_paths)
    for t in range(length):
        if t > 0:
            new = rng.random(n_paths) < p
            cur = np.where(new, rng.integers(0, n_obs, n_paths), (cur + 1) % n_obs)
        idx[:, t] = cur
    return idx


def main():
    rng = np.random.default_rng(SEED)
    out = {"rates": RATES, "eras": {}}
    E = eras()
    for era in E:
        R, infl = era["R"]
        iv = infl.values
        res = {"period": [str(R.index[0].date()), str(R.index[-1].date())], "n_months": len(R), "tables": {}}
        for H in era["H"]:
            if len(R) < 12 * H + 12:
                continue
            tab = {}
            for name, w in era["pf"].items():
                p = pwr_all(port_returns(R, w), iv, 12 * H)
                tab[name] = stats(p, R, 12 * H)
            best_min = max(tab, key=lambda k: tab[k]["pwr_min"])
            best_p10 = max(tab, key=lambda k: tab[k]["pwr_p10"])
            res["tables"][str(H)] = {"portfolios": tab, "best_by_min": best_min, "best_by_p10": best_p10}
            print(era["name"], H, "n", tab[best_min]["n_windows_monthly"], "indep", tab[best_min]["n_independent"],
                  "best_min", best_min, round(tab[best_min]["pwr_min"], 4), "best_p10", best_p10, round(tab[best_p10]["pwr_p10"], 4),
                  "| eq100", round(tab["eq100_" + ("UST_TBILL" if era["name"] == "usd_1926" else "CA_GOV_10Y")]["pwr_min"], 4))
        out["eras"][era["name"]] = res

    # ---- bootstrap (USD 1926+, joint months of assets and CPI) ----
    usd = E[0]
    R, infl = usd["R"]
    X, iv = R.values, infl.values
    boot = {}
    pick = ["eq100_UST_TBILL", "bnc_croissance", "bnc_equilibre", "eq60_UST_5Y", "eq70_UST_5Y", "eq40_UST_5Y", "bnc_conservateur"]
    for mb in (60, 120):
        idx = stationary_bootstrap(len(X), 4000, 660, mb, rng)   # 55 y max horizon
        res = {}
        for name in pick:
            w = usd["pf"][name]
            r = port_returns(R, w)
            rp, ip = r[idx], iv[idx]
            row = {}
            for H in (30, 40, 50, 55):
                lv = np.cumsum(np.log1p(rp[:, :12 * H]), 1)
                li = np.cumsum(np.log1p(ip[:, :12 * H]), 1)
                pw = 12 / np.exp(li - lv).sum(1)
                row[str(H)] = {"fail": {str(q): float(np.mean(pw < q)) for q in RATES},
                               "pwr_p10": float(np.quantile(pw, .1)), "pwr_p05": float(np.quantile(pw, .05)),
                               "pwr_median": float(np.median(pw))}
            res[name] = row
        boot[str(mb)] = res
        print("boot", mb, {n: res[n]["50"]["fail"]["0.04"] for n in res})
    out["bootstrap_usd"] = {"n_paths": 4000, "seed": SEED, "method": "stationary bootstrap (Politis-Romano), joint monthly rows",
                            "results": boot}

    # ---- flexibility, glidepath (USD 1926+, H = 50, monthly starts) ----
    assets = list(R.columns)
    vec = lambda d: np.array([d.get(a, 0.0) for a in assets])
    H = 50
    starts = np.arange(len(X) - 12 * H + 1)
    flex = {}
    plans = {"eq60_UST_5Y": lambda k: vec({"US_MKT": .6, "UST_5Y": .4}),
             "eq100": lambda k: vec({"US_MKT": 1.0}),
             "bnc_equilibre": lambda k: vec(usd["pf"]["bnc_equilibre"]),
             f"rising_40_to_70_over_{K_STAR}y": lambda k: vec({"US_MKT": .4 + .3 * min(k / (12 * K_STAR), 1), "UST_5Y": .6 - .3 * min(k / (12 * K_STAR), 1)}),
             f"falling_70_to_40_over_{K_STAR}y": lambda k: vec({"US_MKT": .7 - .3 * min(k / (12 * K_STAR), 1), "UST_5Y": .3 + .3 * min(k / (12 * K_STAR), 1)})}
    for name, fn in plans.items():
        flex[name] = {}
        for cut in (0.0, 0.10, 0.20):
            for rate in (0.035, 0.04, 0.045):
                s = simulate(X, iv, starts, 12 * H, rate, fn, cut)
                flex[name][f"cut{cut}_rate{rate}"] = {"fail": float(s["exhausted"].mean()),
                                                      "median_final_real": float(np.median(s["final_real"])),
                                                      "min_months_survived": int(s["months_survived"].min())}
        for cut in (0.0, 0.10, 0.20):
            lo, hi = 0.01, 0.10
            for _ in range(22):
                mid = (lo + hi) / 2
                if simulate(X, iv, starts, 12 * H, mid, fn, cut)["exhausted"].any():
                    hi = mid
                else:
                    lo = mid
            flex[name][f"safemax_cut{cut}"] = lo
        print("flex", name, {k: round(v["fail"], 3) if isinstance(v, dict) else round(v, 4) for k, v in flex[name].items()})
    out["flex_glide_usd_h50"] = {"n_windows": len(starts), "rule": "after a 12-month block with negative real return, "
                                 "next 12 withdrawals cut by `cut`", "results": flex}

    # ---- sequence: worst annual starts for eq60_UST_5Y, USD H=50 ----
    r = port_returns(R, {"US_MKT": .6, "UST_5Y": .4})
    p = pwr_all(r, iv, 600)
    real = np.log1p(r) - np.log1p(iv)
    c = np.concatenate([[0], np.cumsum(real)])
    jan = [i for i, d in enumerate(R.index[:len(p)]) if d.month == 1]
    seq = sorted([{"start": str(R.index[i].date()), "pwr": float(p[i]),
                   "real_first_10y": float(np.expm1((c[i + 120] - c[i]) / 10)),
                   "real_years_11_50": float(np.expm1((c[i + 600] - c[i + 120]) / 40))} for i in jan], key=lambda d: d["pwr"])
    out["sequence_usd_eq60_h50"] = {"worst5": seq[:5], "best3": seq[-3:], "n_annual_starts": len(seq)}

    # ---- stress: 2022 as first retirement year (real tickers, CAD) ----
    T = load_returns(["XBB.TO", "XIU.TO", "SPY", "ZST.TO", "GLD"], start="2021-12", end="2026-09", currency="CAD")
    ic = load_inflation("CAD").reindex(T.index).values
    stress = {}
    pf_t = {f"bnc_{k.lower()}": bnc_weights(k, "XBB.TO", "XIU.TO", "SPY") for k in BNC}
    pf_t["eq100_xiu30_spy70"] = {"XIU.TO": .3, "SPY": .7}
    pf_t["eq60_zst10_xbb30"] = {"XIU.TO": .18, "SPY": .42, "ZST.TO": .10, "XBB.TO": .30}
    for name, w in pf_t.items():
        rr = port_returns(T, w)
        Wp, cpi, path = 1.0, 1.0, []
        for k in range(len(rr)):
            cpi *= 1 + ic[k]
            Wp = Wp * (1 + rr[k]) - 0.04 / 12 * cpi
            path.append(Wp / cpi)
        stress[name] = {"final_real_wealth": path[-1], "min_real_wealth": min(path),
                        "month_of_min": str(T.index[int(np.argmin(path))].date()),
                        "real_wealth_end_2022": path[list(T.index.strftime("%Y-%m")).index("2022-12")],
                        "max_dd_time_weighted": float(__import__("alphaforge.finance.backtest.metrics", fromlist=["x"]).max_drawdown(rr)),
                        "return_2022": float(np.prod(1 + rr[1:13]) - 1)}
    out["stress_2022_start_cad"] = {"period": [str(T.index[0].date()), str(T.index[-1].date())], "rate": 0.04,
                                    "results": stress}
    # historical context: percentile of real wealth after the same number of months (USD, eq60/40 and eq100)
    m = len(T)
    ctx = {}
    for name, w in (("eq60_UST_5Y", {"US_MKT": .6, "UST_5Y": .4}), ("eq100", {"US_MKT": 1.0}), ("bnc_equilibre", usd["pf"]["bnc_equilibre"])):
        s = simulate(X, iv, np.arange(len(X) - m + 1), m, 0.04, lambda k, w=w: vec(w))
        ctx[name] = {"p10_real_wealth_after_m": float(np.quantile(s["final_real"], .1)),
                     "median": float(np.median(s["final_real"])), "months": m}
    out["stress_2022_start_cad"]["usd_history_context"] = ctx
    print("stress", {k: round(v["final_real_wealth"], 3) for k, v in stress.items()})

    # ---- retirement age +-2 y (capital and horizon), USD history ----
    contrib_h1 = 9908.0
    age = {}
    rc = port_returns(R, usd["pf"]["bnc_croissance"])
    pe = port_returns(R, {"US_MKT": .6, "UST_5Y": .4})
    for T_acc, Hd in ((4, 52), (6, 50), (8, 48)):
        n = 12 * T_acc
        rows = {}
        for contrib_name, cm in (("H1", contrib_h1), ("H2", contrib_h1 / 2)):
            caps = []
            for i in range(len(rc) - n + 1):
                Wc, cpi = 640000.0, 1.0
                for k in range(n):
                    cpi *= 1 + iv[i + k]
                    Wc = Wc * (1 + rc[i + k]) + cm * cpi
                caps.append(Wc / cpi)
            caps = np.array(caps)
            pd_ = pwr_all(pe, iv, 12 * Hd)
            rows[contrib_name] = {}
            for q in ("p10", "median"):
                capq = float(np.quantile(caps, .1 if q == "p10" else .5))
                rate = 52000 / capq
                rows[contrib_name][q] = {"real_capital": capq, "implied_rate": rate,
                                         "hist_fail_eq60_UST_5Y": float(np.mean(pd_ < rate))}
        age[f"retire_after_{T_acc}y_H{Hd}"] = rows
    out["retirement_age_sensitivity_usd"] = {"accumulation_mix": "bnc_croissance (UST_10Y/US_MKT)", "decumulation_mix": "eq60_UST_5Y",
                                             "results": age}
    print("age", {k: {c: {q: round(x["implied_rate"], 4) for q, x in v[c].items()} for c in v} for k, v in age.items()})

    # ---- withdrawal-aware hindsight ORACLE (grid 10 %, constant mix): argmax PWR per window ----
    orc = {}
    for era, H, assets, caps_ in ((E[0], 50, ["US_MKT", "UST_TBILL", "UST_2Y", "UST_5Y", "UST_10Y"], {}),
                                  (E[0], 30, ["US_MKT", "UST_TBILL", "UST_2Y", "UST_5Y", "UST_10Y"], {}),
                                  (E[1], 30, ["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL", "GOLD"], {"GOLD": .3}),
                                  (E[1], 40, ["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL", "GOLD"], {"GOLD": .3})):
        R, infl = era["R"]
        Rr = R[assets].values
        grid = [np.array(c) / 10 for c in itertools.product(range(11), repeat=len(assets)) if sum(c) == 10
                and all(c[j] / 10 <= caps_.get(a, 1) + 1e-9 for j, a in enumerate(assets))]
        P = np.array([pwr_all(Rr @ g, infl.values, 12 * H) for g in grid])
        jan = [i for i, d in enumerate(R.index[:P.shape[1]]) if d.month == 1]
        best = P[:, jan].argmax(0)
        W = np.array([grid[b] for b in best])
        eq = W[:, [assets.index(a) for a in assets if a in ("US_MKT", "CA_EQ")]].sum(1)
        nonov = list(range(0, P.shape[1], 12 * H))
        orc[f"{era['name']}_H{H}"] = {
            "hindsight": True, "n_grid": len(grid), "n_annual_windows": len(jan),
            "weights_p10_p90": {a: [float(np.quantile(W[:, j], .1)), float(np.quantile(W[:, j], .9))] for j, a in enumerate(assets)},
            "equity_share_p10_median_p90": [float(np.quantile(eq, .1)), float(np.median(eq)), float(np.quantile(eq, .9))],
            "oracle_pwr_min_median": [float(P[best, jan].min()), float(np.median(P[best, jan]))],
            "non_overlapping": [{"start": str(R.index[i].date()), "weights": dict(zip(assets, grid[int(P[:, i].argmax())].tolist())),
                                 "pwr": float(P[:, i].max())} for i in nonov]}
        print("oracle", era["name"], H, orc[f"{era['name']}_H{H}"]["equity_share_p10_median_p90"], orc[f"{era['name']}_H{H}"]["non_overlapping"])
    out["oracle_withdrawal"] = orc
    print(write_trace("swr", out, {"rates": RATES, "seed": SEED, "k_star": K_STAR, "doc": __doc__}))


if __name__ == "__main__":
    main()
