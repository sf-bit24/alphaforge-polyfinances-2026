"""Controlled sensitivities around the robust structure (engine run_profile, rolling h4 step 12, oracle off):
 (1) gold share 0/5/10/15/20 % in the CAD structure  CA_EQ 10 / US_MKT 10 / GOLD g / CA_GOV_10Y 50-g/2 / CA_TBILL 20-g/2 ... (see below)
 (2) equity share 0..60 % with the CAD bond/cash/gold split held proportional
 (3) USD 1926+: equity share 0..50 % x bond leg {2y, 5y, 10y, 20y} at fixed equity 20 % (duration risk)
Same objective / risk limits as the base profiles. Run: uv run --group finance python -I analysis/robert/sensitivity.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from common import BT, write_trace
from alphaforge.finance.backtest.profile import load_profile, validate
from alphaforge.finance.backtest.run import run_profile


def strat(name, w):
    return {"name": name, "type": "static", "params": {"weights": {k: round(v, 6) for k, v in w.items() if v > 0}}}


def run(base, sid, strategies, mode="rolling", horizon=4):
    p = copy.deepcopy(load_profile(base))
    p.pop("_path", None)
    p.update(id=sid, strategies=strategies, oracle={"enabled": False, "n_starts": 1})
    p = validate(p)
    r = run_profile(p, mode=mode, horizon=horizon, step_months=12, out_dir=BT / "results" / sid, verbose=False)
    rb = r["robust"].reset_index()
    cols = ["strategy", "score_p10", "score_median", "score_worst", "max_drawdown_worst", "breach_rate", "shortfall_prob"]
    print(f"\n== {sid} {mode} h{horizon} -> {r['trace_path']}")
    print(rb[cols].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    return {"trace": r["trace_path"], "robust": rb[cols].to_dict(orient="records")}


def main():
    out = {}
    # (1) gold share in CAD: equity fixed 20 % (10 CA / 10 US), remaining 80 % = gold g + CA 10y + cash in ratio 5:2
    S = []
    for g in (0.0, 0.05, 0.10, 0.15, 0.20):
        rest = 0.8 - g
        S.append(strat(f"gold{int(g*100):02d}", {"CA_EQ": 0.1, "US_MKT": 0.1, "GOLD": g, "CA_GOV_10Y": rest * 5 / 7,
                                                  "CA_TBILL": rest * 2 / 7}))
    out["cad_gold"] = run("robert_cad", "robert_sens_cad_gold", S)
    # (2) equity share in CAD with gold 10 % of the non-equity part... keep gold 10 %, bonds:cash = 5:2
    S = []
    for e in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
        rest = 0.9 - e
        S.append(strat(f"eq{int(e*100):02d}", {"CA_EQ": e / 2, "US_MKT": e / 2, "GOLD": 0.1, "CA_GOV_10Y": rest * 5 / 7,
                                                "CA_TBILL": rest * 2 / 7}))
    out["cad_equity"] = run("robert_cad", "robert_sens_cad_equity", S)
    # (3) USD 1926+: duration at fixed 20 % equity, and equity share with 2y / 5y legs
    S = [strat(f"eq20_{leg}", {"US_MKT": 0.2, leg: 0.8}) for leg in ("UST_TBILL", "UST_2Y", "UST_5Y", "UST_10Y", "UST_20Y", "CORP_AAA")]
    S += [strat(f"eq{int(e*100):02d}_2y", {"US_MKT": e, "UST_2Y": 1 - e}) for e in (0.0, 0.1, 0.3, 0.4, 0.5)]
    S += [strat(f"eq{int(e*100):02d}_2y5y", {"US_MKT": e, "UST_2Y": (1 - e) / 2, "UST_5Y": (1 - e) / 2}) for e in (0.1, 0.2, 0.3)]
    out["usd_duration"] = run("robert_long_usd", "robert_sens_usd_duration", S)
    out["usd_duration_nonov"] = run("robert_long_usd", "robert_sens_usd_duration", S, mode="non_overlapping")
    S = [strat(f"eq20_gold{int(g*100):02d}", {"US_MKT": 0.2, "GOLD": g, "UST_2Y": (0.8 - g) / 2, "UST_5Y": (0.8 - g) / 2})
         for g in (0.0, 0.05, 0.10, 0.15)]
    out["usd1975_gold"] = run("robert_usd_gold", "robert_sens_usd_gold", S)
    p = write_trace("sensitivity", out, {"mode": "rolling step 12 (+ non_overlapping for usd_duration)", "horizon": 4})
    print("trace:", p)


if __name__ == "__main__":
    main()
