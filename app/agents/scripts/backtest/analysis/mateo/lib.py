"""Helpers to read the Mateo stage-B traces (runs_B_*.json) - no computation of new returns here."""
from __future__ import annotations

import glob
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BT = HERE.parent.parent
OUT = BT / "results" / "mateo_analysis"
OUT.mkdir(parents=True, exist_ok=True)

CLASS_MAP = {"US_MKT": "eq_core", "US_MKT_XEN": "eq_core", "CA_EQ": "eq_ca", "UST_TBILL": "cash", "CA_TBILL": "cash",
             "UST_2Y": "bond_short", "UST_5Y": "bond_mid", "UST_10Y": "bond_10y", "UST_20Y": "bond_long",
             "CA_GOV_10Y": "bond_10y", "CORP_AAA": "bond_corp", "GOLD": "gold"}


def cls(a):
    return CLASS_MAP.get(a, "eq_sector" if a.startswith("US_IND_") else "other")


@lru_cache(maxsize=1)
def runs() -> dict:
    d = {}
    for f in sorted(glob.glob(str(HERE / "runs_B*.json"))):
        d.update(json.loads(Path(f).read_text()))
    return d


def trace_path(pid, mode, h, orc=None):
    r = runs()
    for o in ([orc] if orc is not None else ["1", "0"]):
        k = f"{pid}:{mode}:{h}:{o}"
        if k in r:
            return r[k]
    return None


@lru_cache(maxsize=None)
def load(path) -> dict:
    return json.loads((BT / path).read_text())


def rows(path) -> pd.DataFrame:
    df = pd.DataFrame(load(path)["results"])
    return df


def grouped_weights(w: dict) -> dict:
    out = {}
    for a, x in w.items():
        out[cls(a)] = out.get(cls(a), 0.0) + float(x)
    out["equity_total"] = out.get("eq_core", 0) + out.get("eq_ca", 0) + out.get("eq_sector", 0)
    out["bonds_total"] = sum(out.get(k, 0) for k in ("bond_short", "bond_mid", "bond_10y", "bond_long", "bond_corp"))
    out["duration_long_share"] = out.get("bond_long", 0) + out.get("bond_corp", 0)  # ~20y maturities
    return out
