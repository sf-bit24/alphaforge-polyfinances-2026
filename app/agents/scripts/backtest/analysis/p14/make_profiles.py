"""Persona 14 (Tyler) - writes profiles/p14_*.yaml from results/p14_analysis/derived_thresholds.json.
SIMULATION ONLY - not financial advice. Persona inputs used: identity, RRTTLLU (qualitative), goals/horizons,
biases, test criteria. NO allocation, threshold or market fact from the persona file.

Pockets (from analyse/relation-profils-actifs, persona 14 rows):
  coussin  (layoff buffer, immediate, AMF 1)       horizon of the window = 1 year (a layoff spell spends it)
  etudes   (children's education, 10 y, AMF 3)     window = 10 years
  retraite (early retirement at ~55, 16-20 y)      window = 16 years (39 -> 55), sensitivity 20
Variants: <base> = derived limits (max DD = min(capacity, willingness), energy look-through <= L, CA_EQ energy
loading override from the return-based estimate) ; _libre = same without energy cap ; _volonte = willingness
max DD (0.30) instead of the binding capacity (etudes only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as K  # noqa: E402

import yaml  # noqa: E402

PROF = K.BT / "profiles"
T = json.loads((K.OUT / "derived_thresholds.json").read_text())
LOAD = round(T["ca_eq_energy_loading_full"], 3)

BNC = {"prudent": (0.80, 0.06, 0.14), "conservateur": (0.70, 0.09, 0.21), "pondere": (0.55, 0.135, 0.315),
       "equilibre": (0.40, 0.18, 0.42), "croissance": (0.20, 0.24, 0.56), "actions": (0.0, 0.30, 0.70)}


def r6(d):
    return {k: round(v, 6) for k, v in d.items() if v}


def bnc_w(era, fi, ca, gl, us="US_MKT"):
    if era == "cad":
        return r6({"CA_GOV_10Y": fi, "CA_EQ": ca, us: gl})
    # USD era: no Canadian equity before 1977 -> CA share folded into the US market (documented assumption)
    return r6({"UST_10Y": fi, us: ca + gl})


def static(era, eq, extra=None):
    if era == "cad":
        w = {"CA_EQ": 0.3 * eq, "US_MKT_XEN": 0.7 * eq, "CA_GOV_10Y": 1 - eq}
    else:
        w = {"US_MKT_XEN": eq, "UST_5Y": (1 - eq) / 2, "UST_10Y": (1 - eq) / 2}
    if extra:
        scale = 1 - sum(extra.values())
        w = {k: v * scale for k, v in w.items()}
        w.update(extra)
    return r6(w)


def strategies(era, pocket):
    S = []
    for n, (fi, ca, gl) in BNC.items():
        S.append({"name": f"bnc_{n}", "type": "static", "params": {"weights": bnc_w(era, fi, ca, gl)}})
    for n in ("equilibre", "croissance"):
        fi, ca, gl = BNC[n]
        S.append({"name": f"bnc_{n}_xen", "type": "static", "params": {"weights": bnc_w(era, fi, ca, gl, "US_MKT_XEN")}})
    for eq in (0.4, 0.5, 0.6, 0.7, 0.8):
        S.append({"name": f"xen_eq{int(eq*100)}", "type": "static", "params": {"weights": static(era, eq)}})
    S.append({"name": "request_eq60_energy20", "type": "static", "params": {"weights": static(era, 0.6, {"US_IND_ENRGY": 0.2})}})
    S.append({"name": "xen_eq60_defensive", "type": "static",
              "params": {"weights": static(era, 0.6, {"US_IND_HLTH": 0.08, "US_IND_NODUR": 0.08, "US_IND_UTILS": 0.04})}})
    if era == "cad":
        S.append({"name": "xen_eq60_gold10", "type": "static", "params": {"weights": static(era, 0.6, {"GOLD": 0.10})}})
    hi, lo = (0.7, 0.3) if pocket == "etudes" else (0.8, 0.5)
    cash = "CA_TBILL" if era == "cad" else "UST_TBILL"
    end = static(era, lo)
    if pocket == "etudes":
        end = {k: v * 0.8 for k, v in end.items()}
        end[cash] = 0.2
    S.append({"name": f"glide_{int(hi*100)}_{int(lo*100)}", "type": "glidepath",
              "params": {"start_weights": static(era, hi), "end_weights": r6(end)}})
    S.append({"name": "risk_parity_iv36", "type": "risk_parity", "params": {"lookback": 36, "method": "inverse_vol", "exclude": [cash]}})
    S.append({"name": "min_variance_60", "type": "min_variance", "params": {"lookback": 60}})
    S.append({"name": "mean_var_60_ra4", "type": "mean_variance", "params": {"lookback": 60, "mu_shrink": 0.5, "risk_aversion": 4}})
    S.append({"name": "trend10_eq60", "type": "trend_filter", "rebalancing": {"frequency": "monthly"},
              "params": {"ma_months": 10, "base_weights": static(era, 0.6), "always_hold": ["CA_GOV_10Y" if era == "cad" else "UST_5Y"]}})
    cands = (["CA_EQ", "US_MKT_XEN", "CA_GOV_10Y", "GOLD"] if era == "cad" else ["US_MKT_XEN", "UST_10Y", "CORP_AAA", "US_IND_HLTH"])
    S.append({"name": "dual_mom12_top2", "type": "momentum", "rebalancing": {"frequency": "monthly"},
              "params": {"lookback": 12, "top_k": 2, "absolute": True, "candidates": cands}})
    return S


def risky_profile(pocket, era, variant):
    P = T["pockets"][pocket]
    H = P["horizon_years"]
    maxdd = P["applied_maxdd"] if variant != "volonte" else P["willingness_q10_inferred"]
    if era == "cad":
        uni = ["CA_EQ", "US_MKT_XEN", "US_MKT", "US_IND_ENRGY", "US_IND_HLTH", "US_IND_NODUR", "US_IND_UTILS",
               "CA_GOV_10Y", "UST_5Y", "GOLD", "CA_TBILL"]
        cash, start = "CA_TBILL", "1977-01"
        fb = static("cad", 0.5)
    else:
        uni = ["US_MKT_XEN", "US_MKT", "US_IND_ENRGY", "US_IND_HLTH", "US_IND_NODUR", "US_IND_UTILS",
               "UST_2Y", "UST_5Y", "UST_10Y", "CORP_AAA", "UST_TBILL"]
        cash, start = "UST_TBILL", "1926-08"
        fb = static("usd", 0.5)
    groups = []
    if variant != "libre":
        groups.append({"name": "energy_lookthrough", "exposure": "energy", "max": P["energy_lookthrough_limit_L"]})
    pid = f"p14_{pocket}_{era}" + ("" if variant == "base" else f"_{variant}")
    desc = (f"Tyler (persona 14) - pocket {pocket}, window {H} y, {era.upper()} era, variant {variant}. "
            f"maxDD {maxdd} (min capacity/willingness, analysis/p14/derive.py); energy look-through <= "
            f"{P['energy_lookthrough_limit_L'] if variant != 'libre' else 'none'}; CA_EQ energy={LOAD} (return-based estimate, "
            "results/p14_analysis/energy_style_ca_eq.csv - NOT holdings). Crypto: status 'pas maintenant' -> not in universe. "
            "USD era: investor in USD (no CAD before 1971), BNC CA share folded into US_MKT. SIMULATION ONLY.")
    return pid, {
        "id": pid, "description": desc, "currency": era.upper(), "fx_fill": "none", "horizon_years": H,
        "mode": "non_overlapping", "step_months": 12, "period": {"start": start, "end": "2026-09"},
        "universe": uni, "cash_asset": cash,
        "objective": {"type": "min_shortfall", "target_real_return": 0.0},
        "constraints": {"default_bounds": [0.0, 1.0], "exclude": {"assets": [], "tags": [], "classes": ["crypto"]},
                        "groups": groups, "exposure_overrides": {"CA_EQ": {"energy": LOAD}} if era == "cad" else {}},
        "risk_limits": {"max_vol": None, "max_drawdown": maxdd, "max_cvar_5": None},
        "flows": {"initial": 1.0, "monthly": 0.0, "indexed_to_inflation": True},
        "rebalancing": {"frequency": "annual", "band": 0.05}, "costs_bps": 10, "fallback_weights": fb,
        "strategies": strategies(era, pocket),
        "selection": {"quantile": 0.10, "max_breach_rate": 0.25, "min_past_windows": 3},
        "oracle": {"enabled": True, "n_starts": 6}, "seed": 42}


def cushion_profile(era):
    if era == "cad":
        uni, cash, start = ["CA_TBILL", "CA_GOV_10Y", "UST_TBILL", "UST_2Y"], "CA_TBILL", "1971-02"
        S = [{"name": "cad_cash100", "type": "static", "params": {"weights": {"CA_TBILL": 1.0}}},
             {"name": "cad_cash75_ca10y25", "type": "static", "params": {"weights": {"CA_TBILL": 0.75, "CA_GOV_10Y": 0.25}}},
             {"name": "cad_ca10y100", "type": "static", "params": {"weights": {"CA_GOV_10Y": 1.0}}},
             {"name": "usd_tbill100_unhedged", "type": "static", "params": {"weights": {"UST_TBILL": 1.0}}},
             {"name": "usd_2y100_unhedged", "type": "static", "params": {"weights": {"UST_2Y": 1.0}}},
             {"name": "cad_cash50_usd2y50", "type": "static", "params": {"weights": {"CA_TBILL": 0.5, "UST_2Y": 0.5}}}]
    else:
        uni, cash, start = ["UST_TBILL", "UST_2Y", "UST_5Y", "UST_10Y"], "UST_TBILL", "1926-08"
        S = [{"name": "tbill100", "type": "static", "params": {"weights": {"UST_TBILL": 1.0}}},
             {"name": "tbill75_2y25", "type": "static", "params": {"weights": {"UST_TBILL": 0.75, "UST_2Y": 0.25}}},
             {"name": "tbill50_2y50", "type": "static", "params": {"weights": {"UST_TBILL": 0.5, "UST_2Y": 0.5}}},
             {"name": "ust2y100", "type": "static", "params": {"weights": {"UST_2Y": 1.0}}},
             {"name": "ust5y100", "type": "static", "params": {"weights": {"UST_5Y": 1.0}}},
             {"name": "ust10y100", "type": "static", "params": {"weights": {"UST_10Y": 1.0}}}]
    S.append({"name": "min_variance_36", "type": "min_variance", "params": {"lookback": 36}})
    pid = f"p14_coussin_{era}"
    return pid, {
        "id": pid, "description": ("Tyler (persona 14) - layoff buffer (AMF 1 Sécurité, horizon immediate). Window 1 y. "
                                   "max DD 0.01 = AMF Q10 case 0 % for profile 1 [inf] + 1 pt measurement tolerance (proposal). "
                                   "Equities, gold, crypto excluded (status 'exclu', AMF Q3). SIMULATION ONLY."),
        "currency": era.upper(), "fx_fill": "none", "horizon_years": 1, "mode": "non_overlapping", "step_months": 12,
        "period": {"start": start, "end": "2026-09"}, "universe": uni, "cash_asset": cash,
        "objective": {"type": "max_real_return"},
        "constraints": {"default_bounds": [0.0, 1.0], "exclude": {"assets": [], "tags": [], "classes": ["crypto"]}, "groups": []},
        "risk_limits": {"max_vol": None, "max_drawdown": 0.01, "max_cvar_5": None},
        "flows": {"initial": 1.0, "monthly": 0.0, "indexed_to_inflation": True},
        "rebalancing": {"frequency": "monthly", "band": 0.05}, "costs_bps": 10,
        "fallback_weights": {cash: 1.0}, "strategies": S,
        "selection": {"quantile": 0.10, "max_breach_rate": 0.05, "min_past_windows": 3},
        "oracle": {"enabled": True, "n_starts": 4}, "seed": 42}


def main():
    made = []
    jobs = [cushion_profile("usd"), cushion_profile("cad")]
    for era in ("usd", "cad"):
        for v in ("base", "libre", "volonte"):
            jobs.append(risky_profile("etudes", era, v))
        for v in ("base", "libre"):
            jobs.append(risky_profile("retraite", era, v))
    for pid, p in jobs:
        f = PROF / f"{pid}.yaml"
        head = "# Generated by analysis/p14/make_profiles.py - persona 14 (Tyler). SIMULATION ONLY - not financial advice.\n"
        f.write_text(head + yaml.safe_dump(p, sort_keys=False, allow_unicode=True, width=200))
        made.append(pid)
    print(made)




def titles_profile(variant):
    """CAD 1995-02+ with the real single stocks (CNQ.TO employer, ENB.TO, XOM, JNJ, PG) - pocket etudes limits (10 y)."""
    P = T["pockets"]["etudes"]
    uni = ["CA_EQ", "US_MKT_XEN", "CNQ.TO", "ENB.TO", "XOM", "JNJ", "PG", "CA_GOV_10Y", "GOLD", "CA_TBILL"]
    groups, asset_bounds = [], {}
    if variant == "base":
        groups.append({"name": "energy_lookthrough", "exposure": "energy", "max": P["energy_lookthrough_limit_L"]})
        asset_bounds = {"CNQ.TO": [0.0, P["employer_cap_cnq"]]}
    core = {"CA_EQ": 0.15, "US_MKT_XEN": 0.35, "CA_GOV_10Y": 0.5}
    S = [{"name": "xen_eq50", "type": "static", "params": {"weights": core}},
         {"name": "bnc_equilibre_xen", "type": "static", "params": {"weights": {"CA_GOV_10Y": 0.4, "CA_EQ": 0.18, "US_MKT_XEN": 0.42}}}]
    for k in (0.45, 0.20, 0.05, 0.025):
        w = {a: v * (1 - k) for a, v in core.items()}
        w["CNQ.TO"] = k
        S.append({"name": f"etat_cnq{k*100:g}", "type": "static", "params": {"weights": r6(w)}})
    w = {a: v * 0.35 for a, v in core.items()}
    w.update({"CNQ.TO": 0.45, "ENB.TO": 0.10, "XOM": 0.10})
    S.append({"name": "etat_cnq45_plus_demande_enb10_xom10", "type": "static", "params": {"weights": r6(w)}})
    w = {a: v * 0.84 for a, v in core.items()}
    w.update({"JNJ": 0.08, "PG": 0.08})
    S.append({"name": "xen_eq50_defensive_jnj_pg", "type": "static", "params": {"weights": r6(w)}})
    S.append({"name": "risk_parity_iv36", "type": "risk_parity", "params": {"lookback": 36, "method": "inverse_vol", "exclude": ["CA_TBILL"]}})
    S.append({"name": "min_variance_60", "type": "min_variance", "params": {"lookback": 60}})
    pid = "p14_titres_cad" + ("" if variant == "base" else "_libre")
    return pid, {
        "id": pid, "description": ("Tyler (persona 14) - CAD 1995-02+ with real single stocks (Yahoo before 2021-12, starter after). "
                                   f"Etudes limits: maxDD {P['applied_maxdd']}" + (f", energy look-through <= {P['energy_lookthrough_limit_L']}, CNQ.TO <= {P['employer_cap_cnq']}" if variant == "base" else ", no energy/employer cap")
                                   + ". Survivorship bias: tickers chosen in 2026. SIMULATION ONLY."),
        "currency": "CAD", "fx_fill": "none", "horizon_years": 10, "mode": "rolling", "step_months": 12,
        "period": {"start": "1995-02", "end": "2026-09"}, "universe": uni, "cash_asset": "CA_TBILL",
        "objective": {"type": "min_shortfall", "target_real_return": 0.0},
        "constraints": {"default_bounds": [0.0, 1.0], "asset_bounds": asset_bounds, "exclude": {"assets": [], "tags": [], "classes": ["crypto"]},
                        "groups": groups, "exposure_overrides": {"CA_EQ": {"energy": LOAD}}},
        "risk_limits": {"max_vol": None, "max_drawdown": P["applied_maxdd"], "max_cvar_5": None},
        "flows": {"initial": 1.0, "monthly": 0.0, "indexed_to_inflation": True},
        "rebalancing": {"frequency": "annual", "band": 0.05}, "costs_bps": 10, "fallback_weights": core,
        "strategies": S, "selection": {"quantile": 0.10, "max_breach_rate": 0.25, "min_past_windows": 3},
        "oracle": {"enabled": True, "n_starts": 6}, "seed": 42}


def write_titles():
    for v in ("base", "libre"):
        pid, p = titles_profile(v)
        (PROF / f"{pid}.yaml").write_text("# Generated by analysis/p14/make_profiles.py (titles) - persona 14. SIMULATION ONLY.\n"
                                          + yaml.safe_dump(p, sort_keys=False, allow_unicode=True, width=200))
        print(pid)


if __name__ == "__main__":
    if sys.argv[1:] == ["titles"]:
        write_titles()
    else:
        main()
