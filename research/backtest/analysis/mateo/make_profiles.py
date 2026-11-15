"""Generate the Mateo profile YAMLs (profiles/mateo*.yaml) so that the with/without-exclusion variants are
strictly parallel (same strategies, only the core equity asset and exclusions differ).

Every threshold written here is DERIVED in reports/mateo.md (stage A sensitivity) - see DERIVED below.
Persona-document allocations/thresholds are NOT used. SIMULATION ONLY.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
PROF = HERE.parent.parent / "profiles"

# Filled after stage A (derived). Stage A itself runs with no equity band and no risk limits.
DERIVED_FILE = HERE / "derived_thresholds.json"
SECTORS = ["US_IND_NODUR", "US_IND_DURBL", "US_IND_MANUF", "US_IND_ENRGY", "US_IND_CHEMS", "US_IND_BUSEQ",
           "US_IND_TELCM", "US_IND_UTILS", "US_IND_SHOPS", "US_IND_HLTH", "US_IND_MONEY", "US_IND_OTHER"]
LADDER_USD = {"UST_2Y": 1 / 3, "UST_5Y": 1 / 3, "UST_10Y": 1 / 3}

ERAS = {
    # era id: universe, cash, currency, fx_fill, start, bonds ladder, gold?
    "usd_long": dict(currency="USD", fx_fill="none", start="1926-07", cash="UST_TBILL",
                     universe=["US_MKT", "US_MKT_XEN"] + SECTORS + ["UST_2Y", "UST_5Y", "UST_10Y", "UST_20Y", "CORP_AAA", "UST_TBILL"],
                     ladder=LADDER_USD, gold=None, ca_eq=None),
    "usd_gold": dict(currency="USD", fx_fill="none", start="1975-01", cash="UST_TBILL",
                     universe=["US_MKT", "US_MKT_XEN"] + SECTORS + ["UST_2Y", "UST_5Y", "UST_10Y", "UST_20Y", "CORP_AAA", "GOLD", "UST_TBILL"],
                     ladder=LADDER_USD, gold="GOLD", ca_eq=None),
    "cad": dict(currency="CAD", fx_fill="none", start="1977-01", cash="CA_TBILL",
                universe=["CA_EQ", "US_MKT", "US_MKT_XEN", "US_IND_ENRGY", "US_IND_BUSEQ", "US_IND_HLTH", "US_IND_NODUR",
                          "US_IND_UTILS", "US_IND_MONEY", "CA_GOV_10Y", "UST_5Y", "GOLD", "CA_TBILL"],
                ladder={"CA_GOV_10Y": 0.5, "CA_TBILL": 0.0, "UST_5Y": 0.5}, gold="GOLD", ca_eq="CA_EQ"),
}
# exclusion variants: which core equity, which exclusions
VARIANTS = {
    "base": dict(core="US_MKT", exclude_assets=["US_MKT_XEN"], exclude_tags=[]),
    "esg": dict(core="US_MKT_XEN", exclude_assets=["US_MKT"], exclude_tags=["fossil_fuel"]),
    # CAD only: strict = also drop CA_EQ (TSX energy share unknown: no Canadian sector data)
    "esgstrict": dict(core="US_MKT_XEN", exclude_assets=["US_MKT", "CA_EQ"], exclude_tags=["fossil_fuel"]),
}


def equity_core(era, var, e):
    """Equity sleeve of weight e: core (US) market, + Canadian market in CAD era (home bias 1/2) unless excluded."""
    core = VARIANTS[var]["core"]
    ca = ERAS[era]["ca_eq"]
    if ca and ca not in VARIANTS[var]["exclude_assets"]:
        return {core: e / 2, ca: e / 2}
    return {core: e}


def mix(era, var, e, gold=0.0):
    w = equity_core(era, var, e)
    rest = 1 - e - gold
    for a, x in ERAS[era]["ladder"].items():
        if x:
            w[a] = w.get(a, 0) + rest * x
    if gold:
        w[ERAS[era]["gold"]] = gold
    return {k: round(v, 6) for k, v in w.items()}


def strategies(era, var, derived):
    E = ERAS[era]
    core = VARIANTS[var]["core"]
    g = E["gold"]
    e_mid = derived["equity_policy"] if derived else 0.6
    out = []
    shares = derived["static_grid"] if derived else [round(0.1 * i, 1) for i in range(0, 11)]
    for e in shares:
        out.append({"name": f"static_eq{int(round(e * 100)):02d}", "type": "static", "params": {"weights": mix(era, var, e)}})
    if not derived:
        return out
    if g:
        out.append({"name": f"static_eq{int(e_mid*100)}_gold", "type": "static",
                    "params": {"weights": mix(era, var, e_mid, gold=derived["gold_test"])}})
    hi, lo = derived["glide_start"], derived["glide_end"]
    out.append({"name": f"glidepath_lin_{int(hi*100)}_{int(lo*100)}", "type": "glidepath",
                "params": {"start_weights": mix(era, var, hi), "end_weights": mix(era, var, lo)}})
    for p0 in derived["derisk_starts"]:
        out.append({"name": f"glide_delay{int(round(p0*10))}y_{int(hi*100)}_{int(lo*100)}", "type": "delayed_glidepath",
                    "params": {"start_weights": mix(era, var, hi), "end_weights": mix(era, var, lo), "derisk_start": p0}})
    bonds = [a for a in E["ladder"] if E["ladder"][a]]
    rp_assets = list(equity_core(era, var, 1).keys()) + bonds + ["CORP_AAA" if "CORP_AAA" in E["universe"] else None] + ([g] if g else [])
    rp_assets = [a for a in rp_assets if a]
    out += [
        {"name": "risk_parity_iv36", "type": "risk_parity",
         "params": {"lookback": 36, "method": "inverse_vol", "exclude": [a for a in E["universe"] if a not in rp_assets]}},
        {"name": "min_variance_60", "type": "min_variance", "params": {"lookback": 60}},
        {"name": "max_sharpe_60", "type": "max_sharpe", "params": {"lookback": 60, "mu_shrink": 0.75}},
        {"name": "mean_var_60_ra4", "type": "mean_variance", "params": {"lookback": 60, "mu_shrink": 0.75, "risk_aversion": 4}},
        {"name": "mean_var_60_ra10", "type": "mean_variance", "params": {"lookback": 60, "mu_shrink": 0.75, "risk_aversion": 10}},
        {"name": "trend10_policy", "type": "trend_filter", "rebalancing": {"frequency": "monthly"},
         "params": {"ma_months": 10, "base_weights": mix(era, var, e_mid), "always_hold": bonds}},
    ]
    sect = [a for a in E["universe"] if a.startswith("US_IND_") and not (var != "base" and a == "US_IND_ENRGY")]
    core_bonds = {a: round((1 - e_mid) * x, 6) for a, x in E["ladder"].items() if x}
    out.append({"name": "sector_mom12_top3", "type": "momentum", "rebalancing": {"frequency": "monthly"},
                "params": {"lookback": 12, "skip": 1, "top_k": 3, "absolute": True, "candidates": sect + [core],
                           "core_weights": core_bonds}})
    cls = [core] + bonds[:1] + (["CORP_AAA"] if "CORP_AAA" in E["universe"] else []) + ([g] if g else [])
    out.append({"name": "dual_mom12_top2", "type": "momentum", "rebalancing": {"frequency": "monthly"},
                "params": {"lookback": 12, "top_k": 2, "absolute": True, "candidates": cls}})
    return out


def profile(era, var, derived=None, pid=None, tech_cap="derived", horizon=10):
    E = ERAS[era]
    V = VARIANTS[var]
    groups = []
    risk = {"max_vol": None, "max_drawdown": None, "max_cvar_5": None}
    target = derived["target_real_return"] if derived else 0.0
    if derived:
        eq_classes = ["equity_us", "sector_us", "equity_ca"]
        groups.append({"name": "equity_band", "classes": eq_classes, "min": derived["equity_min"], "max": derived["equity_max"]})
        cap = derived["tech_cap"] if tech_cap == "derived" else tech_cap
        if cap is not None:
            groups.append({"name": "tech_lookthrough", "exposure": "tech", "max": cap})
        risk = {"max_vol": derived["max_vol"], "max_drawdown": derived["max_drawdown"], "max_cvar_5": None}
    p = {
        "id": pid or f"mateo_{era}_{var}",
        "description": f"Mateo (moderate, 8-12y, ESG proxy) - era {era} - variant {var}. Thresholds derived in reports/mateo.md.",
        "currency": E["currency"], "fx_fill": E["fx_fill"], "horizon_years": horizon, "mode": "non_overlapping",
        "step_months": 12, "period": {"start": E["start"], "end": None},
        "universe": E["universe"], "cash_asset": E["cash"],
        "objective": {"type": "min_shortfall", "target_real_return": target, "target_real_wealth": None},
        "constraints": {"default_bounds": [0.0, 1.0], "asset_bounds": {}, "class_max_weight": {},
                        "exclude": {"assets": V["exclude_assets"], "tags": V["exclude_tags"], "classes": ["crypto"]},
                        "groups": groups, "exposure_overrides": {}},
        "risk_limits": risk,
        "flows": {"initial": 10000, "monthly": 0, "indexed_to_inflation": True},
        "rebalancing": {"frequency": "annual", "band": 0.05},
        "costs_bps": 10,
        "fallback_weights": mix(era, var, derived["equity_policy"] if derived else 0.6),
        "strategies": strategies(era, var, derived),
        "selection": {"quantile": 0.10, "max_breach_rate": derived.get("max_breach_rate") if derived else None,
                      "min_past_windows": 3},
        "oracle": {"enabled": bool(derived), "n_starts": 4},
        "seed": 42,
    }
    return p


def write(p, name=None):
    path = PROF / f"{name or p['id']}.yaml"
    head = ("# GENERATED by analysis/mateo/make_profiles.py - do not edit by hand.\n"
            "# Mateo persona (fictional). Thresholds DERIVED from data (reports/mateo.md), proposals to validate by the team.\n"
            "# Uses the synthetic asset US_MKT_XEN: run through analysis/mateo/run_mateo.py (sets ALPHAFORGE_BT_DATA).\n"
            "# SIMULATION ONLY - not financial advice.\n")
    path.write_text(head + yaml.safe_dump(p, sort_keys=False, allow_unicode=True))
    return path


def main(stage):
    derived = json.loads(DERIVED_FILE.read_text()) if stage == "B" else None
    out = []
    for era in ERAS:
        for var in VARIANTS:
            if var == "esgstrict" and era != "cad":
                continue
            pid = f"mateo_{'sens_' if stage == 'A' else ''}{era}_{var}"
            out.append(write(profile(era, var, derived, pid)))
    if stage == "B":
        for era in ERAS:
            for var in VARIANTS:
                if var == "esgstrict" and era != "cad":
                    continue
                # class-level oracle: no sector portfolios (cleaner rule extraction, isolates the core-equity ESG effect)
                q = profile(era, var, derived, f"mateo_{era}_{var}_classes")
                q["constraints"]["exclude"]["assets"] = sorted(set(q["constraints"]["exclude"]["assets"]) |
                                                              {a for a in q["universe"] if a.startswith("US_IND_")})
                q["strategies"] = [s for s in q["strategies"] if s["type"] in ("static", "glidepath", "delayed_glidepath")]
                out.append(write(q))
                if var == "esg" or (var == "base"):
                    for cap in derived["tech_cap_grid"]:
                        out.append(write(profile(era, var, derived, f"mateo_{era}_{var}_tc{int(round(cap*100))}", tech_cap=cap)))
        # canonical profile = CAD era, ESG proxy variant (reference currency of a Canadian investor)
        p = profile("cad", "esg", derived, "mateo")
        out.append(write(p))
    print("\n".join(map(str, out)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "A")
