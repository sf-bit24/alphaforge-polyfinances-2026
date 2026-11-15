"""Persona 14 - check on the REAL starter tickers, window 2021-12..2026-09 (58 monthly returns, base 2021-11-30), CAD,
with engine.backtest.run_window (history from 2018-11 for the estimation strategies). SIMULATION ONLY.
Proxy -> ticker translation (assets.csv universe_tickers / proxy_for_ticker):
  CA_EQ -> XIU.TO ; US_MKT / US_MKT_XEN -> SPY (contains ~3 % energy, engine look-through) or ESGV (variant; its fossil
  exclusion methodology is NOT in our data) ; CA_GOV_10Y -> XBB.TO ; UST_5Y -> AGG ; GOLD -> GLD ; CA_TBILL -> ZST.TO ;
  US_IND_HLTH -> JNJ ; US_IND_NODUR -> PG ; US_IND_UTILS -> FTS.TO ; US_IND_ENRGY -> CNQ.TO / ENB.TO / XOM.
Energy look-through of each mix: CNQ/ENB/XOM = 1 ; SPY/ESGV = engine US_MKT share at each date ; XIU.TO = return-based
estimate (energy_style_ca_eq.csv: 2019-2026 block and full sample, NOT holdings).
Writes profiles/p14_real_tickers.yaml (documentation) and results/p14_analysis/real_check.json / .csv
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as K  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from alphaforge.finance.backtest.backtest import ConstraintProvider, run_window  # noqa: E402
from alphaforge.finance.backtest.data import data_version, exposure_vector, load_inflation, load_returns  # noqa: E402
from alphaforge.finance.backtest.profile import DEFAULTS, _merge, validate  # noqa: E402
from alphaforge.finance.backtest.run import engine_hash  # noqa: E402
from alphaforge.finance.backtest.strategies import build_strategy  # noqa: E402
from alphaforge.finance.backtest.windows import Window  # noqa: E402

START, END = "2021-12", "2026-09"
UNI = ["XIU.TO", "SPY", "ESGV", "XBB.TO", "AGG", "GLD", "ZST.TO", "CNQ.TO", "ENB.TO", "XOM", "JNJ", "PG", "FTS.TO"]
STY = pd.read_csv(K.OUT / "energy_style_ca_eq.csv")
XIU_RECENT = float(STY[(STY.target == "XIU.TO") & STY.block.str.startswith("2019")].energy_loading.iloc[0])
XIU_FULL = float(STY[(STY.target == "XIU.TO") & STY.block.str.startswith("full")].energy_loading.iloc[0])
BNC = {"prudent": (0.80, 0.06, 0.14), "conservateur": (0.70, 0.09, 0.21), "pondere": (0.55, 0.135, 0.315),
       "equilibre": (0.40, 0.18, 0.42), "croissance": (0.20, 0.24, 0.56), "actions": (0.0, 0.30, 0.70)}


def r6(d):
    return {k: round(v, 6) for k, v in d.items() if v}


def core(eq, us="SPY"):
    return {"XIU.TO": 0.3 * eq, us: 0.7 * eq, "XBB.TO": 1 - eq}


def with_extra(w, extra):
    s = 1 - sum(extra.values())
    w = {k: v * s for k, v in w.items()}
    w.update(extra)
    return r6(w)


def strategies():
    S = [{"name": "coussin_zst100", "type": "static", "params": {"weights": {"ZST.TO": 1.0}}}]
    for n, (fi, ca, gl) in BNC.items():
        S.append({"name": f"bnc_{n}", "type": "static", "params": {"weights": r6({"XBB.TO": fi, "XIU.TO": ca, "SPY": gl})}})
        if n in ("pondere", "equilibre", "croissance"):
            S.append({"name": f"bnc_{n}_esgv", "type": "static", "params": {"weights": r6({"XBB.TO": fi, "XIU.TO": ca, "ESGV": gl})}})
    for eq in (0.4, 0.5, 0.6, 0.7):
        S.append({"name": f"core_eq{int(eq*100)}", "type": "static", "params": {"weights": r6(core(eq))}})
        S.append({"name": f"core_eq{int(eq*100)}_esgv", "type": "static", "params": {"weights": r6(core(eq, "ESGV"))}})
    S.append({"name": "core_eq60_gold10", "type": "static", "params": {"weights": with_extra(core(0.6), {"GLD": 0.10})}})
    S.append({"name": "core_eq60_defensive", "type": "static",
              "params": {"weights": with_extra(core(0.6), {"JNJ": 0.08, "PG": 0.08, "FTS.TO": 0.04})}})
    for k in (0.45, 0.20, 0.05, 0.025, 0.0):
        S.append({"name": f"etat_cnq{k*100:g}", "type": "static", "params": {"weights": with_extra(core(0.6), {"CNQ.TO": k} if k else {})}})
    S.append({"name": "etat_cnq45_plus_demande_enb10_xom10", "type": "static",
              "params": {"weights": with_extra(core(0.6), {"CNQ.TO": 0.45, "ENB.TO": 0.10, "XOM": 0.10})}})
    S.append({"name": "request_eq60_energy20_enb_xom", "type": "static", "params": {"weights": with_extra(core(0.6), {"ENB.TO": 0.10, "XOM": 0.10})}})
    S.append({"name": "risk_parity_iv36", "type": "risk_parity",
              "params": {"lookback": 36, "method": "inverse_vol", "exclude": ["ZST.TO", "ESGV", "CNQ.TO", "ENB.TO", "XOM", "JNJ", "PG", "FTS.TO", "AGG"]}})
    S.append({"name": "dual_mom12_top2", "type": "momentum", "rebalancing": {"frequency": "monthly"},
              "params": {"lookback": 12, "top_k": 2, "absolute": True, "candidates": ["XIU.TO", "SPY", "XBB.TO", "GLD"]}})
    S.append({"name": "trend10_eq60", "type": "trend_filter", "rebalancing": {"frequency": "monthly"},
              "params": {"ma_months": 10, "base_weights": r6(core(0.6)), "always_hold": ["XBB.TO"]}})
    return S


def profile():
    return {"id": "p14_real_tickers", "currency": "CAD", "fx_fill": "none", "horizon_years": 58 / 12,
            "period": {"start": "2018-11", "end": END}, "universe": UNI, "cash_asset": "ZST.TO",
            "objective": {"type": "min_shortfall", "target_real_return": 0.0},
            "risk_limits": {"max_drawdown": 0.20}, "rebalancing": {"frequency": "annual", "band": 0.05}, "costs_bps": 10,
            "flows": {"initial": 1.0, "monthly": 0, "indexed_to_inflation": True},
            "fallback_weights": r6(core(0.5)), "strategies": strategies(), "oracle": {"enabled": False}, "seed": 42}


def main():
    prof = profile()
    (K.BT / "profiles" / "p14_real_tickers.yaml").write_text(
        "# GENERATED by analysis/p14/real_check.py - persona 14 (Tyler) real-ticker check. Run through run_window, not the CLI.\n"
        "# risk limit = etudes pocket max DD (0.20, derived). SIMULATION ONLY - not financial advice.\n"
        + yaml.safe_dump(prof, sort_keys=False, width=200))
    p = validate(_merge(DEFAULTS, prof))
    infl = load_inflation("CAD")
    R = load_returns(p["universe"], p["period"]["start"], END, "CAD", "none")
    w = Window(R.loc[START:].index[0], R.index[-1], len(R.loc[START:]))
    prov = ConstraintProvider(p["universe"], p["constraints"])
    fb = prov.at(R.index[-1]).project(np.array([float(p["fallback_weights"].get(a, 0)) for a in p["universe"]]))
    cnq = R.loc[w.start:w.end, "CNQ.TO"]
    stress = cnq <= cnq.quantile(0.10)
    recs = []
    for s in p["strategies"]:
        res = run_window(R, infl, w, build_strategy(s), p, prov, None, fb)
        m, W, r = res["metrics"], res["weights"], res["returns"]
        en = []
        for d in W.index:
            v = exposure_vector(list(R.columns), "energy", date=d)
            v[list(R.columns).index("XIU.TO")] = XIU_RECENT
            v[list(R.columns).index("ESGV")] = 0.0  # ESGV methodology excludes fossil fuels (to verify; not in our data)
            en.append(v @ W.loc[d].values)
        xiu = W["XIU.TO"].mean()
        y22 = r[r.index.year == 2022]
        recs.append({"strategy": s["name"], "window": w.label,
                     **{k: m[k] for k in ("ann_return", "ann_real_return", "volatility", "max_drawdown", "recovery_months", "worst_12m")},
                     "ret_2022": float((1 + y22).prod() - 1), "corr_cnq": float(r.corr(cnq)),
                     "mean_in_cnq_worst_decile": float(r[stress].mean()),
                     "energy_lookthrough_xiu_recent": float(np.mean(en)),
                     "energy_lookthrough_xiu_full": float(np.mean(en) + xiu * (XIU_FULL - XIU_RECENT)),
                     "breaches": m["risk_breaches"], "fallback_months": m["fallback_months"],
                     "avg_weights": {k: round(float(v), 4) for k, v in W.mean().items() if v > 0.005}})
    df = pd.DataFrame(recs)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace = {"run_id": f"p14_real_check_{stamp}", "disclaimer": "Simulation historique uniquement, pas un conseil financier.",
             "engine_sha256": engine_hash(), "data_version": data_version(), "patch_note": K.PATCH_NOTE,
             "profile": "profiles/p14_real_tickers.yaml", "data_info": R.attrs["info"],
             "xiu_energy_loading": {"recent_2019_2026": XIU_RECENT, "full": XIU_FULL},
             "cnq_worst_decile_months": [str(d.date()) for d in cnq[stress].index],
             "results": df.to_dict(orient="records")}
    (K.OUT / "real_check.json").write_text(json.dumps(trace, indent=1, default=str))
    df.drop(columns=["avg_weights"]).to_csv(K.OUT / "real_check.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 20, "display.max_rows", 100)
    print(df.drop(columns=["breaches", "avg_weights", "window"]).to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    for r in recs:
        if r["strategy"] in ("risk_parity_iv36", "dual_mom12_top2", "trend10_eq60"):
            print(r["strategy"], r["avg_weights"], r["fallback_months"])


if __name__ == "__main__":
    main()
