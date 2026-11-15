"""D6 (plafond d'or) : statistiques de l'or (CAD/USD) et sensibilité du choix robuste de Mateo au plafond d'or.

Partie A (lecture des données partagées, aucun run) : perte maximale et durée sous l'eau de GOLD depuis 1975,
rendement réel par décennie, corrélation mensuelle or / actions en USD et en CAD (effet de change).
Partie B (runs moteur, sans ORACLE) : Mateo, variantes ESG CAD 1977+ et USD 1975+ (avec or), stratégies
`risk_parity_iv36` (choix robuste du rapport) et `static_eq60_gold`, avec GOLD borné à [0, cap],
cap ∈ {0 ; 0,05 ; 0,10 ; sans plafond}. Profils lus depuis profiles/ ; le moteur n'est pas modifié
(enrobage analysis/mateo/common.py pour US_MKT_XEN). Traces : results/dec_mateo_*_gold*/.

Écrit results/decisions_analysis/d6_gold.json. SIMULATION UNIQUEMENT, pas un conseil.
Usage : .venv/bin/python -I -W ignore analysis/decisions/d6_gold.py [--no-runs]
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BT = HERE.parents[1]
sys.path.insert(0, str(BT / "analysis" / "mateo"))
import common  # noqa: E402  (sets ALPHAFORGE_BT_DATA to analysis/mateo/data_ext, wraps exposure_vector)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from engine.data import load_inflation, load_returns  # noqa: E402

OUT = BT / "results" / "decisions_analysis" / "d6_gold.json"


def maxdd(r: pd.Series) -> tuple[float, str, str, int]:
    w = (1 + r).cumprod()
    peak = w.cummax()
    dd = 1 - w / peak
    trough = dd.idxmax()
    pk = w.loc[:trough].idxmax()
    rec = w.loc[trough:][w.loc[trough:] >= w.loc[pk]]
    months = int(((rec.index[0] if len(rec) else w.index[-1]).to_period("M") - pk.to_period("M")).n)
    return float(dd.max()), str(pk.date()), str(trough.date()), months


def part_a() -> dict:
    out = {}
    for cur, start in [("USD", "1975-01"), ("CAD", "1975-01")]:
        g = load_returns(["GOLD"], start=start, currency=cur)["GOLD"]
        infl = load_inflation(cur)
        real = (1 + g) / (1 + infl.reindex(g.index)) - 1
        dd, pk, tr, m = maxdd(real.dropna())
        dn, pkn, trn, mn = maxdd(g)
        dec = {}
        for d0 in range(1975, 2030, 10):
            seg = real.loc[f"{d0}-01":f"{d0 + 9}-12"].dropna()
            if len(seg) >= 24:
                dec[f"{d0}-{min(d0 + 9, 2026)}"] = round(float((1 + seg).prod() ** (12 / len(seg)) - 1), 4)
        out[cur] = {"period": [str(g.index.min().date()), str(g.index.max().date())],
                    "maxdd_nominal": round(dn, 3), "maxdd_nominal_peak_trough": [pkn, trn], "months_to_recover_nominal": mn,
                    "maxdd_real": round(dd, 3), "maxdd_real_peak_trough": [pk, tr], "months_to_recover_real": m,
                    "real_return_by_decade": dec}
    corr = {}
    for cur in ["USD", "CAD"]:
        R = load_returns(["GOLD", "US_MKT", "CA_EQ"], start="1977-01", currency=cur)
        corr[cur] = {"gold_vs_us_mkt_1977_2026": round(float(R["GOLD"].corr(R["US_MKT"])), 3),
                     "gold_vs_ca_eq_1977_2026": round(float(R["GOLD"].corr(R["CA_EQ"])), 3)}
        T = load_returns(["GLD", "SPY", "XIU.TO"], start="2021-11", currency=cur)
        corr[cur]["gld_vs_spy_2021_11_2026"] = round(float(T["GLD"].corr(T["SPY"])), 3)
        corr[cur]["gld_vs_xiu_2021_11_2026"] = round(float(T["GLD"].corr(T["XIU.TO"])), 3)
        corr[cur]["n_months_tickers"] = int(len(T))
    out["correlations_monthly"] = corr
    return out


def part_b() -> dict:
    res = {}
    for prof_id in ["mateo_cad_esg", "mateo_usd_gold_esg"]:
        base = common.load_profile(prof_id)
        for cap in [0.0, 0.05, 0.10, None]:
            p = copy.deepcopy(base)
            tag = "nocap" if cap is None else f"{int(round(cap * 100)):02d}"
            p["id"] = f"dec_{prof_id}_gold{tag}"
            p["strategies"] = [s for s in p["strategies"] if s["name"] in ("risk_parity_iv36", "static_eq60_gold")]
            if cap is not None:
                p["constraints"].setdefault("asset_bounds", {})
                p["constraints"]["asset_bounds"] = dict(p["constraints"]["asset_bounds"] or {}, GOLD=[0.0, cap])
            r = common.run_profile(p, "rolling", 10, None, None, 12, False, verbose=False)
            rows = r["rows"]
            for s in ["risk_parity_iv36", "static_eq60_gold"]:
                d = rows[rows["strategy"] == s]
                if not len(d):
                    continue
                eq_assets = [a for a in p["universe"] if a in ("CA_EQ", "US_MKT", "US_MKT_XEN") or a.startswith("US_IND_")]
                rec = {"n_windows": int(len(d)),
                       "p10_real": round(float(np.quantile(d["ann_real_return"], 0.10)), 4),
                       "median_real": round(float(d["ann_real_return"].median()), 4),
                       "worst_maxdd": round(float(d["max_drawdown"].max()), 3),
                       "breach_rate": round(float((d["n_breaches"] > 0).mean()), 3),
                       "gold_weight_mean": round(float(np.mean([w.get("GOLD", 0.0) for w in d["avg_weights"]])), 3),
                       "equity_weight_mean": round(float(np.mean([sum(w.get(a, 0.0) for a in eq_assets)
                                                                  for w in d["avg_weights"]])), 3),
                       "trace": str(r["trace_path"])}
                res.setdefault(prof_id, {}).setdefault(s, {})[tag] = rec
                print(prof_id, s, tag, rec, flush=True)
    return res


def main() -> None:
    out = {"disclaimer": "SIMULATION ONLY - historical reconstruction, not a forecast nor advice",
           "part_a_gold_stats": part_a()}
    print(json.dumps(out["part_a_gold_stats"], indent=1), flush=True)
    if "--no-runs" not in sys.argv:
        out["part_b_mateo_gold_cap"] = part_b()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
