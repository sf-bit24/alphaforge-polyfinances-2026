"""Shared helpers for the cross-check Amira / Mateo / Robert x regulatory analysis (analyse/relation-profils-actifs).
Imports the engine, never modifies it. SIMULATION ONLY - historical reconstructions, not financial advice.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from alphaforge.finance.backtest.data import data_version
from alphaforge.finance.backtest.run import DISCLAIMER, _clean, engine_hash
from alphaforge.finance.backtest.validation import robust_table

BT = Path(__file__).resolve().parents[2]
RES = BT / "results"
OUT = RES / "croisement_analysis"
OUT.mkdir(parents=True, exist_ok=True)
REG = Path(os.environ.get("ALPHAFORGE_REG_DIR", "relation-profils-actifs"))  # READ ONLY

# Retained traces of the persona reports (reports/{robert,mateo,amira}.md, current versions after the glidepath fix)
ORIG = {
    "robert_cad|non_overlapping|4": "results/robert_cad/20261114T233723Z_non_overlapping_h4.json",
    "robert_cad|rolling|4": "results/robert_cad/20261114T234006Z_rolling_h4.json",
    "robert_long_usd|non_overlapping|4": "results/robert_long_usd/20261114T234617Z_non_overlapping_h4.json",
    "robert_long_usd|rolling|4": "results/robert_long_usd/20261114T234412Z_rolling_h4.json",
    "mateo_usd_long_esg|rolling|10": "results/mateo_usd_long_esg/20261115T000606Z_rolling_h10.json",
    "mateo_usd_gold_esg|rolling|10": "results/mateo_usd_gold_esg/20261114T235948Z_rolling_h10.json",
    "mateo_cad_esg|rolling|10": "results/mateo_cad_esg/20261114T234928Z_rolling_h10.json",
    "mateo_cad_esg|non_overlapping|10": "results/mateo_cad_esg/20261114T234337Z_non_overlapping_h10.json",
    "amira_etf|non_overlapping|15": "results/amira_etf/20261114T224838Z_non_overlapping_h15.json",
    "amira_etf|rolling|15": "results/amira_etf/20261114T225010Z_rolling_h15.json",
    "amira_etf|rolling|20": "results/amira_etf/20261114T225046Z_rolling_h20.json",
    "amira_etf_long_usd|non_overlapping|15": "results/amira_etf_long_usd/20261114T224857Z_non_overlapping_h15.json",
    "amira_etf_long_usd|rolling|15": "results/amira_etf_long_usd/20261114T225227Z_rolling_h15.json",
    "amira_etf_long_usd|rolling|20": "results/amira_etf_long_usd/20261114T225343Z_rolling_h20.json",
}

EQ_CA = {"CA_EQ", "XIU.TO"}
EQ_US_BROAD = {"US_MKT", "US_MKT_XEN", "SPY", "ESGV", "QQQ"}
GOLD = {"GOLD", "GLD"}
CASH = {"CA_TBILL", "UST_TBILL", "ZST.TO"}
CRYPTO = {"BTC-USD", "ETH-USD"}


def asset_class(a: str) -> str:
    """Map an engine asset to the regulatory analysis classes (00-cadre.md section 3).
    Proxies: CA_EQ/US_MKT(_XEN) = index funds (XIU.TO / SPY / ESGV) -> 'fnb_actions';
    US_IND_* (KF industries) = stand-in for individual US stocks -> 'actions_us';
    bonds and cash (ZST.TO is a bond ETF in their table) -> 'fnb_oblig' (cash reported separately)."""
    if a in EQ_CA or a in EQ_US_BROAD:
        return "fnb_actions"
    if a.startswith("US_IND_"):
        return "actions_us"
    if a in GOLD:
        return "or"
    if a in CASH:
        return "encaisse"
    if a in CRYPTO:
        return "crypto"
    if a.endswith(".TO"):
        return "actions_ca"
    if a.startswith(("UST_", "CORP_", "CA_GOV")) or a in {"XBB.TO", "AGG", "TLT"}:
        return "fnb_oblig"
    return "actions_us"


def class_weights(w: dict) -> dict:
    out: dict = {}
    for a, x in w.items():
        k = asset_class(a)
        out[k] = out.get(k, 0.0) + float(x)
    out["actions_total"] = out.get("fnb_actions", 0) + out.get("actions_us", 0) + out.get("actions_ca", 0)
    out["oblig_et_encaisse"] = out.get("fnb_oblig", 0) + out.get("encaisse", 0)
    return out


def load(path: str | Path) -> dict:
    return json.loads((BT / path).read_text())


def rows(path) -> pd.DataFrame:
    t = load(path)
    df = pd.DataFrame(t["results"])
    df["missed_target"] = df["missed_target"].astype(object)
    return df


def latest(pid: str, mode: str, h) -> str:
    fs = sorted(glob.glob(str(RES / "croisement_runs" / pid / f"*_{mode}_h{float(h):g}.json")))
    if not fs:
        raise FileNotFoundError(f"{pid} {mode} h{h}")
    return str(Path(fs[-1]).relative_to(BT))


def rtable(df: pd.DataFrame, max_breach: float | None) -> pd.DataFrame:
    return robust_table(df, 0.10, max_breach)


def strategy_class_weights(df: pd.DataFrame, strategy: str) -> pd.DataFrame:
    g = df[df.strategy == strategy]
    W = pd.DataFrame([class_weights(w if isinstance(w, dict) else json.loads(w)) for w in g.avg_weights]).fillna(0)
    W.index = g.window.values
    return W


def q(s: pd.Series, p: float) -> float:
    return float(np.quantile(s.values, p)) if len(s) else float("nan")


def write(name: str, payload: dict, inputs: list[str], params: dict | None = None) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace = {"run_id": name, "created_utc": stamp, "disclaimer": DISCLAIMER, "engine_sha256": engine_hash(),
             "data_version": data_version(), "script": f"analysis/croisement/{name}.py", "inputs": inputs,
             "params": params or {}, "results": payload}
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(_clean(trace), indent=1, default=str))
    return str(p.relative_to(BT))


def simulate_long(profile: dict, spec: dict, skip_months: int = 61) -> pd.Series:
    """Monthly net returns of one strategy over ONE long window (all months after `skip_months` of history, so
    estimation-based strategies do not use their fallback weights). Same engine functions as the per-window runs
    (engine.backtest.run_window); only the window differs. Returns a Series indexed by month-end."""
    from alphaforge.finance.backtest.backtest import ConstraintProvider, run_window
    from alphaforge.finance.backtest.data import load_inflation, load_returns
    from alphaforge.finance.backtest.strategies import build_strategy
    from alphaforge.finance.backtest.windows import Window
    p = profile
    R = load_returns(p["universe"], p["period"]["start"], p["period"]["end"], p["currency"], p["fx_fill"])
    infl = load_inflation(p["currency"])
    R = R.loc[: infl.index.max()]
    months = R.index[skip_months:]
    w = Window(months[0], months[-1], len(months))
    res = run_window(R, infl, w, build_strategy(spec), p, ConstraintProvider(p["universe"], p["constraints"]), None, None)
    s = res["returns"]
    s.attrs["fallback_months"] = int(res["metrics"]["fallback_months"])
    return s
