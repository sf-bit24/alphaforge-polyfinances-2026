"""Decision report A (regulatory profile) - supporting computations. SIMULATION ONLY, not financial advice.

1. D9 - CSA "Investment Risk Classification Methodology" (NI 81-102, Appendix F, consolidation of 2025-07-16):
   annualised standard deviation of the last 120 MONTHLY returns, sqrt(12/(n-1) * sum (r_i - mean)^2), bands
   [0,6) Low, [6,11) Low-to-medium, [11,16) Medium, [16,20) Medium-to-high, >=20 High.
   Applied to the same long-window series as analysis/croisement/stress_anchor.py (6 BNC target mixes on proxies,
   CAD 1977+ and USD 1926+, plus our 3 robust strategies), via stress_anchor.series() - same engine, same params.
   Compared with: 2022 calendar loss, worst calendar year (the measure Vanguard publishes per stock/bond mix,
   1928-2025), worst episode (stress_anchor.json).
2. D1/D11 - dollar view of the AMF Q10 answer options for a fictional amount M = 100 000 $ (illustration only),
   and which robust strategies / BNC mixes fit each answer, read from the existing traces (no new engine run).
Reads engine/, data/ and results/croisement_analysis/*.json; writes results/decisions/A_reglementaire_calculs.json only.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BT))
sys.path.insert(0, str(BT / "analysis" / "croisement"))
import stress_anchor as sa  # noqa: E402  (reused, not modified)
from alphaforge.finance.backtest.data import data_version  # noqa: E402
from alphaforge.finance.backtest.run import DISCLAIMER, engine_hash  # noqa: E402

BANDS = [(0.0, 6.0, "Faible"), (6.0, 11.0, "Faible a moyen"), (11.0, 16.0, "Moyen"),
         (16.0, 20.0, "Moyen a eleve"), (20.0, np.inf, "Eleve")]
OUT = BT / "results" / "decisions"
OUT.mkdir(parents=True, exist_ok=True)


def band(sd_pct: float) -> str:
    return next(lbl for lo, hi, lbl in BANDS if lo <= sd_pct < hi)


def appendix_f(s: pd.Series) -> dict:
    r = s.astype(float)
    sd = r.rolling(120).std(ddof=1).dropna() * np.sqrt(12) * 100  # % annualised, Appendix F formula
    cats = sd.map(band)
    share = cats.value_counts(normalize=True).round(4).to_dict()
    return {"last_window_end": str(sd.index[-1].date()), "sd_last_pct": round(float(sd.iloc[-1]), 2),
            "band_last": band(float(sd.iloc[-1])), "sd_min_pct": round(float(sd.min()), 2),
            "sd_max_pct": round(float(sd.max()), 2), "sd_max_end": str(sd.idxmax().date()),
            "band_at_max": band(float(sd.max())), "n_windows": int(len(sd)), "band_share": share,
            "sd_full_period_pct": round(float(r.std(ddof=1) * np.sqrt(12) * 100), 2)}


def main():
    S = sa.series()
    stress = json.loads((BT / "results/croisement_analysis/stress_anchor.json").read_text())["results"]
    res = {"appendix_f": {}, "comparison_bnc": {}}
    for cur in ("CAD", "USD"):
        res["appendix_f"][cur] = {k: appendix_f(v) for k, v in S[cur].items() if k != "cash_100"}
        rows = {}
        for b in sa.BNC:
            a = res["appendix_f"][cur][b]
            m = stress[cur][b]
            rows[b] = {"sd10_last_pct": a["sd_last_pct"], "band_last": a["band_last"], "sd10_max_pct": a["sd_max_pct"],
                       "band_at_max": a["band_at_max"], "loss_2022_pct": round(100 * m["loss_2022"], 2) if m["loss_2022"] is not None else None,
                       "worst_year_pct": round(100 * m["worst_year"], 2), "worst_year_when": m["worst_year_when"],
                       "episode_max_pct": round(100 * m["episode_max"], 2), "episode_max_when": m["episode_max_when"]}
        df = pd.DataFrame(rows).T
        spread = {k: round(float(df[k].astype(float).max() - df[k].astype(float).min()), 2)
                  for k in ("sd10_last_pct", "sd10_max_pct", "loss_2022_pct", "worst_year_pct", "episode_max_pct")}
        res["comparison_bnc"][cur] = {"rows": rows, "spread_prudent_to_actions_pts": spread,
                                      "distinct_bands_last": int(df["band_last"].nunique()),
                                      "distinct_bands_at_max": int(df["band_at_max"].nunique())}
        print("=====", cur)
        print(df.to_string())
        print("spread (pts):", spread)
        for k in [k for k in res["appendix_f"][cur] if ":" in k]:
            print(k, res["appendix_f"][cur][k])

    # 2. dollar view of AMF Q10 options (fictional M), worst losses read from traces
    M = 100_000
    WC = json.loads((BT / "results/croisement_analysis/will_vs_cap.json").read_text())["results"]
    rob_cap = WC["robert"]["robert_cad|rolling|capacite_0.23"]["robust"]
    rob_w05 = WC["robert"]["robert_cad|rolling|volonte_0.05"]["robust"]
    q10 = {"0 %": 0.0, "5 %": 0.05, "15 %": 0.15, "30 %": 0.30, "plus de 30 % (borne basse)": 0.30}
    res["q10_dollars"] = {"M_fictif": M, "options": {k: int(round(v * M)) for k, v in q10.items()},
                          "robert_eq20_gold10_worst_dd": round(rob_cap["maxdd_worst"], 4),
                          "robert_eq20_gold10_worst_dd_dollars": int(round(rob_cap["maxdd_worst"] * M)),
                          "robert_eq20_gold10_worst_12m_cad1977": round(stress["CAD"]["robert:eq20_gold10"]["worst_12m"], 4),
                          "robert_eq20_gold10_worst_year_cad1977": round(stress["CAD"]["robert:eq20_gold10"]["worst_year"], 4),
                          "robert_cash_p_real_loss_4y": round(rob_w05["p_real_loss"], 4),
                          "robert_eq20_gold10_p_real_loss_4y": round(rob_cap["p_real_loss"], 4),
                          "robert_cash_p10_real": round(rob_w05["p10"], 4), "robert_eq20_p10_real": round(rob_cap["p10"], 4)}
    print(json.dumps(res["q10_dollars"], indent=1))

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace = {"run_id": "A_reglementaire_calculs", "created_utc": stamp, "disclaimer": DISCLAIMER,
             "engine_sha256": engine_hash(), "data_version": data_version(),
             "script": "analysis/decisions/A_reglementaire_calculs.py",
             "inputs": ["data/long/monthly_returns.parquet (via stress_anchor.series())",
                        "results/croisement_analysis/stress_anchor.json", "results/croisement_analysis/will_vs_cap.json",
                        "results/croisement_analysis/stress_mateo_series.json"],
             "params": {"appendix_f": "NI 81-102 Appendix F, 120 monthly returns, ddof=1, x sqrt(12); bands 6/11/16/20",
                        "doc": __doc__}, "results": res}
    p = OUT / "A_reglementaire_calculs.json"
    p.write_text(json.dumps(trace, indent=1, default=str))
    print(p.relative_to(BT))


if __name__ == "__main__":
    main()
