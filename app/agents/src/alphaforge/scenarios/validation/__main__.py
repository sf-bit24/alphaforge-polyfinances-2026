"""Point d'entrée de la validation hors échantillon (volet C).

    cd app/agents
    uv run --group scenarios python -m alphaforge.scenarios.validation \
        --input <données longues> --output <dossier> [--ref <run de référence>] [--workers 12] [--n-paths 4000]

Sorties (``--output``) : ``scores.csv.gz`` (une ligne par famille × modèle × origine × mélange × H),
``fits.csv``, ``per_mix.csv``, ``pooled.csv``, ``reliability.csv``, ``pit_hist.csv``, ``checks/*.csv|json``,
``tables.md`` (tableaux du rapport, générés) et ``manifest.json`` (configuration, graine, ``data_sha256``,
empreinte du code, durées). Résultat déterministe pour une graine donnée, quel que soit ``--workers``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..data import Inputs, Pool, load_inputs
from ..job import package_sha
from . import checks
from .analysis import ks_summary, per_mix_summary, pit_histogram, pooled_summary, reliability
from .report import ValidationResults, write_tables
from .walkforward import WFConfig, make_pools, run_walkforward

VALIDATION_DIR = Path(__file__).resolve().parent


def validation_sha() -> str:
    digest = hashlib.sha256()
    for path in sorted(VALIDATION_DIR.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m alphaforge.scenarios.validation")
    parser.add_argument(
        "--input", required=True, help="dossier des données longues (alphaforge/data/long ou ALPHAFORGE_BT_DATA)"
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--ref", default=None, help="dossier d'un run du job (contrôle de monotonie)")
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--n-paths", type=int, default=4000)
    parser.add_argument("--n-boot", type=int, default=1000, help="réplications du bootstrap par blocs sur les origines")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--families", default="CAD77,CAD71,USD1926,USD1953")
    parser.add_argument("--max-origins", type=int, default=None)
    return parser


def _walkforward_config(args: argparse.Namespace) -> WFConfig:
    return WFConfig(
        input_dir=args.input,
        seed=args.seed,
        n_paths=args.n_paths,
        families=tuple(args.families.split(",")),
        max_origins=args.max_origins,
        workers=args.workers,
    )


@contextmanager
def _timed(timings: dict[str, float], key: str) -> Iterator[None]:
    """Range sous ``key`` la durée du bloc, en secondes arrondies au dixième."""
    started = time.perf_counter()
    yield
    timings[key] = round(time.perf_counter() - started, 1)


def _aggregate(scores: pd.DataFrame, n_boot: int, seed: int, out: Path) -> dict[str, pd.DataFrame]:
    """Résumés par mélange et agrégés, fiabilité, histogrammes PIT et KS, écrits en CSV ; renvoie ceux du rapport
    (clés : champs de ``ValidationResults``)."""
    per_mix = per_mix_summary(scores, n_boot, seed)
    pooled = pooled_summary(scores, n_boot, seed)
    reliability_table = reliability(scores)
    pit_hist = pit_histogram(scores)
    per_mix.to_csv(out / "per_mix.csv", index=False, float_format="%.6g")
    pooled.to_csv(out / "pooled.csv", index=False, float_format="%.6g")
    reliability_table.to_csv(out / "reliability.csv", index=False, float_format="%.6g")
    pit_hist.to_csv(out / "pit_hist.csv", index=False)
    ks_table = ks_summary(per_mix)
    ks_table.to_csv(out / "ks_summary.csv", index=False)
    return {"per_mix": per_mix, "pooled": pooled, "reliability": reliability_table, "ks_summary": ks_table}


def _targeted_checks(scores: pd.DataFrame, pools: dict[str, Pool], seed: int, out: Path) -> dict[str, Any]:
    """Contrôles ciblés (hausse des taux, 2021-2023, HMM USD1926, repères historiques), écrits dans ``checks/``
    (clés : champs de ``ValidationResults``)."""
    rising_rates = checks.rising_rates(scores)
    rising_rates.to_csv(out / "checks" / "rising_rates.csv", index=False, float_format="%.6g")
    recent = checks.recent_episode(scores)
    recent.to_csv(out / "checks" / "recent_2021_2023.csv", index=False, float_format="%.6g")
    hmm = checks.hmm_usd1926(pools, seed) if "USD1926" in pools else {}
    (out / "checks" / "hmm_usd1926.json").write_text(json.dumps(hmm, indent=2), encoding="utf-8")
    historical_mdd = checks.historical_bond_mdd(pools)
    historical_mdd.to_csv(out / "checks" / "historical_mdd_windows.csv", index=False, float_format="%.6g")
    return {"rising_rates": rising_rates, "recent": recent, "hmm": hmm, "historical_mdd": historical_mdd}


def _reference_checks(ref: str | None, out: Path) -> dict[str, Any]:
    """Contrôles sur le run de référence du job (``--ref``) : monotonie et doublons du fichier de sensibilité."""
    if not ref:
        return {"monotonicity": pd.DataFrame(), "duplicates": {}}
    ref_dir = Path(ref)
    monotonicity = checks.monotonicity_reference(ref_dir / "table" / "scenarios.parquet")
    monotonicity.to_csv(out / "checks" / "monotonicity_reference.csv", index=False)
    duplicates = checks.sensitivity_duplicates(ref_dir)
    (out / "checks" / "sensitivity_duplicates.json").write_text(json.dumps(duplicates, indent=2), encoding="utf-8")
    return {"monotonicity": monotonicity, "duplicates": duplicates}


def _provenance(args: argparse.Namespace, config: WFConfig, inputs: Inputs) -> dict[str, Any]:
    """Début du manifeste : configuration, données et empreintes du code."""
    return {
        "what": "validation walk-forward hors échantillon des scénarios (volet C)",
        "config": asdict(config),
        "n_boot_origins": args.n_boot,
        "data_sha256": inputs.data_sha256,
        "data_version": inputs.data_version,
        "input_files_sha256": inputs.files_sha256,
        "scenarios_package_sha": package_sha(),
        "validation_code_sha": validation_sha(),
        "ref_run": args.ref,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    out = Path(args.output)
    (out / "checks").mkdir(parents=True, exist_ok=True)
    t_start = time.perf_counter()
    config = _walkforward_config(args)
    inputs = load_inputs(args.input)
    pools = make_pools(inputs)
    timings: dict[str, float] = {}
    with _timed(timings, "look_ahead_s"):
        look_ahead = checks.look_ahead_real(pools)
        pd.DataFrame(look_ahead).to_csv(out / "checks" / "look_ahead_real.csv", index=False)
    with _timed(timings, "walkforward_s"):
        scores, fits = run_walkforward(config)
    scores.to_csv(out / "scores.csv.gz", index=False, float_format="%.6g")
    fits.to_csv(out / "fits.csv", index=False)
    warnings.filterwarnings("ignore", category=RuntimeWarning)  # moyennes vides (repère ponctuel sans intervalle)
    with _timed(timings, "aggregate_s"):
        aggregates = _aggregate(scores, args.n_boot, args.seed, out)
    results = ValidationResults(
        look_ahead=look_ahead,
        fits=fits,
        **aggregates,
        **_targeted_checks(scores, pools, args.seed, out),
        **_reference_checks(args.ref, out),
    )
    write_tables(out, results)
    timings["total_s"] = round(time.perf_counter() - t_start, 1)
    manifest = {
        **_provenance(args, config, inputs),
        "n_score_rows": int(len(scores)),
        "timings": timings,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "pools": {name: pool.describe() | {"name": pool.name} for name, pool in pools.items()},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"output": str(out), "rows": len(scores), **timings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
