"""Sensitivity sweep: total look-through tech exposure T x equity share E (static, ex-ante policies).

Each policy: BusEq = T, the (E - T) rest of equity spread equally over the 11 non-tech KF industries
(=> look-through tech is exactly T, no estimate needed), bonds (1 - E) half 5y / half 10y Treasury
(USD eras) or Canada 10y (CAD era). Annual rebalancing, 10 bps costs, no oracle.
Rolling 15y (step 12) + 20y sensitivity. Writes engine traces in results/amira_sweep_tech/.

    uv run --group finance python -I analysis/amira/sweep_tech.py
SIMULATION ONLY.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amira_common import NONTECH, RESULTS, per_strategy_stats, rel, run, write_json  # noqa: E402

E_GRID = [0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 1.0]
T_GRID = [0.0, 0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.8, 1.0]


def policies(era: str):
    out = []
    for E in E_GRID:
        for T in T_GRID:
            if T > E + 1e-9:
                continue
            w = {"US_IND_BUSEQ": T}
            rest = E - T
            if era == "cad_1977":
                # non-tech equity: half Canadian market, half US non-tech industries (CA_EQ tech share unknown -> 0)
                w["CA_EQ"] = rest / 2
                for s in NONTECH:
                    w[s] = rest / 2 / len(NONTECH)
                w["CA_GOV_10Y"] = 1 - E
            else:
                for s in NONTECH:
                    w[s] = rest / len(NONTECH)
                w["UST_5Y"] = (1 - E) / 2
                w["UST_10Y"] = (1 - E) / 2
            w = {k: round(v, 10) for k, v in w.items() if v > 0}
            out.append({"name": f"E{int(E*100):03d}_T{int(T*100):03d}", "type": "static", "params": {"weights": w}})
    # references
    if era == "cad_1977":
        out.append({"name": "REF_CA_EQ_100", "type": "static", "params": {"weights": {"CA_EQ": 1.0}}})
        out.append({"name": "REF_USMKT_100", "type": "static", "params": {"weights": {"US_MKT": 1.0}}})
    else:
        out.append({"name": "REF_USMKT_100", "type": "static", "params": {"weights": {"US_MKT": 1.0}}})
        out.append({"name": "REF_USMKT_80_UST10_20", "type": "static",
                    "params": {"weights": {"US_MKT": 0.8, "UST_10Y": 0.2}}})
    return out


def base(era: str) -> dict:
    if era == "cad_1977":
        uni = ["CA_EQ", "US_MKT"] + NONTECH + ["US_IND_BUSEQ", "CA_GOV_10Y", "CA_TBILL"]
        cur, cash, start = "CAD", "CA_TBILL", "1977-01"
    else:
        uni = ["US_MKT"] + NONTECH + ["US_IND_BUSEQ", "UST_5Y", "UST_10Y", "UST_TBILL"]
        cur, cash, start = "USD", "UST_TBILL", "1926-07"
    return {"id": f"amira_sweep_tech_{era}", "description": "Amira tech look-through x equity-share sweep",
            "currency": cur, "horizon_years": 15, "mode": "rolling", "step_months": 12,
            "period": {"start": start, "end": None}, "universe": uni, "cash_asset": cash,
            "objective": {"type": "max_real_return", "target_real_return": 0.0},
            "rebalancing": {"frequency": "annual"}, "costs_bps": 10,
            "flows": {"initial": 1.0, "monthly": 0.0, "indexed_to_inflation": True},
            "strategies": policies(era), "oracle": {"enabled": False}, "seed": 42}


def main():
    summary = {}
    for era in ("long_usd", "cad_1977"):
        for h in (15, 20):
            res = run(base(era), "amira_sweep_tech", horizon=h, mode="rolling", step_months=12)
            st = per_strategy_stats(res["rows"])
            key = f"{era}_h{h}"
            summary[key] = {"trace": rel(res["trace_path"]), "n_windows": len(res["windows"]),
                            "data_info": res["data_info"], "stats": st.reset_index().to_dict(orient="records")}
            print(key, rel(res["trace_path"]), len(res["windows"]))
            print(st.round(4).to_string())
    p = write_json(summary, RESULTS / "amira_sweep_tech" / "sweep_tech_summary.json",
                   [v["trace"] for v in summary.values()])
    print("summary:", p)


if __name__ == "__main__":
    main()
