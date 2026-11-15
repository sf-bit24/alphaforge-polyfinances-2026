"""Persona 35 - which USD share of ASSETS (u) best covers a mixed CAD/USD SPENDING basket (USD share s)?

Spending-currency reasoning: every result is measured in units of Denise's spending basket
(deflator = common.basket_inflation(s)), i.e. CAD cost of s USD-goods (US CPI x USDCAD) + (1-s) CAD-goods (CPI CA).
For each u in 0..100 % (step 5) we look at ALL rolling windows (step 1 month) of H years:
  M1 = annualised basket-real return (TWR);
  M2 = coverage of a run-down liability: wealth 1 at start, monthly withdrawal of 1/(12 H) basket units
       (a liability spent evenly over H years, converted at the rate of the moment for its USD part);
       coverage = 1 + final basket wealth / total withdrawals  (< 1 = could not pay all spending).
Derived rule (proposition): u* = argmax over u of the WORST coverage (minimises the worst shortfall);
ties (within 0.001) -> the u closest to s. Also u_mv = argmin volatility of the basket-real return.
Layers:
  cash   : u UST_TBILL + (1-u) CA_TBILL          (pure currency matching, 1971+)
  bonds  : u UST_10Y  + (1-u) CA_GOV_10Y          (1971+)
  e20/e40/e60 : e [u US_MKT + (1-u) CA_EQ] + (1-e) [u UST_10Y + (1-u) CA_GOV_10Y]   (1977+, CA_EQ limiting)
Monthly rebalancing (assumption, linear in u). FX risk split: 'useful' = FX exposure that offsets USD spending
(min(u,s)), 'unwanted' = |u - s|; FX-driven vol = vol(actual) - vol(constant-FX counterfactual).
Outputs results/p35_analysis/usd_share.json. SIMULATION ONLY - no FX forecast.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd

import common as C
from engine.data import load_inflation, load_returns

US_GRID = np.round(np.arange(0, 1.0001, 0.05), 2)
S_GRID = [0.3, 0.4, 0.5, 0.6, 0.7]
H_GRID = [1, 8, 15]
LAYERS = {"cash": (0.0, ("UST_TBILL", "CA_TBILL"), None, "1971-02"),
          "bonds": (0.0, ("UST_10Y", "CA_GOV_10Y"), None, "1971-02"),
          "e20": (0.2, ("UST_10Y", "CA_GOV_10Y"), ("US_MKT", "CA_EQ"), "1977-01"),
          "e40": (0.4, ("UST_10Y", "CA_GOV_10Y"), ("US_MKT", "CA_EQ"), "1977-01"),
          "e60": (0.6, ("UST_10Y", "CA_GOV_10Y"), ("US_MKT", "CA_EQ"), "1977-01")}


def port(Rc: pd.DataFrame, e: float, fi: tuple, eq: tuple | None, u: float) -> np.ndarray:
    r = (1 - e) * (u * Rc[fi[0]] + (1 - u) * Rc[fi[1]])
    if eq:
        r = r + e * (u * Rc[eq[0]] + (1 - u) * Rc[eq[1]])
    return r.values


def rolling_stats(r: np.ndarray, b: np.ndarray, H: int) -> dict:
    n = 12 * H
    real = (1 + r) / (1 + b) - 1
    lr = np.log1p(real)
    c = np.concatenate([[0.0], np.cumsum(lr)])
    ann = np.expm1((c[n:] - c[:-n]) * 12 / n)
    covs = []
    wd = 1.0 / n
    for i in range(0, len(real) - n + 1):
        w = 1.0
        for x in real[i:i + n]:
            w = w * (1 + x) - wd           # basket units, withdrawal at month end
        covs.append(1 + w / 1.0)           # total withdrawals = 1 basket unit
    covs = np.array(covs)
    return {"ann_real_p10": float(np.quantile(ann, .1)), "ann_real_worst": float(ann.min()),
            "ann_real_median": float(np.median(ann)), "coverage_worst": float(covs.min()),
            "coverage_p10": float(np.quantile(covs, .1)), "share_coverage_below_1": float((covs < 1).mean()),
            "n_windows": int(len(covs))}


def main() -> dict:
    out = {"definitions": __doc__.split("Layers:")[0].strip(), "layers": {}}
    fx = C.fx_monthly()
    fxr = fx / fx.shift(1) - 1
    for lname, (e, fi, eq, start) in LAYERS.items():
        assets = list(fi) + (list(eq) if eq else [])
        Rc = load_returns(assets, start, "2026-09", "CAD")
        Rl = load_returns(assets, start, "2026-09", "USD")  # for constant-FX counterfactual (local returns)
        # local-currency returns: USD assets in USD, CAD assets in CAD
        Rloc = Rc.copy()
        for a in assets:
            if a.startswith(("US", "UST")):
                Rloc[a] = Rl[a]
        L = {"period": [str(Rc.index.min().date()), str(Rc.index.max().date())], "equity_share": e,
             "assets_usd_side": [fi[0]] + ([eq[0]] if eq else []), "assets_cad_side": [fi[1]] + ([eq[1]] if eq else []),
             "by_s": {}}
        for s in S_GRID:
            b = C.basket_inflation(s, "CAD").reindex(Rc.index).values
            # constant-FX counterfactual basket: CPI only
            b0 = (s * load_inflation("USD").reindex(Rc.index) + (1 - s) * load_inflation("CAD").reindex(Rc.index)).values
            grid = {}
            for u in US_GRID:
                r = port(Rc, e, fi, eq, u)
                r0 = port(Rloc, e, fi, eq, u)
                real = (1 + r) / (1 + b) - 1
                real0 = (1 + r0) / (1 + b0) - 1
                g = {"vol_basket_real": float(np.std(real, ddof=1) * np.sqrt(12)),
                     "vol_basket_real_constant_fx": float(np.std(real0, ddof=1) * np.sqrt(12)),
                     "fx_exposure_useful": float(min(u, s)), "fx_exposure_unwanted": float(abs(u - s))}
                g["fx_driven_vol"] = g["vol_basket_real"] - g["vol_basket_real_constant_fx"]
                for H in H_GRID:
                    g[f"H{H}"] = rolling_stats(r, b, H)
                grid[f"{u:.2f}"] = g
            best = {}
            for H in H_GRID:
                wc = np.array([grid[f"{u:.2f}"][f"H{H}"]["coverage_worst"] for u in US_GRID])
                p10 = np.array([grid[f"{u:.2f}"][f"H{H}"]["coverage_p10"] for u in US_GRID])
                ok = np.where(wc >= wc.max() - 1e-3)[0]
                u_star = float(US_GRID[ok[np.argmin(np.abs(US_GRID[ok] - s))]])
                ok_band = US_GRID[wc >= wc.max() - 0.01]
                best[f"H{H}"] = {"u_star_worst_coverage": u_star, "worst_coverage_at_u_star": float(wc.max()),
                                 "u_argmax_exact": float(US_GRID[int(np.argmax(wc))]),
                                 "u_band_within_1pt_of_best_worst": [float(ok_band.min()), float(ok_band.max())],
                                 "u_star_p10_coverage": float(US_GRID[int(np.argmax(p10))]),
                                 "worst_coverage_at_u0": float(wc[0]), "worst_coverage_at_u_eq_s":
                                     float(wc[int(np.argmin(np.abs(US_GRID - s)))]), "worst_coverage_at_u1": float(wc[-1])}
            vols = np.array([grid[f"{u:.2f}"]["vol_basket_real"] for u in US_GRID])
            best["u_min_vol"] = float(US_GRID[int(np.argmin(vols))])
            L["by_s"][f"{s:.1f}"] = {"best": best, "grid": grid}
        out["layers"][lname] = L
    return out


if __name__ == "__main__":
    res = main()
    p = C.write_trace("usd_share", res, {"u_grid": US_GRID.tolist(), "s_grid": S_GRID, "H_grid": H_GRID,
                                         "rebalancing": "monthly", "step": "1 month rolling"}, "usd_share.py")
    for ln, L in res["layers"].items():
        print("==", ln, L["period"])
        for s, d in L["by_s"].items():
            b = d["best"]
            print(f"  s={s} u_minvol={b['u_min_vol']:.2f} " + " | ".join(
                f"H{H}: u*={b[f'H{H}']['u_star_worst_coverage']:.2f} band={b[f'H{H}']['u_band_within_1pt_of_best_worst']} "
                f"wc*={b[f'H{H}']['worst_coverage_at_u_star']:.3f} wc(u=s)={b[f'H{H}']['worst_coverage_at_u_eq_s']:.3f} "
                f"wc0={b[f'H{H}']['worst_coverage_at_u0']:.3f} wc1={b[f'H{H}']['worst_coverage_at_u1']:.3f}" for H in H_GRID))
    print(p)
