"""CLI and Python entry point: backtest a profile over all windows (ex-ante strategies + oracle).

    uv run --group finance python -I -m alphaforge.finance.backtest.run --profile example
        [--mode rolling|non_overlapping] [--horizon N] [--start 1926-07] [--end 2026-09] [--step 12]
        [--no-oracle] [--profiles-dir DIR] [--out DIR]

SIMULATION ONLY - historical backtests describe the past, they are not forecasts nor advice.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import ConstraintProvider, run_window
from .data import data_version, load_inflation, load_returns
from .oracle import oracle_window
from .paths import PACKAGE_DIR, results_dir
from .profile import load_profile
from .strategies import build_strategy
from .validation import robust_table, walk_forward
from .windows import windows

DISCLAIMER = ("Simulation historique uniquement (donnees publiques). Ne constitue pas un conseil financier. "
              "Les resultats passes ne predisent pas les resultats futurs. Les lignes hindsight=True (ORACLE) "
              "utilisent le futur et sont non investissables.")


# build_data.py rebuilds the dataset (covered by data_sha256); it is not part of the simulation code.
NOT_ENGINE = {"build_data.py"}


def engine_hash() -> str:
    """SHA-256 (16 hex) of the engine modules, written in every trace."""
    h = hashlib.sha256()
    for p in sorted(PACKAGE_DIR.glob("*.py")):
        if p.name not in NOT_ENGINE:
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, dt.date)):
        return str(o.date() if isinstance(o, pd.Timestamp) else o)
    return o


def run_profile(profile: dict, mode: str | None = None, horizon: float | None = None, start=None, end=None,
                step_months: int | None = None, oracle: bool | None = None, out_dir: Path | None = None,
                write: bool = True, verbose: bool = True) -> dict:
    """Run every strategy of `profile` on every window. Returns a dict with DataFrames and the trace path."""
    p = copy.deepcopy(profile)
    if mode:
        p["mode"] = mode
    if horizon:
        p["horizon_years"] = horizon
    if step_months:
        p["step_months"] = step_months
    if start:
        p["period"]["start"] = start
    if end:
        p["period"]["end"] = end
    if oracle is not None:
        p["oracle"]["enabled"] = oracle
    run_warnings: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        R = load_returns(p["universe"], p["period"]["start"], p["period"]["end"], p["currency"], p["fx_fill"])
        infl = load_inflation(p["currency"])
        provider = ConstraintProvider(p["universe"], p["constraints"])
        cs0 = provider.at(R.index[-1])
        cs0.feasible_point()  # raises early if constraints are infeasible
    run_warnings += [str(w.message) for w in caught]
    info = R.attrs["info"]
    R = R.loc[: infl.index.max()]
    wins = windows(p["horizon_years"], R.index.min(), R.index.max(), p["mode"], p["step_months"], index=R.index)
    if not wins:
        raise ValueError(f"no complete {p['horizon_years']}y window in {info['effective']}")
    strategies = [build_strategy(s) for s in p["strategies"]]
    fb = None
    if p.get("fallback_weights"):
        fb = cs0.project(np.array([float(p["fallback_weights"].get(a, 0)) for a in p["universe"]]))
    rows, oracle_out, cache = [], [], {}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for w in wins:
            for s in strategies:
                res = run_window(R, infl, w, s, p, provider, cache, fb)
                m = res["metrics"]
                rows.append({"window": w.label, "start": w.start.date(), "end": w.end.date(), "strategy": s.name,
                             "hindsight": False, **{k: v for k, v in m.items() if k != "risk_breaches"},
                             "n_breaches": len(m["risk_breaches"]), "risk_breaches": "; ".join(m["risk_breaches"]),
                             "avg_weights": {a: round(float(x), 4) for a, x in res["weights"].mean().items()}})
            if p["oracle"]["enabled"]:
                o = oracle_window(R, infl, w, p, provider, seed=int(p["seed"]))
                m = o["metrics"]
                rows.append({"window": w.label, "start": w.start.date(), "end": w.end.date(), "strategy": "ORACLE",
                             "hindsight": True, **{k: v for k, v in m.items() if k != "risk_breaches"},
                             "n_breaches": len(m["risk_breaches"]), "risk_breaches": "; ".join(m["risk_breaches"]),
                             "avg_weights": o["weights"]})
                oracle_out.append({"window": w.label, **o})
            if verbose:
                print(f"  window {w.label} done", file=sys.stderr)
    run_warnings += sorted({str(w.message) for w in caught})
    df = pd.DataFrame(rows)
    sel = p["selection"]
    robust = robust_table(df, sel["quantile"], sel.get("max_breach_rate"))
    wf = walk_forward(df, sel["quantile"], sel.get("max_breach_rate"), int(sel.get("min_past_windows", 3)))
    summary = {
        "robust_choice": robust.index[0],
        "robust_rule": f"max of score_p{int(sel['quantile'] * 100)} across windows"
        + (f", excluding breach_rate > {sel['max_breach_rate']}" if sel.get("max_breach_rate") is not None else ""),
        "walk_forward": {
            "n_oos_windows": int(len(wf)),
            "mean_oos_score": float(wf["chosen_score"].mean()) if len(wf) else None,
            "p10_oos_score": float(wf["chosen_score"].quantile(0.10)) if len(wf) else None,
            "oos_shortfall_prob": float(wf["chosen_missed_target"].astype(float).mean())
            if len(wf) and wf["chosen_missed_target"].notna().all()
            else None,
            "mean_oracle_gap": float((wf["oracle_score"] - wf["chosen_score"]).mean()) if len(wf) else None,
        },
    }
    result = {
        "profile": p,
        "data_info": info,
        "windows": [w.label for w in wins],
        "rows": df,
        "robust": robust,
        "walk_forward": wf,
        "oracle": oracle_out,
        "summary": summary,
        "warnings": run_warnings,
    }
    if write:
        out_dir = Path(out_dir or results_dir() / p["id"])
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        base = out_dir / f"{stamp}_{p['mode']}_h{p['horizon_years']:g}"
        flat = df.drop(columns=["avg_weights"]).copy()
        flat["avg_weights"] = df["avg_weights"].apply(json.dumps)
        flat.to_csv(f"{base}_windows.csv", index=False)
        robust.to_csv(f"{base}_robust.csv")
        wf.to_csv(f"{base}_walkforward.csv", index=False)
        trace = {
            "run_id": base.name,
            "created_utc": stamp,
            "disclaimer": DISCLAIMER,
            "engine_sha256": engine_hash(),
            "data_version": data_version(),
            "seed": p["seed"],
            "profile": p,
            "data_info": info,
            "windows": result["windows"],
            "results": df.to_dict(orient="records"),
            "oracle": oracle_out,
            "robust_selection": robust.reset_index().to_dict(orient="records"),
            "walk_forward": wf.to_dict(orient="records"),
            "summary": summary,
            "warnings": run_warnings,
            "files": {
                "windows_csv": f"{base.name}_windows.csv",
                "robust_csv": f"{base.name}_robust.csv",
                "walkforward_csv": f"{base.name}_walkforward.csv",
            },
        }
        path = Path(f"{base}.json")
        path.write_text(json.dumps(_clean(trace), indent=1, default=str))
        result["trace_path"] = str(path)
    return result


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True, help="profile id (<profiles dir>/<id>.yaml) or path to a YAML file")
    ap.add_argument(
        "--profiles-dir",
        help="directory searched for the profile id (default: ALPHAFORGE_BT_PROFILES, "
        "else the packaged profiles/ folder)",
    )
    ap.add_argument("--mode", choices=["rolling", "non_overlapping"])
    ap.add_argument("--horizon", type=float, help="horizon in years (overrides the profile)")
    ap.add_argument("--step", type=int, help="rolling step in months")
    ap.add_argument("--start"), ap.add_argument("--end")
    ap.add_argument("--no-oracle", action="store_true")
    ap.add_argument(
        "--out",
        help="output directory (default: ALPHAFORGE_BT_RESULTS or ./backtest-results, then /<profile id>)",
    )
    a = ap.parse_args(argv)
    prof = load_profile(a.profile, a.profiles_dir)
    res = run_profile(
        prof, a.mode, a.horizon, a.start, a.end, a.step, False if a.no_oracle else None, Path(a.out) if a.out else None
    )
    pd.set_option("display.width", 200, "display.max_columns", 30)
    info = res["data_info"]
    print(f"\n{DISCLAIMER}\n")
    print(
        f"Profile {prof['id']} | {info['currency']} | data {info['effective'][0]}..{info['effective'][1]} "
        f"({info['n_months']} months) | limiting start asset: {info['limiting_start_asset']} "
        f"| windows: {len(res['windows'])} x {res['profile']['horizon_years']:g}y ({res['profile']['mode']})"
    )
    for w in res["warnings"]:
        print("WARNING:", w)
    rows = res["rows"]
    cols = [
        "window",
        "strategy",
        "ann_real_return",
        "volatility",
        "max_drawdown",
        "cvar_5",
        "final_real_wealth",
        "score",
        "missed_target",
        "n_breaches",
    ]
    print("\nPer-window results (ORACLE = hindsight, non investable):")
    print(rows[cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("\nScore by window (rows) and strategy (columns):")
    print(rows.pivot(index="window", columns="strategy", values="score").to_string(float_format=lambda x: f"{x:.4f}"))
    print("\nRobust selection:")
    print(res["robust"].to_string(float_format=lambda x: f"{x:.4f}"))
    print("\nWalk-forward (out-of-sample):")
    print(
        res["walk_forward"].to_string(index=False, float_format=lambda x: f"{x:.4f}")
        if len(res["walk_forward"])
        else "  not enough past windows"
    )
    print("\nSummary:", json.dumps(_clean(res["summary"]), indent=1))
    print("\nTrace:", res["trace_path"])


if __name__ == "__main__":
    main()
