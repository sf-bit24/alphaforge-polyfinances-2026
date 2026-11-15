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
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import ConstraintProvider, run_window
from .data import data_version, load_inflation, load_returns
from .oracle import oracle_window
from .paths import PACKAGE_DIR, results_dir
from .profile import load_profile
from .strategies import Strategy, build_strategy
from .validation import robust_table, walk_forward
from .windows import Window, windows

DISCLAIMER = (
    "Simulation historique uniquement (donnees publiques). Ne constitue pas un conseil financier. "
    "Les resultats passes ne predisent pas les resultats futurs. Les lignes hindsight=True (ORACLE) "
    "utilisent le futur et sont non investissables."
)


# build_data.py rebuilds the dataset (covered by data_sha256); it is not part of the simulation code.
NOT_ENGINE = {"build_data.py"}


def engine_hash() -> str:
    """SHA-256 (16 hex) of the engine modules, written in every trace."""
    digest = hashlib.sha256()
    for path in sorted(PACKAGE_DIR.glob("*.py")):
        if path.name not in NOT_ENGINE:
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _clean(value):
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, dt.date)):
        return str(value.date() if isinstance(value, pd.Timestamp) else value)
    return value


@dataclass(frozen=True)
class _ProfileOverrides:
    """Run options that override the profile. An empty value keeps the profile's setting; `oracle` applies whenever
    it is not None."""

    mode: str | None
    horizon: float | None
    start: object
    end: object
    step_months: int | None
    oracle: bool | None

    def applied_to(self, profile: dict) -> dict:
        updated = copy.deepcopy(profile)
        if self.mode:
            updated["mode"] = self.mode
        if self.horizon:
            updated["horizon_years"] = self.horizon
        if self.step_months:
            updated["step_months"] = self.step_months
        if self.start:
            updated["period"]["start"] = self.start
        if self.end:
            updated["period"]["end"] = self.end
        if self.oracle is not None:
            updated["oracle"]["enabled"] = self.oracle
        return updated


@dataclass
class _RunInputs:
    """What the window loop needs, prepared once per run."""

    profile: dict
    returns: pd.DataFrame
    inflation: pd.Series
    provider: ConstraintProvider
    windows: list[Window]
    strategies: list[Strategy]
    fallback: np.ndarray | None
    data_info: dict
    warnings: list[str]


def _prepare(profile: dict) -> _RunInputs:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        period = profile["period"]
        returns = load_returns(
            profile["universe"], period["start"], period["end"], profile["currency"], profile["fx_fill"]
        )
        inflation = load_inflation(profile["currency"])
        provider = ConstraintProvider(profile["universe"], profile["constraints"])
        latest_constraints = provider.at(returns.index[-1])
        latest_constraints.feasible_point()  # raises early if constraints are infeasible
    load_warnings = [str(record.message) for record in caught]
    info = returns.attrs["info"]
    returns = returns.loc[: inflation.index.max()]
    run_windows = windows(
        profile["horizon_years"],
        returns.index.min(),
        returns.index.max(),
        profile["mode"],
        profile["step_months"],
        index=returns.index,
    )
    if not run_windows:
        raise ValueError(f"no complete {profile['horizon_years']}y window in {info['effective']}")
    strategies = [build_strategy(spec) for spec in profile["strategies"]]
    fallback = None
    if profile.get("fallback_weights"):
        weights = profile["fallback_weights"]
        fallback = latest_constraints.project(np.array([float(weights.get(asset, 0)) for asset in profile["universe"]]))
    return _RunInputs(profile, returns, inflation, provider, run_windows, strategies, fallback, info, load_warnings)


def _result_row(window: Window, strategy: str, metrics: dict, avg_weights: dict, *, hindsight: bool) -> dict:
    return {
        "window": window.label,
        "start": window.start.date(),
        "end": window.end.date(),
        "strategy": strategy,
        "hindsight": hindsight,
        **{key: value for key, value in metrics.items() if key != "risk_breaches"},
        "n_breaches": len(metrics["risk_breaches"]),
        "risk_breaches": "; ".join(metrics["risk_breaches"]),
        "avg_weights": avg_weights,
    }


def _simulate(inputs: _RunInputs, *, verbose: bool) -> tuple[list[dict], list[dict], list[str]]:
    """Every strategy (and the oracle) on every window: result rows, oracle details, distinct warnings."""
    profile = inputs.profile
    rows, oracle_details, cache = [], [], {}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for window in inputs.windows:
            for strategy in inputs.strategies:
                result = run_window(
                    inputs.returns, inputs.inflation, window, strategy, profile, inputs.provider, cache, inputs.fallback
                )
                avg_weights = {asset: round(float(x), 4) for asset, x in result["weights"].mean().items()}
                rows.append(_result_row(window, strategy.name, result["metrics"], avg_weights, hindsight=False))
            if profile["oracle"]["enabled"]:
                oracle = oracle_window(
                    inputs.returns, inputs.inflation, window, profile, inputs.provider, seed=int(profile["seed"])
                )
                rows.append(_result_row(window, "ORACLE", oracle["metrics"], oracle["weights"], hindsight=True))
                oracle_details.append({"window": window.label, **oracle})
            if verbose:
                print(f"  window {window.label} done", file=sys.stderr)
    return rows, oracle_details, sorted({str(record.message) for record in caught})


def _walk_forward_summary(out_of_sample: pd.DataFrame) -> dict:
    chosen = out_of_sample["chosen_score"] if len(out_of_sample) else None
    return {
        "n_oos_windows": int(len(out_of_sample)),
        "mean_oos_score": float(chosen.mean()) if len(out_of_sample) else None,
        "p10_oos_score": float(chosen.quantile(0.10)) if len(out_of_sample) else None,
        "oos_shortfall_prob": float(out_of_sample["chosen_missed_target"].astype(float).mean())
        if len(out_of_sample) and out_of_sample["chosen_missed_target"].notna().all()
        else None,
        "mean_oracle_gap": float((out_of_sample["oracle_score"] - chosen).mean()) if len(out_of_sample) else None,
    }


def _summary(robust: pd.DataFrame, walk_forward_rows: pd.DataFrame, selection: dict) -> dict:
    return {
        "robust_choice": robust.index[0],
        "robust_rule": f"max of score_p{int(selection['quantile'] * 100)} across windows"
        + (
            f", excluding breach_rate > {selection['max_breach_rate']}"
            if selection.get("max_breach_rate") is not None
            else ""
        ),
        "walk_forward": _walk_forward_summary(walk_forward_rows),
    }


def _trace(result: dict, base: Path, stamp: str) -> dict:
    """JSON trace of a run: provenance (data and engine hashes, seed, profile) and every result."""
    return {
        "run_id": base.name,
        "created_utc": stamp,
        "disclaimer": DISCLAIMER,
        "engine_sha256": engine_hash(),
        "data_version": data_version(),
        "seed": result["profile"]["seed"],
        "profile": result["profile"],
        "data_info": result["data_info"],
        "windows": result["windows"],
        "results": result["rows"].to_dict(orient="records"),
        "oracle": result["oracle"],
        "robust_selection": result["robust"].reset_index().to_dict(orient="records"),
        "walk_forward": result["walk_forward"].to_dict(orient="records"),
        "summary": result["summary"],
        "warnings": result["warnings"],
        "files": {
            "windows_csv": f"{base.name}_windows.csv",
            "robust_csv": f"{base.name}_robust.csv",
            "walkforward_csv": f"{base.name}_walkforward.csv",
        },
    }


def _write_run_files(result: dict, out_dir: Path) -> str:
    """Writes the windows, robust and walk-forward CSVs, then the JSON trace; returns the trace path."""
    profile = result["profile"]
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    base = out_dir / f"{stamp}_{profile['mode']}_h{profile['horizon_years']:g}"
    rows = result["rows"]
    flat = rows.drop(columns=["avg_weights"]).copy()
    flat["avg_weights"] = rows["avg_weights"].apply(json.dumps)
    flat.to_csv(f"{base}_windows.csv", index=False)
    result["robust"].to_csv(f"{base}_robust.csv")
    result["walk_forward"].to_csv(f"{base}_walkforward.csv", index=False)
    path = Path(f"{base}.json")
    path.write_text(json.dumps(_clean(_trace(result, base, stamp)), indent=1, default=str))
    return str(path)


def run_profile(  # noqa: PLR0913 - public signature: keyword callers (tests, README, the CLI)
    profile: dict,
    mode: str | None = None,
    horizon: float | None = None,
    start=None,
    end=None,
    step_months: int | None = None,
    *,
    oracle: bool | None = None,
    out_dir: Path | None = None,
    write: bool = True,
    verbose: bool = True,
) -> dict:
    """Run every strategy of `profile` on every window. Returns a dict with DataFrames and the trace path."""
    overrides = _ProfileOverrides(
        mode=mode, horizon=horizon, start=start, end=end, step_months=step_months, oracle=oracle
    )
    inputs = _prepare(overrides.applied_to(profile))
    rows, oracle_details, window_warnings = _simulate(inputs, verbose=verbose)
    table = pd.DataFrame(rows)
    selection = inputs.profile["selection"]
    robust = robust_table(table, selection["quantile"], selection.get("max_breach_rate"))
    walk_forward_rows = walk_forward(
        table, selection["quantile"], selection.get("max_breach_rate"), int(selection.get("min_past_windows", 3))
    )
    result = {
        "profile": inputs.profile,
        "data_info": inputs.data_info,
        "windows": [window.label for window in inputs.windows],
        "rows": table,
        "robust": robust,
        "walk_forward": walk_forward_rows,
        "oracle": oracle_details,
        "summary": _summary(robust, walk_forward_rows, selection),
        "warnings": inputs.warnings + window_warnings,
    }
    if write:
        result["trace_path"] = _write_run_files(result, Path(out_dir or results_dir() / inputs.profile["id"]))
    return result


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", required=True, help="profile id (<profiles dir>/<id>.yaml) or path to a YAML file")
    parser.add_argument(
        "--profiles-dir",
        help="directory searched for the profile id (default: ALPHAFORGE_BT_PROFILES, "
        "else the packaged profiles/ folder)",
    )
    parser.add_argument("--mode", choices=["rolling", "non_overlapping"])
    parser.add_argument("--horizon", type=float, help="horizon in years (overrides the profile)")
    parser.add_argument("--step", type=int, help="rolling step in months")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--no-oracle", action="store_true")
    parser.add_argument(
        "--out",
        help="output directory (default: ALPHAFORGE_BT_RESULTS or ./backtest-results, then /<profile id>)",
    )
    return parser


REPORT_COLUMNS = [
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


def _four_decimals(x: float) -> str:
    return f"{x:.4f}"


def _print_report(profile_id: str, result: dict) -> None:
    info = result["data_info"]
    print(f"\n{DISCLAIMER}\n")
    print(
        f"Profile {profile_id} | {info['currency']} | data {info['effective'][0]}..{info['effective'][1]} "
        f"({info['n_months']} months) | limiting start asset: {info['limiting_start_asset']} "
        f"| windows: {len(result['windows'])} x {result['profile']['horizon_years']:g}y ({result['profile']['mode']})"
    )
    for message in result["warnings"]:
        print("WARNING:", message)
    rows = result["rows"]
    print("\nPer-window results (ORACLE = hindsight, non investable):")
    print(rows[REPORT_COLUMNS].to_string(index=False, float_format=_four_decimals))
    print("\nScore by window (rows) and strategy (columns):")
    print(rows.pivot(index="window", columns="strategy", values="score").to_string(float_format=_four_decimals))
    print("\nRobust selection:")
    print(result["robust"].to_string(float_format=_four_decimals))
    print("\nWalk-forward (out-of-sample):")
    walk_forward_rows = result["walk_forward"]
    print(
        walk_forward_rows.to_string(index=False, float_format=_four_decimals)
        if len(walk_forward_rows)
        else "  not enough past windows"
    )
    print("\nSummary:", json.dumps(_clean(result["summary"]), indent=1))
    print("\nTrace:", result["trace_path"])


def main(argv=None) -> None:
    arguments = _argument_parser().parse_args(argv)
    profile = load_profile(arguments.profile, arguments.profiles_dir)
    result = run_profile(
        profile,
        arguments.mode,
        arguments.horizon,
        arguments.start,
        arguments.end,
        arguments.step,
        oracle=False if arguments.no_oracle else None,
        out_dir=Path(arguments.out) if arguments.out else None,
    )
    pd.set_option("display.width", 200, "display.max_columns", 30)
    _print_report(profile["id"], result)


if __name__ == "__main__":
    main()
