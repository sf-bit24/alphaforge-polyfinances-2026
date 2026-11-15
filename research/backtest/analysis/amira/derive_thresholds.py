"""Derive Amira's tech look-through cap, reference equity share and drawdown budget from the sweep.

Rules (written BEFORE looking at which number comes out; proposals for the team to validate):
  R-UW  recovery rule: a policy is admissible if, in EVERY rolling window of the horizon H, its longest
        underwater spell (months below the previous peak) is <= H/2 (90 months for H = 15 y).
        Rationale: Amira has 15+ years; a loss that takes more than half the horizon to recover leaves
        no time to compound and is the situation that triggers capitulation (loss aversion, persona doc
        section 4 - behavioural input only, no number taken from it).
  R-P10 among admissible policies, pick the one with the best 10th-percentile real annualised return.
  R-TECH tech cap = the largest T that is admissible at the selected equity share in BOTH eras
        (long USD 1926+ and CAD 1977+), because her income is itself tied to tech (human capital):
        we do not use the era that is more favourable to tech.
  R-DD  drawdown budget = 90th percentile (across windows) of the selected policy's max drawdown
        in the long USD era (the drawdown accepted in 9 windows out of 10), rounded to 5 points.
Writes results/amira_sweep_tech/derived_thresholds.json.
SIMULATION ONLY.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amira_common import BT, RESULTS, write_json  # noqa: E402

SUM = RESULTS / "amira_sweep_tech" / "sweep_tech_summary.json"


def parse(name):
    if not name.startswith("E"):
        return np.nan, np.nan
    e, t = name.split("_")
    return int(e[1:]) / 100, int(t[1:]) / 100


def main():
    s = json.loads(SUM.read_text())["result"]
    out = {"rules": __doc__.split("Rules")[1].split("Writes")[0].strip(), "eras": {}}
    for key, v in s.items():
        st = pd.DataFrame(v["stats"]).set_index("strategy")
        H = int(key.split("_h")[1])
        st[["E", "T"]] = [parse(n) for n in st.index]
        st["admissible"] = st["underwater_worst"] <= H * 12 / 2
        grid = st.dropna(subset=["E"])
        adm = grid[grid["admissible"]]
        best = adm["real_p10"].idxmax() if len(adm) else None
        tmax_by_E = {f"{E:.2f}": float(g.loc[g["admissible"], "T"].max()) if g["admissible"].any() else None
                     for E, g in grid.groupby("E")}
        p10_argmax_T_by_E = {f"{E:.2f}": float(g.loc[g["real_p10"].idxmax(), "T"]) for E, g in grid.groupby("E")}
        # who drives the worst underwater spell (window label) for each policy at the chosen E
        trace = json.loads((BT / v["trace"]).read_text())
        rows = pd.DataFrame(trace["results"])
        drivers = {}
        if best:
            Eb = st.at[best, "E"]
            for n in grid[grid["E"] == Eb].index:
                r = rows[rows["strategy"] == n]
                i = r["max_underwater_months"].idxmax()
                j = r["max_drawdown"].idxmax()
                drivers[n] = {"underwater_worst": int(r.at[i, "max_underwater_months"]), "uw_window": r.at[i, "window"],
                              "maxdd_worst": float(r.at[j, "max_drawdown"]), "dd_window": r.at[j, "window"],
                              "real_p10": float(st.at[n, "real_p10"]), "real_worst": float(st.at[n, "real_worst"])}
        out["eras"][key] = {"trace": v["trace"], "n_windows": v["n_windows"], "best_admissible": best,
                            "best_admissible_stats": st.loc[best].to_dict() if best else None,
                            "max_admissible_T_by_E": tmax_by_E, "p10_argmax_T_by_E": p10_argmax_T_by_E,
                            "drivers_at_best_E": drivers,
                            "unconstrained_best_p10": st["real_p10"].idxmax()}
    # R-TECH and R-DD on the main horizon (15 y)
    a, c = out["eras"]["long_usd_h15"], out["eras"]["cad_1977_h15"]
    E_ref = a["best_admissible_stats"]["E"]
    t_usd = a["max_admissible_T_by_E"][f"{E_ref:.2f}"]
    t_cad = c["max_admissible_T_by_E"].get(f"{E_ref:.2f}")
    tech_cap = min(x for x in (t_usd, t_cad) if x is not None)
    trace = json.loads((BT / a["trace"]).read_text())
    rows = pd.DataFrame(trace["results"])
    ref = a["best_admissible"]
    dd_p90 = float(rows.loc[rows["strategy"] == ref, "max_drawdown"].quantile(0.9))
    out["derived"] = {"reference_policy_long_usd": ref, "equity_share_ref": E_ref,
                      "tech_cap_usd_at_Eref": t_usd, "tech_cap_cad_at_Eref": t_cad, "tech_cap": tech_cap,
                      "maxdd_p90_ref": dd_p90, "dd_budget": round(dd_p90 * 20) / 20,
                      "status": "proposition a valider par l'equipe"}
    p = write_json(out, RESULTS / "amira_sweep_tech" / "derived_thresholds.json", [SUM.relative_to(BT).as_posix()])
    print(json.dumps(out["derived"], indent=1))
    for k, v in out["eras"].items():
        print(k, v["best_admissible"], "maxT_by_E", v["max_admissible_T_by_E"], "p10argmaxT", v["p10_argmax_T_by_E"])
    print(p)


if __name__ == "__main__":
    main()
