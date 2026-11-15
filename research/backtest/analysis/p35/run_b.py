"""Persona 35 - pocket B runs with the engine loop and the MIXED spending-basket inflation (common.run_custom).

usage: python -I analysis/p35/run_b.py <job>
jobs: cad_roll15 | cad_non15 | cad_roll20 | cad_non20 | cad_roll15_s03 | cad_roll15_s07 | tickers
Writes results/p35_B_cad*/... and results/p35_B_tickers/... (trace JSON + CSVs). SIMULATION ONLY.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C
from engine.profile import load_profile

JOBS = {"cad_roll15": ("p35_B_cad", "rolling", 15, 0.5, True, "p35_B_cad"),
        "cad_non15": ("p35_B_cad", "non_overlapping", 15, 0.5, True, "p35_B_cad"),
        "cad_roll20": ("p35_B_cad", "rolling", 20, 0.5, True, "p35_B_cad"),
        "cad_non20": ("p35_B_cad", "non_overlapping", 20, 0.5, True, "p35_B_cad"),
        "cad_roll15_s03": ("p35_B_cad", "rolling", 15, 0.3, False, "p35_B_cad_s03"),
        "cad_roll15_s07": ("p35_B_cad", "rolling", 15, 0.7, False, "p35_B_cad_s07"),
        "cad_roll10": ("p35_B_cad", "rolling", 10, 0.5, False, "p35_B_cad_h10"),
        "tickers": ("p35_B_tickers", "non_overlapping", 4.9167, 0.5, True, "p35_B_tickers")}

if __name__ == "__main__":
    job = sys.argv[1]
    pid, mode, H, s, orc, out = JOBS[job]
    p = copy.deepcopy(load_profile(pid))
    rate = p["p35"]["withdrawal_rate"]
    p["objective"]["target_real_wealth"] = round(1 - rate * H, 4)
    p["p35"]["basket_usd_share"] = s
    infl = C.basket_inflation(s, "CAD")
    res = C.run_custom(p, infl, out, mode, H, 12, oracle=orc,
                       extra_info={"basket_usd_share": s, "withdrawal_rate": rate, "job": job})
    print(res["trace_path"])
    print(res["robust"].head(12)[["n_windows", "score_p10", "score_median", "score_worst", "max_drawdown_worst",
                                  "breach_rate", "shortfall_prob", "eligible"]].to_string())
    print(res["summary"])
