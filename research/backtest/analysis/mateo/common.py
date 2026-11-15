"""Shared setup for the Mateo analysis (imports the engine WITHOUT modifying it).

1. Points the engine to the derived dataset analysis/mateo/data_ext (adds US_MKT_XEN, see build_ext_data.py).
2. Look-through for US_MKT_XEN: tech share = BusEq / (1 - Enrgy) of the KF cap shares (time-varying),
   energy = 0. The engine only knows time-varying look-through for US_MKT, so we wrap
   engine.constraints.exposure_vector (runtime wrapper, engine files untouched).
3. Registers a 'delayed_glidepath' strategy type (hold start_weights until `derisk_start` (fraction of the
   window), then linear to end_weights) - needed to DERIVE the de-risking start date by sensitivity.
SIMULATION ONLY - not financial advice.
"""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
BT = HERE.parent.parent
os.environ["ALPHAFORGE_BT_DATA"] = str(HERE / "data_ext")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import engine.constraints as C  # noqa: E402
import engine.profile as P  # noqa: E402
import engine.strategies as S  # noqa: E402
from engine import data as D  # noqa: E402

assert str(D.DATA_DIR) == str(HERE / "data_ext"), D.DATA_DIR

_orig_exposure_vector = D.exposure_vector


def _xen_share(tag: str, date=None, window=None) -> float | None:
    lt = D.load_lookthrough()
    if tag == "energy":
        return 0.0
    if tag not in D.LOOKTHROUGH_TAGS:
        return None
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


class DelayedGlidepath(S.Strategy):
    """Hold start_weights until ELAPSED TIME reaches `derisk_start` x horizon, then interpolate linearly to
    end_weights, reached at the LAST scheduled decision of the window.

    Convention (engine fix 2026-11-14): ctx.progress = i / last_decision_month (0 at the first decision, 1 at the
    last one), no longer i / n. To keep "de-risk from year 5" = month 60 for every rebalancing frequency, the month
    index is recovered as i = progress x last, with last = last scheduled decision month computed from the
    injected params `_n_months` (window length) and `_frequency` (see inject_glide_params). Then
        i0 = ceil(derisk_start x n);  a = 0 if i < i0 else (i - i0) / (last - i0)
    Annual 120 m, derisk_start 0.5: decisions 60, 72, 84, 96, 108 -> a = 0, .25, .5, .75, 1.
    """
    type = "delayed_glidepath"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.window_dependent = True

    def _target(self, hist, ctx):
        from engine.backtest import _due
        w0 = S._vec(ctx.assets, self.params["start_weights"])
        w1 = S._vec(ctx.assets, self.params["end_weights"])
        n = int(self.params["_n_months"])
        freq = self.params.get("_frequency", "annual")
        last = max(j for j in range(n) if _due(freq, j))
        i = int(round(ctx.progress * last))
        i0 = int(np.ceil(float(self.params.get("derisk_start", 0.0)) * n - 1e-9))
        a = 0.0 if i < i0 or last <= i0 else min(1.0, (i - i0) / (last - i0))
        return (1 - a) * w0 + a * w1


def inject_glide_params(p: dict, horizon_years: float | None = None) -> dict:
    """Copy of profile p where each delayed_glidepath strategy gets _n_months and _frequency."""
    import copy
    q = copy.deepcopy(p)
    h = horizon_years or q["horizon_years"]
    for s in q["strategies"]:
        if s["type"] == "delayed_glidepath":
            s.setdefault("params", {})
            s["params"]["_n_months"] = int(round(h * 12))
            s["params"]["_frequency"] = (s.get("rebalancing") or q["rebalancing"]).get("frequency", "annual")
    return q


S.REGISTRY["delayed_glidepath"] = DelayedGlidepath
P.STRATEGY_TYPES = tuple(P.STRATEGY_TYPES) + ("delayed_glidepath",)

from engine.run import run_profile as _engine_run_profile  # noqa: E402


def run_profile(profile, mode=None, horizon=None, *a, **k):
    """engine.run.run_profile with delayed_glidepath params injected for the effective horizon."""
    return _engine_run_profile(inject_glide_params(profile, horizon), mode, horizon, *a, **k)
from engine.profile import load_profile  # noqa: E402,F401

PATCH_NOTE = ("analysis/mateo/common.py: data=analysis/mateo/data_ext (US_MKT_XEN added); runtime wrapper on "
              "engine.constraints.exposure_vector (US_MKT_XEN tech look-through = BusEq/(1-Enrgy)); strategy type "
              "delayed_glidepath registered (de-risk start in elapsed months, end at last decision; uses engine progress = i/last_decision since the 2026-11-14 engine fix). engine/*.py unchanged.")


def annotate_trace(path: str, extra: dict) -> None:
    import json
    p = Path(path)
    t = json.loads(p.read_text())
    t["mateo_analysis"] = {"patch_note": PATCH_NOTE, **extra}
    p.write_text(json.dumps(t, indent=1, default=str))
