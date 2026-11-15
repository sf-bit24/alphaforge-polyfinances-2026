"""Shared helpers for persona 35 (Denise Fortier, snowbird) - imports the shared engine, never modifies it.

Key idea: Denise's liability is a MIXED CAD/USD spending basket. We measure "real" returns against a
basket deflator (in CAD):
    pi_b,t = s * [(1 + pi_us,t) * (F_t / F_{t-1}) - 1] + (1 - s) * pi_ca,t
with s = USD share of spending (SCENARIO, declared), F = USDCAD month-end (CAD per USD), pi_us = US CPI-U,
pi_ca = Canada CPI. Shares are rebalanced monthly (assumption). A return deflated by this basket is the change
of purchasing power over Denise's mixed spending, whatever the reporting currency (CAD or USD).

SIMULATION ONLY - historical reconstructions, not forecasts, not financial advice. No FX forecast anywhere.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import sys
import warnings
from pathlib import Path
from alphaforge.finance.backtest.paths import starter_dir

import numpy as np
import pandas as pd

from alphaforge.finance.backtest import metrics as M
from alphaforge.finance.backtest.backtest import ConstraintProvider, run_window
from alphaforge.finance.backtest.data import DATA_DIR, data_version, load_inflation, load_returns
from alphaforge.finance.backtest.oracle import oracle_window
from alphaforge.finance.backtest.profile import load_profile
from alphaforge.finance.backtest.run import DISCLAIMER, _clean, engine_hash
from alphaforge.finance.backtest.strategies import build_strategy
from alphaforge.finance.backtest.validation import robust_table, walk_forward
from alphaforge.finance.backtest.windows import windows

BT = Path(__file__).resolve().parents[2]          # app/agents/scripts/backtest
PROF = BT / "profiles"
RES = BT / "results"
OUT = RES / "p35_analysis"
OUT.mkdir(parents=True, exist_ok=True)
STARTER = starter_dir()  # official starter, committed in the app


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_trace(name: str, payload: dict, params: dict, script: str) -> Path:
    trace = {"run_id": name, "created_utc": stamp(), "disclaimer": DISCLAIMER, "engine_sha256": engine_hash(),
             "data_version": data_version(), "script": f"analysis/p35/{script}", "params": params,
             "results": payload}
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(_clean(trace), indent=1, default=str))
    return p


def fx_monthly() -> pd.Series:
    df = pd.read_parquet(DATA_DIR / "fx_monthly.parquet")
    return df.set_index(pd.to_datetime(df["date"]))["usdcad"]


def basket_inflation(s: float, currency: str = "CAD") -> pd.Series:
    """Monthly inflation of the mixed spending basket (USD share s), expressed in `currency`."""
    pu = load_inflation("USD")
    pc = load_inflation("CAD")
    fx = fx_monthly()
    fxr = fx / fx.shift(1) - 1
    idx = pu.index.intersection(pc.index).intersection(fxr.dropna().index)
    us_in_cad = (1 + pu[idx]) * (1 + fxr[idx]) - 1
    b_cad = s * us_in_cad + (1 - s) * pc[idx]
    if currency.upper() == "CAD":
        return b_cad.rename(f"basket_cad_s{s:g}")
    # same basket measured in USD: divide CAD cost by FX
    return ((1 + b_cad) / (1 + fxr[idx]) - 1).rename(f"basket_usd_s{s:g}")


def wealth_with_withdrawals(port: np.ndarray, binfl: np.ndarray, rate_annual: float) -> np.ndarray:
    """Real (basket units) wealth path, W0 = 1, withdrawal of rate/12 basket units each month end.
    Withdrawals are indexed to the basket (CAD cost of a fixed mixed CAD/USD consumption)."""
    w = np.empty(len(port))
    cur, defl = 1.0, 1.0
    for i, (r, pi) in enumerate(zip(port, binfl)):
        defl *= 1 + pi
        cur = cur * (1 + r) - rate_annual / 12 * defl if cur > 0 else 0.0
        cur = max(cur, 0.0)
        w[i] = cur / defl
    return w


def run_custom(profile: dict, infl: pd.Series, out_name: str, mode: str, horizon: float, step: int = 12,
               start=None, end=None, oracle: bool = True, R: pd.DataFrame | None = None,
               extra_info: dict | None = None, verbose: bool = False) -> dict:
    """Same loop as engine.run.run_profile, but with an EXTERNAL inflation series (the spending basket).

    Writes results/<out_name>/<stamp>_<mode>_h<H>{.json,_windows.csv,_robust.csv,_walkforward.csv}.
    """
    p = copy.deepcopy(profile)
    p["mode"], p["horizon_years"], p["step_months"] = mode, horizon, step
    if start:
        p["period"]["start"] = start
    if end:
        p["period"]["end"] = end
    p["oracle"]["enabled"] = oracle
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if R is None:
            R = load_returns(p["universe"], p["period"]["start"], p["period"]["end"], p["currency"], p["fx_fill"])
        provider = ConstraintProvider(p["universe"], p["constraints"])
        cs0 = provider.at(R.index[-1])
        cs0.feasible_point()
    run_warnings = [str(w.message) for w in caught]
    info = dict(R.attrs.get("info", {}))
    R = R.loc[: infl.index.max()]
    R = R.loc[R.index >= infl.index.min()]
    wins = windows(horizon, R.index.min(), R.index.max(), mode, step, index=R.index)
    strategies = [build_strategy(s) for s in p["strategies"]]
    fb = None
    if p.get("fallback_weights"):
        fb = cs0.project(np.array([float(p["fallback_weights"].get(a, 0)) for a in p["universe"]]))
    rows, oracle_out, cache, series = [], [], {}, {}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for w in wins:
            for s in strategies:
                res = run_window(R, infl, w, s, p, provider, cache, fb)
                m = res["metrics"]
                series[(w.label, s.name)] = res["returns"]
                rows.append({"window": w.label, "start": w.start.date(), "end": w.end.date(), "strategy": s.name,
                             "hindsight": False, **{k: v for k, v in m.items() if k != "risk_breaches"},
                             "n_breaches": len(m["risk_breaches"]), "risk_breaches": "; ".join(m["risk_breaches"]),
                             "avg_weights": {a: round(float(x), 4) for a, x in res["weights"].mean().items()}})
            if oracle:
                o = oracle_window(R, infl, w, p, provider, seed=int(p["seed"]))
                m = o["metrics"]
                rows.append({"window": w.label, "start": w.start.date(), "end": w.end.date(), "strategy": "ORACLE",
                             "hindsight": True, **{k: v for k, v in m.items() if k != "risk_breaches"},
                             "n_breaches": len(m["risk_breaches"]), "risk_breaches": "; ".join(m["risk_breaches"]),
                             "avg_weights": o["weights"]})
                oracle_out.append({"window": w.label, **o})
            if verbose:
                print(f"  {out_name} {w.label} done", file=sys.stderr)
    run_warnings += sorted({str(w.message) for w in caught})
    df = pd.DataFrame(rows)
    sel = p["selection"]
    robust = robust_table(df, sel["quantile"], sel.get("max_breach_rate"))
    wf = walk_forward(df, sel["quantile"], sel.get("max_breach_rate"), int(sel.get("min_past_windows", 3))) \
        if len(wins) > 1 else pd.DataFrame()
    summary = {"robust_choice": robust.index[0],
               "robust_rule": f"max score_p{int(sel['quantile']*100)}, excluding breach_rate > {sel.get('max_breach_rate')}",
               "walk_forward": {
                   "n_oos_windows": int(len(wf)),
                   "mean_oos_score": float(wf["chosen_score"].mean()) if len(wf) else None,
                   "p10_oos_score": float(wf["chosen_score"].quantile(0.10)) if len(wf) else None,
                   "oos_shortfall_prob": float(wf["chosen_missed_target"].astype(float).mean()) if len(wf) else None,
                   "mean_oracle_gap": float((wf["oracle_score"] - wf["chosen_score"]).mean())
                   if len(wf) and "oracle_score" in wf else None}}
    out_dir = RES / out_name
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{stamp()}_{mode}_h{horizon:g}"
    flat = df.drop(columns=["avg_weights"]).copy()
    flat["avg_weights"] = df["avg_weights"].apply(lambda d: json.dumps(_clean(d)))
    flat.to_csv(f"{base}_windows.csv", index=False)
    robust.to_csv(f"{base}_robust.csv")
    wf.to_csv(f"{base}_walkforward.csv", index=False)
    trace = {"run_id": base.name, "created_utc": stamp(), "disclaimer": DISCLAIMER,
             "engine_sha256": engine_hash(), "data_version": data_version(), "seed": p["seed"],
             "runner": "analysis/p35/common.py:run_custom (engine loop with external basket inflation)",
             "inflation_series": infl.name, "extra_info": extra_info or {},
             "profile": p, "data_info": info, "windows": [w.label for w in wins],
             "results": df.to_dict(orient="records"), "oracle": oracle_out,
             "robust_selection": robust.reset_index().to_dict(orient="records"),
             "walk_forward": wf.to_dict(orient="records"), "summary": summary, "warnings": run_warnings}
    path = Path(f"{base}.json")
    path.write_text(json.dumps(_clean(trace), indent=1, default=str))
    return {"rows": df, "robust": robust, "walk_forward": wf, "summary": summary, "trace_path": str(path),
            "series": series, "R": R, "windows": wins, "oracle": oracle_out, "profile": p}


def latest(out_name: str, pattern: str) -> Path:
    c = sorted((RES / out_name).glob(pattern))
    if not c:
        raise FileNotFoundError(f"{out_name}/{pattern}")
    return c[-1]
