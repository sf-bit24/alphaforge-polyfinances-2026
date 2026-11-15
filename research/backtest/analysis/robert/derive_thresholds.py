"""Derive Robert's risk thresholds from the data (sensitivity grid), instead of taking them from the persona doc.

Grid: static monthly-rebalanced mixes  e * EQUITY + (1 - e) * BOND_LEG, e = 0..100 % step 10,
BOND_LEG in {T-bill, 2y, 5y, 10y, 20y} (USD era) or {CA T-bill, CA 10y} (CAD era).
For each mix: full-history max drawdown and longest peak-to-recovery (nominal), and on rolling
3/4/5-year windows (step 1 month): P(real loss), 10th pct / worst annualised real return, worst in-window maxDD.

Derivation rule (readable, proposed to the team):
  Robert cannot wait longer than his horizon H to get back to his previous peak.
  -> admissible mix = longest nominal underwater period over the era <= H*12 months.
  -> loss capacity L*(H) = deepest full-history maxDD among admissible mixes;
     vol*(H), CVaR*(H) = those of the same boundary mix (monthly rebalanced).
Run:  .venv/bin/python -I analysis/robert/derive_thresholds.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from common import longest_underwater, rolling_maxdd, rolling_real, write_trace
from engine import metrics as M
from engine.data import load_inflation, load_returns

ERAS = {
    "usd_1926": dict(currency="USD", start="1926-08", eq="US_MKT", legs=["UST_TBILL", "UST_2Y", "UST_5Y", "UST_10Y", "UST_20Y"]),
    "usd_1962": dict(currency="USD", start="1962-01", eq="US_MKT", legs=["UST_TBILL", "UST_2Y", "UST_5Y", "UST_10Y", "UST_20Y"]),
    "cad_1977": dict(currency="CAD", start="1977-01", eq="CA_EQ", legs=["CA_TBILL", "CA_GOV_10Y"]),
}
GRID = np.round(np.arange(0, 1.0001, 0.1), 2)


def main():
    out, derived = {}, {}
    for era, cfg in ERAS.items():
        R = load_returns([cfg["eq"], *cfg["legs"]], start=cfg["start"], currency=cfg["currency"])
        infl = load_inflation(cfg["currency"]).reindex(R.index).values
        rows = []
        for leg in cfg["legs"]:
            for e in GRID:
                port = e * R[cfg["eq"]].values + (1 - e) * R[leg].values
                lu, cens = longest_underwater(port)
                v, cv = M.var_cvar(port)
                row = {"equity_share": float(e), "bond_leg": leg, "max_dd_full": M.max_drawdown(port),
                       "longest_underwater_m": lu, "underwater_censored": cens, "vol": M.volatility(port),
                       "cvar_5": cv, "ann_real_full": M.annualized_real_return(port, infl)}
                for h in (3, 4, 5):
                    rr = rolling_real(port, infl, 12 * h)
                    row[f"h{h}_p_real_loss"] = float(np.mean(rr < 0))
                    row[f"h{h}_real_p10"] = float(np.quantile(rr, 0.10))
                    row[f"h{h}_real_worst"] = float(rr.min())
                    row[f"h{h}_real_median"] = float(np.median(rr))
                    row[f"h{h}_inwin_dd_worst"] = float(rolling_maxdd(port, 12 * h, step=3).max())
                rows.append(row)
        df = pd.DataFrame(rows)
        out[era] = {"info": R.attrs["info"], "grid": df.to_dict(orient="records")}
        derived[era] = {}
        for h in (3, 4, 5):
            adm = df[df["longest_underwater_m"] <= 12 * h]
            if adm.empty:
                derived[era][f"h{h}"] = None
                continue
            b = adm.sort_values(["max_dd_full", "equity_share"]).iloc[-1]
            # max equity share admissible per bond leg (reported for transparency)
            emax = adm.groupby("bond_leg")["equity_share"].max().to_dict()
            derived[era][f"h{h}"] = {"rule": f"longest nominal underwater <= {12*h} months",
                                     "boundary_mix": {"equity_share": b["equity_share"], "bond_leg": b["bond_leg"]},
                                     "L_star_max_drawdown": b["max_dd_full"], "vol_star": b["vol"],
                                     "cvar5_star": b["cvar_5"], "boundary_longest_underwater_m": int(b["longest_underwater_m"]),
                                     "max_equity_share_by_leg": emax}
        print(f"\n=== {era} {R.attrs['info']['effective']} ===")
        cols = ["equity_share", "bond_leg", "max_dd_full", "longest_underwater_m", "vol", "cvar_5",
                "h4_p_real_loss", "h4_real_p10", "h4_real_worst", "h4_inwin_dd_worst"]
        print(df[cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        print("derived:", derived[era])
    p = write_trace("derive_thresholds", {"eras": out, "derived": derived},
                    {"grid": GRID.tolist(), "eras": ERAS, "rebalancing": "monthly, no costs"})
    print("trace:", p)


if __name__ == "__main__":
    main()
