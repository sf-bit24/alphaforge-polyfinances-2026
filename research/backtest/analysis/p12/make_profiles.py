"""Write engine profiles for persona 12 (one per pocket x era) from derived thresholds/caps.

Persona inputs used (identity / objectives / RRTTLLU only): accumulation 6 y (36 -> 42), decumulation ~50 y
(42 -> 92), CAD reference, capital 640 k$ (fictional), target 1.3 M$ at 42, withdrawals 52 k$/y indexed
(fictional), declared savings rate 58 % of 205 k$ gross (fictional; gross vs net unknown -> hypothesis H1 and a
half-contribution stress H2). No allocation, threshold or market fact from the persona file is used.
SIMULATION ONLY.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from scipy.optimize import brentq

from common import BNC, BT, OUT, bnc_weights

thr = json.loads((OUT / "derive_thresholds.json").read_text())["results"]["proposal"]
caps = json.loads((OUT / "derive_caps.json").read_text())["results"]
PROF = BT / "profiles"

W_RATE = 52000 / 1300000          # objective withdrawal rate of the persona (fictional figures)
R_REQ = brentq(lambda r: r / (1 - (1 + r) ** -50) - W_RATE, 1e-6, 0.2)   # real annuity rate funding it over 50 y
CONTRIB_H1 = round(0.58 * 205000 / 12)   # hypothesis H1 (gross basis, upper bound)
GOLD_CAP = 0.05                    # derive_caps.json gold: most prudent non-zero value (CAD 40 % eq: 0.05)


def bnc_strats(fi, ca, gl):
    return [{"name": f"bnc_{k.lower()}", "type": "static", "params": {"weights": bnc_weights(k, fi, ca, gl)}} for k in BNC]


def cad_strats(pocket):
    S = bnc_strats("CA_GOV_10Y", "CA_EQ", "US_MKT")
    S += [
        {"name": "eq100_ca30_us70", "type": "static", "params": {"weights": {"CA_EQ": .3, "US_MKT": .7}}},
        {"name": "eq100_us", "type": "static", "params": {"weights": {"US_MKT": 1.0}}},
        {"name": "eq100_ca", "type": "static", "params": {"weights": {"CA_EQ": 1.0}}},
        {"name": "eq70_gold5_bond25", "type": "static", "params": {"weights": {"CA_EQ": .21, "US_MKT": .49, "GOLD": .05, "CA_GOV_10Y": .25}}},
        {"name": "eq60_buffer10_bond30", "type": "static", "params": {"weights": {"CA_EQ": .18, "US_MKT": .42, "CA_TBILL": .10, "CA_GOV_10Y": .30}}},
        {"name": "eq60_ust5y40", "type": "static", "params": {"weights": {"CA_EQ": .18, "US_MKT": .42, "UST_5Y": .40}}},
        {"name": "dividend_tilt", "type": "static",
         "params": {"weights": {"CA_EQ": .40, "US_MKT": .18, "US_IND_UTILS": .01, "US_IND_MONEY": .01, "CA_GOV_10Y": .40}}},
        {"name": "risk_parity_36m", "type": "risk_parity", "params": {"lookback": 36, "method": "inverse_vol", "exclude": ["CA_TBILL"]}},
        {"name": "min_variance_60m", "type": "min_variance", "params": {"lookback": 60}},
        {"name": "mean_variance_60m", "type": "mean_variance", "params": {"lookback": 60, "mu_shrink": 0.5, "risk_aversion": 4}},
        {"name": "trend_eq60", "type": "trend_filter", "rebalancing": {"frequency": "monthly"},
         "params": {"ma_months": 10, "base_weights": {"CA_EQ": .18, "US_MKT": .42, "CA_GOV_10Y": .40}, "always_hold": ["CA_GOV_10Y"]}},
        {"name": "momentum_core_bond", "type": "momentum", "rebalancing": {"frequency": "monthly"},
         "params": {"lookback": 12, "top_k": 2, "absolute": True, "core_weights": {"CA_GOV_10Y": .4},
                    "candidates": ["CA_EQ", "US_MKT", "US_IND_HLTH", "GOLD", "CA_GOV_10Y"]}},
    ]
    if pocket == "accum":
        S += [{"name": "glide_tent_85_to_55", "type": "glidepath",
               "params": {"start_weights": {"CA_EQ": .255, "US_MKT": .595, "CA_GOV_10Y": .15},
                          "end_weights": {"CA_EQ": .165, "US_MKT": .385, "CA_GOV_10Y": .30, "CA_TBILL": .15}}}]
    else:
        S += [{"name": "glide_rising_40_to_70", "type": "glidepath",
               "params": {"start_weights": {"CA_EQ": .12, "US_MKT": .28, "CA_GOV_10Y": .45, "CA_TBILL": .15},
                          "end_weights": {"CA_EQ": .21, "US_MKT": .49, "CA_GOV_10Y": .30}}}]
    return S


def usd_strats(pocket):
    S = [{"name": f"bnc_{k.lower()}", "type": "static",
          "params": {"weights": {k2: v for k2, v in {"UST_10Y": f, "US_MKT": c + g}.items() if v > 0}}}
         for k, (f, c, g) in BNC.items()]
    S += [
        {"name": "eq100_us", "type": "static", "params": {"weights": {"US_MKT": 1.0}}},
        {"name": "eq60_buffer10_bond30", "type": "static", "params": {"weights": {"US_MKT": .6, "UST_TBILL": .1, "UST_10Y": .3}}},
        {"name": "eq60_ust5y40", "type": "static", "params": {"weights": {"US_MKT": .6, "UST_5Y": .4}}},
        {"name": "eq60_ust2y40", "type": "static", "params": {"weights": {"US_MKT": .6, "UST_2Y": .4}}},
        {"name": "dividend_tilt", "type": "static",
         "params": {"weights": {"US_MKT": .54, "US_IND_UTILS": .03, "US_IND_MONEY": .03, "UST_10Y": .40}}},
        {"name": "risk_parity_36m", "type": "risk_parity", "params": {"lookback": 36, "method": "inverse_vol", "exclude": ["UST_TBILL"]}},
        {"name": "min_variance_60m", "type": "min_variance", "params": {"lookback": 60}},
        {"name": "mean_variance_60m", "type": "mean_variance", "params": {"lookback": 60, "mu_shrink": 0.5, "risk_aversion": 4}},
        {"name": "trend_eq60", "type": "trend_filter", "rebalancing": {"frequency": "monthly"},
         "params": {"ma_months": 10, "base_weights": {"US_MKT": .6, "UST_10Y": .4}, "always_hold": ["UST_10Y"]}},
        {"name": "momentum_core_bond", "type": "momentum", "rebalancing": {"frequency": "monthly"},
         "params": {"lookback": 12, "top_k": 2, "absolute": True, "core_weights": {"UST_5Y": .4},
                    "candidates": ["US_MKT", "US_IND_HLTH", "US_IND_UTILS", "UST_10Y", "UST_5Y"]}},
    ]
    if pocket == "accum":
        S += [{"name": "glide_tent_85_to_55", "type": "glidepath",
               "params": {"start_weights": {"US_MKT": .85, "UST_10Y": .15},
                          "end_weights": {"US_MKT": .55, "UST_10Y": .30, "UST_TBILL": .15}}}]
    else:
        S += [{"name": "glide_rising_40_to_70", "type": "glidepath",
               "params": {"start_weights": {"US_MKT": .40, "UST_10Y": .45, "UST_TBILL": .15},
                          "end_weights": {"US_MKT": .70, "UST_10Y": .30}}}]
    return S


def profile(pid, era, pocket, maxdd, sector_cap, desc, monthly=None):
    usd = era == "usd"
    universe = (["US_MKT", "US_IND_UTILS", "US_IND_MONEY", "US_IND_BUSEQ", "US_IND_HLTH", "UST_10Y", "UST_5Y", "UST_2Y", "UST_TBILL"]
                if usd else
                ["CA_EQ", "US_MKT", "US_IND_UTILS", "US_IND_MONEY", "US_IND_BUSEQ", "US_IND_HLTH", "CA_GOV_10Y", "UST_5Y", "GOLD", "CA_TBILL"])
    bounds = {s: [0.0, sector_cap] for s in ["US_IND_UTILS", "US_IND_MONEY", "US_IND_BUSEQ", "US_IND_HLTH"]}
    if not usd:
        bounds["GOLD"] = [0.0, GOLD_CAP]
    if pocket == "accum":
        obj = {"type": "min_shortfall", "target_real_wealth": 1300000.0}
        flows = {"initial": 640000.0, "monthly": float(monthly if monthly is not None else CONTRIB_H1), "indexed_to_inflation": True}
        H = 6
    else:
        obj = {"type": "min_shortfall", "target_real_return": round(R_REQ, 5)}
        flows = {"initial": 1300000.0, "monthly": -52000 / 12, "indexed_to_inflation": True}
        H = 50 if usd else 30
    return {
        "id": pid, "description": desc, "currency": "USD" if usd else "CAD", "fx_fill": "none", "horizon_years": H,
        "mode": "non_overlapping", "step_months": 12, "period": {"start": "1926-08" if usd else "1977-01", "end": None},
        "universe": universe, "cash_asset": "UST_TBILL" if usd else "CA_TBILL", "objective": obj,
        "constraints": {"default_bounds": [0.0, 1.0], "asset_bounds": bounds,
                        "exclude": {"assets": [], "tags": ["crypto"], "classes": ["crypto"]}, "groups": []},
        "risk_limits": {"max_vol": None, "max_drawdown": round(maxdd, 3), "max_cvar_5": None},
        "flows": flows, "rebalancing": {"frequency": "annual", "band": 0.05}, "costs_bps": 10,
        "fallback_weights": ({"US_MKT": .6, "UST_10Y": .4} if usd else {"CA_EQ": .18, "US_MKT": .42, "CA_GOV_10Y": .4}),
        "strategies": usd_strats(pocket) if usd else cad_strats(pocket),
        "selection": {"quantile": 0.10, "max_breach_rate": 0.10, "min_past_windows": 3},
        "oracle": {"enabled": True, "n_starts": 4}, "seed": 42}


def main():
    a, d = thr["accumulation"], thr["decumulation"]
    sc = {(p, e): caps[p][f"sector_{'usd1926' if e == 'usd' else 'cad1977'}"]["cap"]["0.01"]
          for p in ("accumulation", "decumulation") for e in ("usd", "cad")}
    hdr = ("# Persona 12 (Julien & Mei-Lin, FIRE) - generated by analysis/p12/make_profiles.py. SIMULATION ONLY.\n"
           "# Risk limit = min(willingness AMF Q10 [inf] 0.30, derived capacity) - results/p12_analysis/derive_thresholds.json\n"
           "# Sector caps (proxies of single names) and gold cap - results/p12_analysis/derive_caps.json. PROPOSALS TO VALIDATE.\n")
    specs = [
        ("p12_accum_usd", "usd", "accum", a["effective"], sc[("accumulation", "usd")], "P12 accumulation 6 y, USD 1926+ (US proxies, constant-currency assumption)", None),
        ("p12_accum_cad", "cad", "accum", a["effective"], sc[("accumulation", "cad")], "P12 accumulation 6 y, CAD 1977+", None),
        ("p12_accum_cad_h2", "cad", "accum", a["effective"], sc[("accumulation", "cad")], "P12 accumulation, contribution stress H2 = H1/2", CONTRIB_H1 / 2),
        ("p12_decum_usd", "usd", "decum", d["effective"], sc[("decumulation", "usd")], "P12 decumulation, USD 1926+, 52k/1.3M indexed withdrawals", None),
        ("p12_decum_cad", "cad", "decum", d["effective"], sc[("decumulation", "cad")], "P12 decumulation, CAD 1977+", None),
        ("p12_decum_usd_will", "usd", "decum", d["willingness"], sc[("decumulation", "usd")], "P12 decumulation USD, willingness-only limit", None),
        ("p12_decum_cad_will", "cad", "decum", d["willingness"], sc[("decumulation", "cad")], "P12 decumulation CAD, willingness-only limit", None),
    ]
    for pid, era, pocket, mdd, cap, desc, monthly in specs:
        p = profile(pid, era, pocket, mdd, cap, desc, monthly)
        (PROF / f"{pid}.yaml").write_text(hdr + f"# R_REQ (real annuity rate for 4.0 % over 50 y) = {R_REQ:.5f}; contribution H1 = {CONTRIB_H1}/month\n"
                                          + yaml.safe_dump(p, sort_keys=False, allow_unicode=True))
        print(pid, mdd, cap)
    print("R_REQ", R_REQ, "CONTRIB_H1", CONTRIB_H1)


if __name__ == "__main__":
    main()
