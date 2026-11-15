"""Persona 14 - apply the readable derivation rules to the stage-A sweeps. SIMULATION ONLY.
PROPOSALS TO BE VALIDATED BY THE TEAM. Reads results/p14_analysis/sweep_*.csv and energy_style_ca_eq.csv,
writes results/p14_analysis/derived_thresholds.json.

R-CAP (capacity, per pocket, CAD 1977+ = Tyler's currency): largest equity share of the ex-energy core whose
      longest REAL underwater spell (full sample, peak -> recovery of real wealth) <= horizon / 2
      ("a loss must be recovered in real terms within half of the horizon, so the second half still serves the goal").
      Capacity max_drawdown = full-sample nominal max DD of that mix, rounded UP to the next 5 pts.
R-WILL (willingness): AMF Q10 answer INFERRED from "tolérance déclarée élevée" = case "30 %" [inf].
R-MIN (31-103CP): applied limit = min(capacity, willingness).
R-ENERGY: largest direct energy weight e (look-through, incl. CA_EQ loading) such that the p90 (across rolling
      windows of the pocket horizon) of TOTAL-WEALTH max drawdown, central scenario h = 1/2, rises by at most
      b = 10 % of the pocket's drawdown limit vs e = 0. Era: CAD 1977+ (min over eras reported).
R-EMPLOYER: largest CNQ.TO weight k such that, in the worst rolling window (5 and 10 y, step 3 m, CAD 1995+), the
      financial portfolio max drawdown rises by at most b = 10 % of the pocket's drawdown limit vs k = 0
      (same convention as Amira's single-stock rule R-IDIO).
R-CAEQ: CA_EQ / XIU.TO cap implied by the energy cap: (energy cap) / (CA_EQ energy loading), loading = return-based
      estimate (energy_style_ca_eq.csv; full sample and 2007-2016 / 2017-2026 blocks as sensitivity).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as K  # noqa: E402

import pandas as pd  # noqa: E402

POCKETS = {"etudes": {"H": 10, "eq_file": 50}, "retraite": {"H": 16, "eq_file": 70}}
WILL_Q10 = 0.30


def up5(x):
    return math.ceil(round(x * 100, 6) / 5) * 5 / 100


def main():
    A = pd.read_csv(K.OUT / "sweep_A_capacity.csv")
    style = pd.read_csv(K.OUT / "energy_style_ca_eq.csv")
    load_full = float(style[(style.target == "CA_EQ") & style.block.str.startswith("full")].energy_loading.iloc[0])
    load_blocks = style[(style.target == "CA_EQ") & ~style.block.str.startswith("full")].set_index("block").energy_loading.to_dict()
    out = {"rules": __doc__, "ca_eq_energy_loading_full": load_full, "ca_eq_energy_loading_blocks": load_blocks, "pockets": {}}
    for p, cfg in POCKETS.items():
        H = cfg["H"]
        lim = H * 12 / 2
        cap_rows = {}
        for era in ("CAD 1977+", "USD 1926+"):
            a = A[A.era == era]
            ok = a[a.full_real_underwater_months <= lim]
            if len(ok):
                r = ok.sort_values("equity").iloc[-1]
                cap_rows[era] = {"equity_share": float(r.equity), "full_maxdd": float(r.full_maxdd),
                                 "real_underwater_months": int(r.full_real_underwater_months), "capacity_maxdd": up5(float(r.full_maxdd))}
            else:
                cap_rows[era] = {"equity_share": None, "note": f"no mix with real underwater <= {lim:.0f} months",
                                 "min_real_underwater_months": int(a.full_real_underwater_months.min())}
        cap = cap_rows["CAD 1977+"]["capacity_maxdd"]
        applied = min(cap, WILL_Q10)
        winner = "capacité" if cap < WILL_Q10 else ("égalité" if cap == WILL_Q10 else "volonté")
        b_main = round(0.10 * applied, 4)
        # energy cap
        B = pd.read_csv(K.OUT / f"sweep_B_energy_eq{cfg['eq_file']}.csv")
        B = B[B.H == H]
        en_tab = {}
        for era in ("CAD 1977+", "USD 1926+"):
            for h in (1 / 3, 0.5, 2 / 3):
                d = B[(B.era == era) & ((B.h - h).abs() < 1e-3)].sort_values("energy_w")
                base = float(d[d.energy_w == 0].tot_maxdd_p90.iloc[0])
                for b in (0.01, 0.02, 0.03, 0.04, b_main):
                    okk = d[d.tot_maxdd_p90 - base <= b + 1e-9]
                    en_tab[f"{era}|h={h:.3f}|b={b:.3f}"] = float(okk.energy_w.max())
        en_main = en_tab[f"CAD 1977+|h=0.500|b={b_main:.3f}"]
        en_usd = en_tab[f"USD 1926+|h=0.500|b={b_main:.3f}"]
        # employer cap
        D = pd.read_csv(K.OUT / f"sweep_D_cnq_eq{cfg['eq_file']}.csv")
        D = D[(D.asset == "CNQ.TO") & (D.h == 0)]
        emp_tab = {}
        for b in (0.01, 0.02, 0.03, 0.04, b_main):
            v = []
            for Hw in (5, 10):
                d = D[D.H == Hw]
                v.append(float(d[d.fin_add_dd_worst <= b + 1e-9].k.max()))
            emp_tab[f"b={b:.3f}"] = min(v)
        emp_main = emp_tab[f"b={b_main:.3f}"]
        eq_share = cfg["eq_file"] / 100
        implicit = eq_share * 0.3 * load_full  # CA_EQ = 30 % of equity in the sweep base (BNC CA/global split)
        lookthrough_L = round(implicit + en_main, 3)
        out["pockets"][p] = {
            "energy_base_implicit_ca_eq": round(implicit, 4),
            "energy_lookthrough_limit_L": lookthrough_L,
            "energy_lookthrough_limit_rule": "L = implicit energy of the sweep base (eq share x 0.3 x CA_EQ loading) + direct cap (CAD, h=1/2, b)",
            "horizon_years": H, "capacity_rule_limit_months": lim, "capacity": cap_rows,
            "willingness_q10_inferred": WILL_Q10, "capacity_maxdd": cap, "applied_maxdd": applied, "binding": winner,
            "amf_profile_retained": "3 Équilibré (Q7) -> Q10 case of profile 3 = 15 % (sensitivity)",
            "budget_b": b_main,
            "energy_direct_cap": min(en_main, en_usd), "energy_cap_cad": en_main, "energy_cap_usd": en_usd,
            "energy_cap_sensitivity": en_tab,
            "employer_cap_cnq": emp_main, "employer_cap_sensitivity": emp_tab,
            "ca_eq_cap_implied_if_no_direct_energy": {"full_loading": round(lookthrough_L / load_full, 3),
                                  **{k: round(lookthrough_L / v, 3) for k, v in load_blocks.items() if v > 0}},
        }
    hh = out["pockets"]
    out["household"] = {"energy_direct_cap": min(hh[p]["energy_direct_cap"] for p in hh),
                        "energy_lookthrough_limit_L": min(hh[p]["energy_lookthrough_limit_L"] for p in hh),
                        "employer_cap_cnq": min(hh[p]["employer_cap_cnq"] for p in hh),
                        "rule": "household level = lowest pocket value (one energy factor hits all pockets at once)"}
    p = K.dump("derived_thresholds.json", out)
    print(json.dumps({k: v for k, v in out.items() if k != "rules"}, indent=1))
    print(p)


if __name__ == "__main__":
    main()
