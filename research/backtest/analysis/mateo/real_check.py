"""Out-of-sample style check on the REAL starter tickers, 2021-11..2026-09 (CAD), with engine.backtest.run_window.
Proxy -> ticker translation (assets.csv universe_tickers / proxy_for_ticker):
  US_MKT_XEN -> ESGV (ESG-screened US; its exclusion list is NOT in our data) ; US_MKT -> SPY ; CA_EQ -> XIU.TO
  CA_GOV_10Y -> XBB.TO ; UST_5Y -> AGG ; GOLD -> GLD ; CA_TBILL -> ZST.TO
Also: equal-weight basket of the 20 single stocks of the starter vs the same basket without XOM, CNQ.TO, ENB.TO.
Writes profiles/mateo_real_tickers.yaml (documentation of the run) and results/mateo_analysis/real_check.json.
SIMULATION ONLY."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from engine.backtest import ConstraintProvider, run_window  # noqa: E402
from engine.data import data_version, load_inflation, load_returns, exposure_vector  # noqa: E402
from engine.profile import DEFAULTS, _merge, validate  # noqa: E402
from engine.run import engine_hash  # noqa: E402
from engine.strategies import build_strategy  # noqa: E402
from engine.windows import Window  # noqa: E402

START, END = "2021-11", "2026-09"
STOCKS = ["RY.TO", "TD.TO", "MFC.TO", "ENB.TO", "CNQ.TO", "CNR.TO", "FTS.TO", "ATD.TO", "SHOP.TO", "CSU.TO",
          "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "JNJ", "PG", "XOM"]
FOSSIL = ["XOM", "CNQ.TO", "ENB.TO"]
ETFS = ["ESGV", "SPY", "XIU.TO", "XBB.TO", "AGG", "GLD", "ZST.TO"]


def mixes(e, variant):
    bonds = {"XBB.TO": 0.5, "AGG": 0.5}
    if variant == "esg":
        eq = {"ESGV": e / 2, "XIU.TO": e / 2}
    elif variant == "esgstrict":
        eq = {"ESGV": e}
    else:
        eq = {"SPY": e / 2, "XIU.TO": e / 2}
    w = dict(eq)
    for a, x in bonds.items():
        w[a] = (1 - e) * x
    return {k: round(v, 6) for k, v in w.items()}


def variant_profile(var):
    eq = {"base": ["SPY", "XIU.TO"], "esg": ["ESGV", "XIU.TO"], "esgstrict": ["ESGV"]}[var]
    excl = [a for a in ("SPY", "ESGV", "XIU.TO") if a not in eq]
    strategies = []
    for e in (0.4, 0.6, 0.7):
        strategies.append({"name": f"{var}_static_eq{int(e*100)}", "type": "static", "params": {"weights": mixes(e, var)}})
    w = mixes(0.6, var)
    wg = {k: (v if k in eq else v * 0.3 / 0.4) for k, v in w.items()}; wg["GLD"] = 0.10
    strategies.append({"name": f"{var}_static_eq60_gold", "type": "static", "params": {"weights": wg}})
    strategies.append({"name": f"{var}_risk_parity_iv36", "type": "risk_parity",
                       "params": {"lookback": 36, "method": "inverse_vol", "exclude": ["ZST.TO"] + excl}})
    strategies.append({"name": f"{var}_dual_mom12_top2", "type": "momentum", "rebalancing": {"frequency": "monthly"},
                       "params": {"lookback": 12, "top_k": 2, "absolute": True, "candidates": [eq[0], "AGG", "GLD"] + (["XBB.TO"])}})
    strategies.append({"name": f"{var}_trend10_eq60", "type": "trend_filter", "rebalancing": {"frequency": "monthly"},
                       "params": {"ma_months": 10, "base_weights": mixes(0.6, var), "always_hold": ["XBB.TO", "AGG"]}})
    strategies.append({"name": f"{var}_glide_compressed_70_40", "type": "delayed_glidepath",
                       "rebalancing": {"frequency": "quarterly"},
                       "params": {"start_weights": mixes(0.7, var), "end_weights": mixes(0.4, var), "derisk_start": 0.5}})
    return {"id": f"mateo_real_tickers_{var}", "currency": "CAD", "fx_fill": "none", "horizon_years": 5,
            "period": {"start": "2018-11", "end": END}, "universe": ETFS, "cash_asset": "ZST.TO",
            "objective": {"type": "min_shortfall", "target_real_return": 0.0},
            "constraints": {"exclude": {"assets": excl, "classes": ["crypto"]},
                            "groups": [{"name": "equity_band", "classes": ["etf_equity"], "min": 0.4, "max": 0.8}]},
            "risk_limits": {"max_vol": 0.10, "max_drawdown": 0.20},
            "rebalancing": {"frequency": "annual", "band": 0.05}, "costs_bps": 10,
            "flows": {"initial": 10000, "monthly": 0, "indexed_to_inflation": True},
            "fallback_weights": mixes(0.6, var), "strategies": strategies, "oracle": {"enabled": False}, "seed": 42}


def stocks_profile():
    return {"id": "mateo_real_tickers_stocks", "currency": "CAD", "fx_fill": "none", "horizon_years": 5,
            "period": {"start": "2018-11", "end": END}, "universe": STOCKS + ["ZST.TO"], "cash_asset": "ZST.TO",
            "objective": {"type": "min_shortfall", "target_real_return": 0.0},
            "risk_limits": {"max_vol": 0.10, "max_drawdown": 0.20}, "rebalancing": {"frequency": "annual", "band": 0.05},
            "costs_bps": 10, "flows": {"initial": 10000, "monthly": 0, "indexed_to_inflation": True},
            "strategies": [{"name": "stocks_ew20", "type": "static", "params": {"weights": {s: 1 / 20 for s in STOCKS}}},
                           {"name": "stocks_ew17_ex_fossil", "type": "static",
                            "params": {"weights": {s: 1 / 17 for s in STOCKS if s not in FOSSIL}}}],
            "oracle": {"enabled": False}, "seed": 42}


def main():
    profs = [variant_profile(v) for v in ("base", "esg", "esgstrict")] + [stocks_profile()]
    (common.BT / "profiles" / "mateo_real_tickers.yaml").write_text(
        "# GENERATED by analysis/mateo/real_check.py - real-ticker check of the Mateo strategies (4 sub-profiles).\n"
        "# Equity band [0.4, 0.8] and risk limits = derived Mateo thresholds. SIMULATION ONLY.\n"
        + yaml.safe_dump({"profiles": profs}, sort_keys=False))
    infl = load_inflation("CAD")
    recs, infos = [], {}
    for prof in profs:
        p = common.inject_glide_params(validate(_merge(DEFAULTS, prof)))
        R = load_returns(p["universe"], p["period"]["start"], END, "CAD", "none")
        infos[p["id"]] = R.attrs["info"]
        w = Window(R.loc[START:].index[0], R.index[-1], len(R.loc[START:]))
        prov = ConstraintProvider(p["universe"], p["constraints"])
        fb = prov.at(R.index[-1]).project(np.array([float(p["fallback_weights"].get(a, 0)) for a in p["universe"]])) \
            if p.get("fallback_weights") else None
        for s in p["strategies"]:
            res = run_window(R, infl, w, build_strategy(s), p, prov, None, fb)
            m = res["metrics"]
            W = res["weights"]
            tech = np.array([exposure_vector(list(R.columns), "tech", date=d) @ W.loc[d].values for d in W.index]).mean()
            recs.append({"profile": p["id"], "strategy": s["name"], "window": w.label,
                         **{k: m[k] for k in ("ann_return", "ann_real_return", "volatility", "max_drawdown",
                                              "recovery_months", "cvar_5", "worst_12m", "final_real_wealth")},
                         "breaches": m["risk_breaches"], "avg_tech_lookthrough": float(tech),
                         "fallback_months": m["fallback_months"],
                         "avg_weights": {k: round(float(v), 4) for k, v in W.mean().items() if v > 0.005}})
    df = pd.DataFrame(recs)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace = {"run_id": f"real_check_{stamp}", "disclaimer": "Simulation historique uniquement, pas un conseil.",
             "engine_sha256": engine_hash(), "data_version": data_version(), "patch_note": common.PATCH_NOTE,
             "profile": "profiles/mateo_real_tickers.yaml", "data_info": infos,
             "note_tech": "tech look-through: SPY/ESGV approximated by US_MKT KF BusEq share (engine rule); XIU.TO/AGG/XBB.TO = 0 (no holdings data)",
             "results": df.to_dict(orient="records")}
    out = common.BT / "results" / "mateo_analysis" / "real_check.json"
    out.write_text(json.dumps(trace, indent=1, default=str))
    pd.set_option("display.width", 250, "display.max_columns", 20)
    print(out)
    print(df.drop(columns=["breaches", "avg_weights", "profile"]).to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    for r in recs:
        if "risk_parity" in r["strategy"] or "mom" in r["strategy"]:
            print(r["strategy"], r["avg_weights"], r["breaches"])


if __name__ == "__main__":
    main()
