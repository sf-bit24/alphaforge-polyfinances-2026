"""Out-of-sample check on the REAL starter period with REAL tickers (CAD investor), and the same policies on
proxies over the same months (translation error). Window = 2021-12 .. 2026-09 (first full month of the
starter data .. last month common to the proxies), history before the window is used by trend/momentum.

Mapping proxy -> ticker (assets.csv universe_tickers):
  US_MKT->SPY, CA_EQ->XIU.TO, CA_GOV_10Y->XBB.TO, GOLD->GLD, CA_TBILL->ZST.TO, UST_10Y->AGG, UST_20Y->TLT,
  US_IND_BUSEQ -> equal basket AAPL MSFT NVDA GOOGL CSU.TO SHOP.TO (each <= single-name cap).
Constraints in the ticker profile: tech look-through <= TECH_CAP (SPY via US_MKT look-through; XIU.TO = 0,
no holdings data -> under-estimated), each single stock <= single-name cap, crypto <= crypto cap.

    uv run --group finance python -I analysis/amira/verify_tickers.py
Writes results/amira_tickers/verify_<stamp>.json. SIMULATION ONLY.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amira_common import RESULTS, make_profile, write_json  # noqa: E402
from alphaforge.finance.backtest.backtest import ConstraintProvider, run_window  # noqa: E402
from alphaforge.finance.backtest.data import load_inflation, load_returns  # noqa: E402
from alphaforge.finance.backtest.strategies import build_strategy  # noqa: E402
from alphaforge.finance.backtest.windows import Window  # noqa: E402

D = json.loads((RESULTS / "amira_sweep_tech" / "derived_thresholds.json").read_text())["result"]["derived"]
SN = json.loads((RESULTS / "amira_sat_single" / "derived_single_name_cap.json").read_text())["result"]
CR = json.loads((RESULTS / "amira_sat_crypto" / "derived_crypto_cap.json").read_text())["result"]
TECH_CAP = D["tech_cap"]
NAME_CAP = SN["variants"]["amira_sat_single"]["main"]["cap"]
CP = json.loads((RESULTS / "amira_sat_crypto" / "crypto_proposal.json").read_text())["result"]
CRYPTO_CAP_BANDS = CP["baskets"]["BTC"]["proposal_monthly_or_bands"]
CRYPTO_CAP_ANNUAL = CP["baskets"]["BTC"]["proposal_annual"]

TECH = ["AAPL", "MSFT", "NVDA", "GOOGL", "CSU.TO", "SHOP.TO"]
MAP = {"US_MKT": {"SPY": 1}, "CA_EQ": {"XIU.TO": 1}, "CA_GOV_10Y": {"XBB.TO": 1}, "GOLD": {"GLD": 1},
       "CA_TBILL": {"ZST.TO": 1}, "UST_10Y": {"AGG": 1}, "UST_20Y": {"TLT": 1},
       "US_IND_BUSEQ": {t: 1 / len(TECH) for t in TECH}}
START, END = "2021-12", "2026-09"


def tr(w: dict) -> dict:
    out = {}
    for a, x in w.items():
        for t, s in MAP.get(a, {a: 1}).items():
            out[t] = out.get(t, 0) + x * s
    return {k: round(v, 8) for k, v in out.items() if v > 0}


def policies():
    """Proxy policies selected by the robust analysis (see reports/amira.md) and their ticker translation."""
    static = {"US_MKT": 0.4, "CA_EQ": 0.4, "GOLD": 0.1, "CA_GOV_10Y": 0.1}                    # E80_us50_g10_t0
    base_tr = {"US_MKT": 0.4, "CA_EQ": 0.4, "CA_GOV_10Y": 0.2}                                 # E80_us50_g0_t0
    proxy = [
        {"name": "E80_us50_g10_t0", "type": "static", "params": {"weights": static}},
        {"name": "E70_us50_g10_t0", "type": "static",
         "params": {"weights": {"US_MKT": 0.35, "CA_EQ": 0.35, "GOLD": 0.1, "CA_GOV_10Y": 0.2}}},
        {"name": "Trend10_E80", "type": "trend_filter", "params": {"ma_months": 10, "base_weights": base_tr,
                                                                   "always_hold": ["CA_GOV_10Y"]},
         "rebalancing": {"frequency": "monthly"}},
        {"name": "Mom_etf_top3", "type": "momentum",
         "params": {"lookback": 12, "skip": 1, "top_k": 3, "absolute": True,
                    "candidates": ["CA_EQ", "US_MKT", "UST_10Y", "UST_20Y", "CA_GOV_10Y", "GOLD"]},
         "rebalancing": {"frequency": "monthly"}},
        {"name": "Mom_etf_top3_core50", "type": "momentum",
         "params": {"lookback": 12, "skip": 1, "top_k": 3, "absolute": True,
                    "candidates": ["CA_EQ", "US_MKT", "UST_10Y", "UST_20Y", "CA_GOV_10Y", "GOLD"],
                    "core_weights": {k: v * 0.5 for k, v in base_tr.items()}}, "rebalancing": {"frequency": "monthly"}},
    ]
    proxy_only = [{"name": "Mom_etf_top3_with_BUSEQ", "type": "momentum",
                   "params": {"lookback": 12, "skip": 1, "top_k": 3, "absolute": True,
                              "candidates": ["CA_EQ", "US_MKT", "US_IND_BUSEQ", "UST_10Y", "UST_20Y", "CA_GOV_10Y",
                                             "GOLD"]}, "rebalancing": {"frequency": "monthly"}}]
    tick = []
    for s in proxy:
        s2 = json.loads(json.dumps(s))
        p = s2["params"]
        for k in ("weights", "base_weights", "core_weights"):
            if k in p:
                p[k] = tr(p[k])
        if "always_hold" in p:
            p["always_hold"] = [t for a in p["always_hold"] for t in MAP[a]]
        if "candidates" in p:
            p["candidates"] = [t for a in p["candidates"] for t in MAP[a]]
        tick.append(s2)
    # satellites at the derived caps (taken from the bond sleeve -> equity share unchanged)
    tick.append({"name": "E80_us50_g10_t0+tech_basket", "type": "static",
                 "params": {"weights": tr({"US_MKT": 0.37, "CA_EQ": 0.37, "GOLD": 0.1, "CA_GOV_10Y": 0.1,
                                           "US_IND_BUSEQ": 0.06})}})
    tick.append({"name": "E80_us50_g10_t0+BTC_bands", "type": "static",
                 "params": {"weights": {**{k: v * (1 - CRYPTO_CAP_BANDS) for k, v in tr(static).items()},
                                        "BTC-USD": CRYPTO_CAP_BANDS}},
                 "rebalancing": {"frequency": "bands", "band": round(CRYPTO_CAP_BANDS / 2, 4)}})
    tick.append({"name": "Mom_etf_top3+BTC_bands", "type": "momentum",
                 "params": {"lookback": 12, "skip": 1, "top_k": 3, "absolute": True,
                            "candidates": ["XIU.TO", "SPY", "AGG", "TLT", "XBB.TO", "GLD"],
                            "core_weights": {"BTC-USD": CRYPTO_CAP_BANDS}}, "rebalancing": {"frequency": "monthly"}})
    return proxy + proxy_only, tick


def refs():
    """Unconstrained references (FICTION: what an 'all-in tech/crypto' request would have done)."""
    return [{"name": "REF_SPY_100", "type": "static", "params": {"weights": {"SPY": 1.0}}},
            {"name": "REF_QQQ_100", "type": "static", "params": {"weights": {"QQQ": 1.0}}},
            {"name": "REF_tech_crypto_request", "type": "static",
             "params": {"weights": {"QQQ": 0.4, "NVDA": 0.15, "TSLA": 0.1, "SHOP.TO": 0.1, "BTC-USD": 0.15,
                                    "ETH-USD": 0.1}}},
            {"name": "REF_XIU_100", "type": "static", "params": {"weights": {"XIU.TO": 1.0}}}]


def run_set(strats, constraints, cash, label):
    assets = sorted({a for s in strats for k in ("weights", "base_weights", "core_weights")
                     for a in (s["params"].get(k) or {})} | {a for s in strats for a in s["params"].get("candidates", [])}
                    | {cash})
    raw = {"id": f"amira_verify_{label}", "currency": "CAD", "universe": assets, "cash_asset": cash,
           "objective": {"type": "max_real_return", "target_real_return": 0.0}, "constraints": constraints,
           "risk_limits": {"max_drawdown": D["dd_budget"]}, "rebalancing": {"frequency": "annual"}, "costs_bps": 10,
           "strategies": strats, "oracle": {"enabled": False}}
    p = make_profile(raw)
    R = load_returns(assets, start="2019-01", end=END, currency="CAD")
    infl = load_inflation("CAD")
    s0 = pd.Timestamp(START).to_period("M").to_timestamp(how="end").normalize()
    months = R.loc[s0:].index
    w = Window(months[0], months[-1], len(months))
    prov = ConstraintProvider(assets, p["constraints"])
    out = []
    for spec in p["strategies"]:
        st = build_strategy(spec)
        res = run_window(R, infl, w, st, p, prov, None, None)
        m = {k: v for k, v in res["metrics"].items()}
        out.append({"strategy": spec["name"], "set": label, "window": w.label, **m,
                    "avg_weights": {a: round(float(x), 4) for a, x in res["weights"].mean().items() if x > 1e-4},
                    "final_weights": {a: round(float(x), 4) for a, x in res["weights"].iloc[-1].items() if x > 1e-4},
                    "spec": spec})
    return out, R.attrs["info"]


def main():
    proxy, tick = policies()
    cons_t = {"class_max_weight": {"equity_single": NAME_CAP, "crypto": CRYPTO_CAP_BANDS},
              "groups": [{"name": "tech_lookthrough", "exposure": "tech", "max": TECH_CAP}]}
    cons_p = {"class_max_weight": {"sector_us": TECH_CAP},
              "groups": [{"name": "tech_lookthrough", "exposure": "tech", "max": TECH_CAP}]}
    rows, info = [], {}
    r, info["proxies"] = run_set(proxy, cons_p, "CA_TBILL", "proxies"); rows += r
    r, info["tickers"] = run_set(tick, cons_t, "ZST.TO", "tickers"); rows += r
    r, info["refs"] = run_set(refs(), {}, "ZST.TO", "refs_unconstrained"); rows += r
    df = pd.DataFrame(rows)
    cols = ["set", "strategy", "window", "ann_return", "ann_real_return", "volatility", "max_drawdown", "recovery_months",
            "cvar_5", "worst_12m", "risk_breaches"]
    pd.set_option("display.width", 250)
    print(df[cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = write_json({"caps": {"tech_cap": TECH_CAP, "single_name_cap": NAME_CAP, "crypto_cap_bands": CRYPTO_CAP_BANDS,
                             "crypto_cap_annual": CRYPTO_CAP_ANNUAL},
                    "map": MAP, "data_info": info, "rows": df.to_dict(orient="records")},
                   RESULTS / "amira_tickers" / f"verify_{stamp}.json",
                   ["results/amira_sweep_tech/derived_thresholds.json", "results/amira_sat_single/derived_single_name_cap.json",
                    "results/amira_sat_crypto/derived_crypto_cap.json", "results/amira_sat_crypto/crypto_proposal.json"])
    print(p)


if __name__ == "__main__":
    main()
