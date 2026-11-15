"""Reverse engineering for persona 12: (1) rule checks across eras/horizons (robust / fragile / inconclusive),
(2) start-of-window observable signals vs outcomes (Spearman; association only, NO causality, small N).
Reads results/p12_analysis/swr.json + derive_thresholds.json and the latest engine traces. SIMULATION ONLY."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from common import BT, OUT, era_data, port_returns, pwr_all, write_trace

swr = json.loads((OUT / "swr.json").read_text())["results"]
thr = json.loads((OUT / "derive_thresholds.json").read_text())["results"]
tab = json.loads((OUT / "tables.json").read_text())["results"]


def T(era, H, pf, key="pwr_min"):
    return swr["eras"][era]["tables"][str(H)]["portfolios"][pf][key]


def rules():
    out = []
    cases = [("usd_1926", H) for H in (30, 40, 50, 55)] + [("cad_1977", H) for H in (30, 40)]
    eq60 = {"usd_1926": "eq60_UST_5Y", "cad_1977": "eq60_CA_GOV_10Y"}
    eq100 = {"usd_1926": "eq100_UST_TBILL", "cad_1977": "eq100_CA_GOV_10Y"}
    def add(rule, fn):
        res = {f"{e}_H{H}": bool(fn(e, H)) for e, H in cases}
        v = list(res.values())
        usd = [res[k] for k in res if k.startswith("usd")]
        verdict = "robuste" if all(v) else ("fragile" if any(v) and not all(v) else "rejetee")
        if all(usd) and not all(v):
            verdict = "robuste USD, fragile CAD (1 fenetre independante)"
        out.append({"rule": rule, "by_case": res, "verdict": verdict})
    add("SAFEMAX 60 % actions >= SAFEMAX 100 % actions", lambda e, H: T(e, H, eq60[e]) >= T(e, H, eq100[e]))
    add("SAFEMAX BNC Equilibre > SAFEMAX BNC Conservateur", lambda e, H: T(e, H, "bnc_equilibre") > T(e, H, "bnc_conservateur"))
    add("Echec historique a 4 % > 0 pour le meilleur melange", lambda e, H: max(swr["eras"][e]["tables"][str(H)]["portfolios"].values(), key=lambda x: x["pwr_min"])["fail"]["0.04"] > 0)
    add("SAFEMAX(H) < 4 % pour le meilleur melange", lambda e, H: max(x["pwr_min"] for x in swr["eras"][e]["tables"][str(H)]["portfolios"].values()) < 0.04)
    add("Meilleur SAFEMAX avec 50-70 % d'actions", lambda e, H: any(swr["eras"][e]["tables"][str(H)]["best_by_min"].startswith(f"eq{x}_") for x in (50, 60, 70)))
    add("100 % actions : pire SAFEMAX que BNC Croissance", lambda e, H: T(e, H, eq100[e]) < T(e, H, "bnc_croissance"))
    return out


def signals():
    """Start-of-window observables vs (a) PWR of the 60/40 mix, (b) withdrawal-oracle equity share."""
    out = {}
    for era, assets, w, cash, H in (("usd_1926", ["US_MKT", "UST_5Y", "UST_TBILL"], {"US_MKT": .6, "UST_5Y": .4}, "UST_TBILL", 50),
                                    ("usd_1926", ["US_MKT", "UST_5Y", "UST_TBILL"], {"US_MKT": .6, "UST_5Y": .4}, "UST_TBILL", 30),
                                    ("cad_1977", ["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL"], {"CA_EQ": .18, "US_MKT": .42, "CA_GOV_10Y": .4}, "CA_TBILL", 30)):
        cur = "USD" if era.startswith("usd") else "CAD"
        R, infl = era_data(assets, cur, "1926-08" if cur == "USD" else "1977-01")
        r = port_returns(R, w)
        p = pwr_all(r, infl.values, 12 * H)
        eqcol = "US_MKT"
        rows = []
        for i in range(len(p)):
            if R.index[i].month != 1 or i < 120:
                continue
            eq = R[eqcol].values[i - 120:i]
            inf = infl.values[i - 12:i]
            rows.append({"start": R.index[i], "pwr": p[i],
                         "trail10y_real_eq": float(np.expm1((np.log1p(eq).sum() - np.log1p(infl.values[i - 120:i]).sum()) / 10)),
                         "trail12m_eq": float(np.prod(1 + R[eqcol].values[i - 12:i]) - 1),
                         "trail12m_infl": float(np.prod(1 + inf) - 1),
                         "cash_yield_12m": float(np.prod(1 + R[cash].values[i - 12:i]) - 1),
                         "eq_drawdown_at_start": float(1 - np.prod(1 + eq[-36:]) / np.max(np.cumprod(1 + eq[-36:])))})
        df = pd.DataFrame(rows)
        res = {"n_annual_starts": len(df), "n_independent": int(len(R) // (12 * H)), "first_start": str(df.start.iloc[0].date()) if len(df) else None, "corr_with_pwr": {}}
        for c in ["trail10y_real_eq", "trail12m_eq", "trail12m_infl", "cash_yield_12m", "eq_drawdown_at_start"]:
            if len(df) > 5:
                rho, pv = spearmanr(df[c], df["pwr"])
                res["corr_with_pwr"][c] = {"rho": float(rho), "p_naive": float(pv)}
        out[f"{era}_H{H}"] = res
        print(era, H, len(df), {k: round(v["rho"], 2) for k, v in res["corr_with_pwr"].items()})
    return out


def accum_oracle_signals():
    """Engine ORACLE (accumulation, rolling 6 y): equity share vs start-of-window trailing 10 y real equity return."""
    out = {}
    for key in ("p12_accum_usd|rolling_h6", "p12_accum_cad|rolling_h6"):
        t = json.loads((BT / tab[key]["trace"]).read_text())
        rows = pd.DataFrame(t["results"])
        orc = rows[rows.hindsight].copy()
        orc["eq"] = orc["avg_weights"].apply(lambda w: sum(v for a, v in w.items() if a in ("US_MKT", "CA_EQ") or a.startswith("US_IND")))
        cur = t["profile"]["currency"]
        R, infl = era_data(["US_MKT"], cur, t["profile"]["period"]["start"])
        sig = []
        for s in pd.to_datetime(orc["start"]):
            i = R.index.get_loc(s)
            sig.append(np.nan if i < 120 else float(np.expm1((np.log1p(R["US_MKT"].values[i - 120:i]).sum() - np.log1p(infl.values[i - 120:i]).sum()) / 10)))
        orc["trail10y"] = sig
        d = orc.dropna(subset=["trail10y"])
        rho, pv = spearmanr(d["trail10y"], d["eq"])
        out[key] = {"n": len(d), "rho_equity_share_vs_trail10y_real_eq": float(rho), "p_naive": float(pv),
                    "oracle_equity_share_p10_median_p90": [float(orc["eq"].quantile(.1)), float(orc["eq"].median()), float(orc["eq"].quantile(.9))]}
        print(key, out[key])
    return out


def main():
    res = {"rules": rules(), "signals_pwr": signals(), "accum_oracle": accum_oracle_signals(),
           "sequence_k_star": {e: {H: {"k_star": s["k_star"], "max_corr": s["max_corr"], "k_at_max": s["k_at_max"]}
                                   for H, s in thr[e]["B_sequence"].items()} for e in ("usd_1926", "cad_1977")}}
    for r in res["rules"]:
        print(r["verdict"], "|", r["rule"], r["by_case"])
    print(write_trace("reverse", res, {"doc": __doc__}))


if __name__ == "__main__":
    main()
