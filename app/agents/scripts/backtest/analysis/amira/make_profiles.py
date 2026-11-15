"""Generate Amira's era profiles (profiles/amira*.yaml) from ONE template, using the thresholds derived
by derive_thresholds.py (results/amira_sweep_tech/derived_thresholds.json). Nothing is taken from the
persona document except qualitative inputs (growth goal, 15+ y horizon, high tolerance, tech/crypto
appetite, 'keep real diversification', tech human capital).

    uv run --group finance python -I analysis/amira/make_profiles.py
SIMULATION ONLY.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amira_common import NONTECH, RESULTS, SECTORS, make_profile, save_yaml  # noqa: E402

D = json.loads((RESULTS / "amira_sweep_tech" / "derived_thresholds.json").read_text())["result"]["derived"]
TECH_CAP = float(D["tech_cap"])          # 0.30 in the reference build
DD_BUDGET = float(D["dd_budget"])        # 0.40 in the reference build
E_REF = float(D["equity_share_ref"])     # 0.80


def core(E=E_REF, T=TECH_CAP, era="usd", ca_share=0.5, gold=0.0):
    """Reference policy family of the sweep: BusEq = T, rest of equity equal across non-tech sectors
    (CAD era: ca_share of it in CA_EQ), bonds = 1 - E - gold."""
    w = {"US_IND_BUSEQ": T}
    rest = E - T
    if era == "cad":
        if ca_share > 0:
            w["CA_EQ"] = rest * ca_share
        for s in NONTECH:
            w[s] = rest * (1 - ca_share) / len(NONTECH)
        b = 1 - E - gold
        w["CA_GOV_10Y"] = b
    else:
        for s in NONTECH:
            w[s] = rest / len(NONTECH)
        b = 1 - E - gold
        w["UST_5Y"], w["UST_10Y"] = b / 2, b / 2
    if gold:
        w["GOLD"] = gold
    return {k: round(v, 8) for k, v in w.items() if v > 1e-12}


def strategies(era: str, universe: list[str], cash: str, bonds: list[str]):
    cad = era == "cad"
    c = (lambda **k: core(era="cad", **k)) if cad else (lambda **k: core(era="usd", **k))
    S = [
        {"name": "S_core_E80_T30", "type": "static", "params": {"weights": c()}},
        {"name": "S_core_E80_T20", "type": "static", "params": {"weights": c(T=0.2)}},
        {"name": "S_core_E90_T25", "type": "static", "params": {"weights": c(E=0.9, T=0.25)}},
        {"name": "S_mkt80_bonds20", "type": "static",
         "params": {"weights": {"US_MKT": 0.8, **{b: 0.2 / len(bonds) for b in bonds}}}},
        {"name": "S_eqw_sectors80", "type": "sixty_forty",
         "params": {"equity": SECTORS + (["CA_EQ"] if cad else []), "bonds": bonds, "equity_share": 0.8}},
        {"name": "S_1overN", "type": "static",
         "params": {"weights": {a: 1 / (len(universe) - 1) for a in universe if a != cash}}},
        {"name": "G_E95_to_E65", "type": "glidepath",
         "params": {"start_weights": c(E=0.95), "end_weights": c(E=0.65)}},
        {"name": "RP_invvol_36m", "type": "risk_parity", "params": {"lookback": 36, "method": "inverse_vol",
                                                                    "exclude": [cash]}},
        {"name": "RP_erc_60m", "type": "risk_parity", "params": {"lookback": 60, "method": "erc", "exclude": [cash]}},
        {"name": "MinVar_60m", "type": "min_variance", "params": {"lookback": 60}},
        {"name": "MaxSharpe_60m", "type": "max_sharpe", "params": {"lookback": 60, "mu_shrink": 0.5}},
        {"name": "MV_ra2_60m", "type": "mean_variance", "params": {"lookback": 60, "mu_shrink": 0.5, "risk_aversion": 2}},
        {"name": "MV_ra4_120m", "type": "mean_variance", "params": {"lookback": 120, "mu_shrink": 0.7,
                                                                    "risk_aversion": 4}},
        {"name": "Trend10_core", "type": "trend_filter",
         "params": {"ma_months": 10, "base_weights": c(), "always_hold": bonds}, "rebalancing": {"frequency": "monthly"}},
        {"name": "Mom_sectors_top3", "type": "momentum",
         "params": {"lookback": 12, "skip": 1, "top_k": 3, "absolute": True, "candidates": SECTORS,
                    "core_weights": {b: 0.2 / len(bonds) for b in bonds}}, "rebalancing": {"frequency": "monthly"}},
        {"name": "Mom_all_top4", "type": "momentum",
         "params": {"lookback": 12, "skip": 1, "top_k": 4, "absolute": True,
                    "candidates": [a for a in universe if a != cash]}, "rebalancing": {"frequency": "monthly"}},
    ]
    if "GOLD" in universe:
        for g in (0.05, 0.10, 0.15, 0.20):
            S.append({"name": f"S_core_E80_T30_gold{int(g*100):02d}", "type": "static",
                      "params": {"weights": c(gold=g)}})
    if cad:
        for ca in (0.0, 1.0):
            S.append({"name": f"S_core_E80_T30_ca{int(ca*100):03d}", "type": "static",
                      "params": {"weights": c(ca_share=ca)}})
    return S


def profile(era: str, pid: str, desc: str, currency: str, start: str, universe, cash, bonds):
    return {
        "id": pid, "description": desc, "currency": currency, "fx_fill": "none",
        "horizon_years": 15, "mode": "non_overlapping", "step_months": 12,
        "period": {"start": start, "end": None},
        "universe": universe, "cash_asset": cash,
        "objective": {"type": "max_real_return", "target_real_return": 0.0, "target_real_wealth": None},
        "constraints": {
            "default_bounds": [0.0, 1.0],
            "asset_bounds": {},
            "class_max_weight": {"sector_us": TECH_CAP},   # no single KF industry above the derived tech cap (hypothesis)
            "exclude": {"assets": [], "tags": [], "classes": []},
            "groups": [{"name": "tech_lookthrough", "exposure": "tech", "max": TECH_CAP}],
            "exposure_overrides": {},
        },
        "risk_limits": {"max_vol": None, "max_drawdown": DD_BUDGET, "max_cvar_5": None},
        "flows": {"initial": 1.0, "monthly": 0.0, "indexed_to_inflation": True},
        "rebalancing": {"frequency": "annual", "band": 0.05},
        "costs_bps": 10,
        "fallback_weights": core(era="cad" if era == "cad" else "usd"),
        "strategies": strategies(era, universe, cash, bonds),
        "selection": {"quantile": 0.10, "max_breach_rate": None, "min_past_windows": 3},
        "oracle": {"enabled": True, "n_starts": 6},
        "seed": 42,
    }


def main():
    usd_long = ["US_MKT"] + SECTORS + ["UST_TBILL", "UST_2Y", "UST_5Y", "UST_10Y", "UST_20Y", "CORP_AAA", "CORP_BAA"]
    profs = {
        "amira_long_usd": profile("usd", "amira_long_usd",
                                  "Amira (fictional) - long USD era 1926+, US proxies, no gold (pre-1975 gold non investable). "
                                  f"Derived: tech look-through <= {TECH_CAP}, KF industry <= {TECH_CAP}, DD budget {DD_BUDGET}.",
                                  "USD", "1926-07", usd_long, "UST_TBILL", ["UST_5Y", "UST_10Y"]),
        "amira_usd_1975": profile("usd", "amira_usd_1975",
                                  "Amira (fictional) - USD era 1975+ with gold (investable after the US ban was lifted).",
                                  "USD", "1975-01", usd_long + ["GOLD"], "UST_TBILL", ["UST_5Y", "UST_10Y"]),
        "amira": profile("cad", "amira",
                             "Amira (fictional) - REFERENCE profile: CAD investor 1977+ (CA_EQ start), unhedged US assets, Canadian bonds/cash, gold.",
                             "CAD", "1977-01",
                             ["CA_EQ", "US_MKT"] + SECTORS + ["UST_5Y", "UST_10Y", "CA_GOV_10Y", "CA_TBILL", "GOLD"],
                             "CA_TBILL", ["CA_GOV_10Y"]),
    }
    if "--etf" in sys.argv:
        profs = {"amira_etf": etf_profile("cad"), "amira_etf_long_usd": etf_profile("usd")}
    for name, raw in profs.items():
        make_profile(raw)  # validate
        print(save_yaml(raw, name))


def etf_profile(era: str) -> dict:
    """IMPLEMENTABLE universe: only proxies that map to a starter ETF (no sector ETF exists in the starter
    universe, so KF-industry strategies cannot be translated without single-stock concentration).
    US_MKT->SPY, CA_EQ->XIU.TO, US_IND_BUSEQ->tech basket (QQQ partial), UST_10Y->AGG, UST_20Y->TLT,
    CA_GOV_10Y->XBB.TO, GOLD->GLD, cash->ZST.TO."""
    cad = era == "cad"
    if cad:
        uni = ["CA_EQ", "US_MKT", "US_IND_BUSEQ", "UST_10Y", "UST_20Y", "CA_GOV_10Y", "GOLD", "CA_TBILL"]
        cash, bond, start, cur = "CA_TBILL", "CA_GOV_10Y", "1977-01", "CAD"
    else:
        uni = ["US_MKT", "US_IND_BUSEQ", "UST_5Y", "UST_10Y", "UST_20Y", "UST_TBILL"]
        cash, bond, start, cur = "UST_TBILL", "UST_10Y", "1926-07", "USD"
    S = []
    for E in (0.7, 0.8, 0.9, 1.0):
        for us in ((0.5, 0.7) if cad else (1.0,)):
            for g in ((0.0, 0.1) if cad else (0.0,)):
                for t in (0.0, 0.1):
                    b = 1 - E - g
                    if b < -1e-9:
                        continue
                    eq = E - t
                    w = {"US_MKT": eq * us, "US_IND_BUSEQ": t}
                    if cad:
                        w["CA_EQ"] = eq * (1 - us)
                        w["GOLD"] = g
                    w[bond] = max(b, 0.0)
                    w = {k: round(v, 8) for k, v in w.items() if v > 1e-9}
                    S.append({"name": f"E{int(E*100)}_us{int(us*100)}_g{int(g*100)}_t{int(t*100)}", "type": "static",
                              "params": {"weights": w}})
    base = next(s["params"]["weights"] for s in S if s["name"] == ("E80_us50_g0_t0" if cad else "E80_us100_g0_t0"))
    risky = [a for a in uni if a != cash]
    S += [
        {"name": "Mom_etf_top2", "type": "momentum", "params": {"lookback": 12, "skip": 1, "top_k": 2, "absolute": True,
                                                                "candidates": risky}, "rebalancing": {"frequency": "monthly"}},
        {"name": "Mom_etf_top3", "type": "momentum", "params": {"lookback": 12, "skip": 1, "top_k": 3, "absolute": True,
                                                                "candidates": risky}, "rebalancing": {"frequency": "monthly"}},
        {"name": "Mom_etf_top3_core50", "type": "momentum",
         "params": {"lookback": 12, "skip": 1, "top_k": 3, "absolute": True, "candidates": risky,
                    "core_weights": {k: v * 0.5 for k, v in base.items()}}, "rebalancing": {"frequency": "monthly"}},
        {"name": "Trend10_E80", "type": "trend_filter", "params": {"ma_months": 10, "base_weights": base,
                                                                   "always_hold": [bond]},
         "rebalancing": {"frequency": "monthly"}},
        {"name": "RP_invvol_36m", "type": "risk_parity", "params": {"lookback": 36, "exclude": [cash]}},
        {"name": "MinVar_60m", "type": "min_variance", "params": {"lookback": 60}},
        {"name": "MaxSharpe_60m", "type": "max_sharpe", "params": {"lookback": 60, "mu_shrink": 0.5}},
        {"name": "MV_ra2_60m", "type": "mean_variance", "params": {"lookback": 60, "mu_shrink": 0.5, "risk_aversion": 2}},
        {"name": "G_E95_to_E65", "type": "glidepath",
         "params": {"start_weights": {k: (v * 0.95 / 0.8 if k not in (bond,) else 0.05) for k, v in base.items()},
                    "end_weights": {k: (v * 0.65 / 0.8 if k not in (bond,) else 0.35) for k, v in base.items()}}},
    ]
    pid = "amira_etf" if cad else "amira_etf_long_usd"
    p = profile("cad" if cad else "usd", pid, f"Amira (fictional) - ETF-implementable universe, {cur} {start}+.",
                cur, start, uni, cash, [bond])
    p["strategies"] = S
    p["fallback_weights"] = base
    return p


if __name__ == "__main__":
    main()
