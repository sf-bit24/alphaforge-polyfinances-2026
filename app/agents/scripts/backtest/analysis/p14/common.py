"""Shared setup for the persona 14 (Tyler) analysis. Imports the engine WITHOUT modifying it.

1. Points the engine to the derived dataset analysis/p14/data_ext (adds US_MKT_XEN = US market ex-energy,
   see build_ext_data.py; method copied from analysis/mateo/).
2. Look-through for US_MKT_XEN: energy = 0, tech = BusEq / (1 - Enrgy) of the KF cap shares at the decision
   date (runtime wrapper around engine.constraints.exposure_vector; engine files untouched).
SIMULATION ONLY - not financial advice.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
BT = HERE.parent.parent
OUT = BT / "results" / "p14_analysis"
OUT.mkdir(parents=True, exist_ok=True)
os.environ["ALPHAFORGE_BT_DATA"] = str(HERE / "data_ext")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import alphaforge.finance.backtest.constraints as C  # noqa: E402
from alphaforge.finance.backtest import data as D  # noqa: E402

assert str(D.DATA_DIR) == str(HERE / "data_ext"), D.DATA_DIR

_orig_exposure_vector = D.exposure_vector


def _xen_share(tag, date=None, window=None):
    if tag == "energy":
        return 0.0
    if tag not in D.LOOKTHROUGH_TAGS:
        return None
    lt = D.load_lookthrough()
    col = lt[D.LOOKTHROUGH_TAGS[tag]] / (1 - lt["US_IND_ENRGY"])
    if window is not None:
        seg = col.loc[D.to_month_end(window[0]) - pd.offsets.MonthEnd(1):D.to_month_end(window[1])]
        return float(seg.max()) if len(seg) else float(col.iloc[-1])
    if date is not None:
        seg = col.loc[:D.to_month_end(date)]
        return float(seg.iloc[-1]) if len(seg) else float(col.iloc[0])
    return None


def exposure_vector(assets, tag, date=None, overrides=None, window=None):
    v = _orig_exposure_vector(assets, tag, date=date, overrides=overrides, window=window)
    if "US_MKT_XEN" in assets and not (overrides and "US_MKT_XEN" in overrides):
        s = _xen_share(tag, date, window)
        if s is not None:
            v[list(assets).index("US_MKT_XEN")] = s
    return v


C.exposure_vector = exposure_vector

from alphaforge.finance.backtest.profile import load_profile  # noqa: E402,F401
from alphaforge.finance.backtest.run import run_profile  # noqa: E402,F401

PATCH_NOTE = ("analysis/p14/common.py: data=analysis/p14/data_ext (US_MKT_XEN added); runtime wrapper on "
              "engine.constraints.exposure_vector (US_MKT_XEN energy=0, tech=BusEq/(1-Enrgy)). engine/*.py unchanged.")


def annotate_trace(path, extra: dict) -> None:
    p = Path(path)
    t = json.loads(p.read_text())
    t["p14_analysis"] = {"patch_note": PATCH_NOTE, **extra}
    p.write_text(json.dumps(t, indent=1, default=str))


def dump(name: str, obj) -> Path:
    p = OUT / name
    if isinstance(obj, pd.DataFrame):
        obj.to_csv(p)
    else:
        p.write_text(json.dumps(obj, indent=1, default=str))
    return p


def drawdown(r: pd.Series) -> pd.Series:
    w = (1 + r).cumprod()
    return w / w.cummax() - 1


def episodes(r: pd.Series, depth: float = 0.30) -> pd.DataFrame:
    """Peak-to-recovery drawdown episodes deeper than `depth` (monthly)."""
    w = (1 + r.fillna(0)).cumprod()
    peak = w.cummax()
    dd = w / peak - 1
    out, in_ep, start = [], False, None
    for i, (d, x) in enumerate(dd.items()):
        if not in_ep and x < 0:
            in_ep, start = True, i - 1 if i > 0 else 0
        if in_ep and x >= 0:
            seg = dd.iloc[start:i + 1]
            out.append((start, i, seg))
            in_ep = False
    if in_ep:
        out.append((start, None, dd.iloc[start:]))
    rows = []
    for s, e, seg in out:
        if seg.min() > -depth:
            continue
        tr = seg.idxmin()
        pk = dd.index[s]
        rows.append({"peak": pk.date(), "trough": tr.date(), "recovered": dd.index[e].date() if e is not None else None,
                     "depth": round(float(seg.min()), 4),
                     "months_peak_to_trough": int(dd.index.get_loc(tr) - s),
                     "months_peak_to_recovery": int(e - s) if e is not None else None,
                     "months_below_minus20": int((seg < -0.20).sum())})
    return pd.DataFrame(rows)
