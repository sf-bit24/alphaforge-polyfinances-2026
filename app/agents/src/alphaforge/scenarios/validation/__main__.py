"""Point d'entrée de la validation hors échantillon (volet C).

    cd app/agents
    uv run --group scenarios python -m alphaforge.scenarios.validation \
        --input <data/processed> --output <dossier> [--ref <run de référence>] [--workers 12] [--n-paths 4000]

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
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from ..data import load_inputs
from ..job import package_sha
from . import checks
from .analysis import ks_summary, per_mix_summary, pit_histogram, pooled_summary, reliability
from .report import write_tables
from .walkforward import WFConfig, make_pools, run_walkforward

VALIDATION_DIR = Path(__file__).resolve().parent


def validation_sha() -> str:
    h = hashlib.sha256()
    for p in sorted(VALIDATION_DIR.glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m alphaforge.scenarios.validation")
    ap.add_argument("--input", required=True, help="dossier data/processed du build long (lecture seule)")
    ap.add_argument("--output", required=True)
    ap.add_argument("--ref", default=None, help="dossier d'un run du job (contrôle de monotonie)")
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument("--n-paths", type=int, default=4000)
    ap.add_argument("--n-boot", type=int, default=1000, help="réplications du bootstrap par blocs sur les origines")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--families", default="CAD77,CAD71,USD1926,USD1953")
    ap.add_argument("--max-origins", type=int, default=None)
    args = ap.parse_args(argv)

    out = Path(args.output)
    (out / "checks").mkdir(parents=True, exist_ok=True)
    t_start = time.perf_counter()
    cfg = WFConfig(
        input_dir=args.input,
        seed=args.seed,
        n_paths=args.n_paths,
        families=tuple(args.families.split(",")),
        max_origins=args.max_origins,
        workers=args.workers,
    )
    inputs = load_inputs(args.input)
    pools = make_pools(inputs)
    timings = {}

    t0 = time.perf_counter()
    la = checks.look_ahead_real(pools)
    pd.DataFrame(la).to_csv(out / "checks" / "look_ahead_real.csv", index=False)
    timings["look_ahead_s"] = round(time.perf_counter() - t0, 1)

    t0 = time.perf_counter()
    scores, fits = run_walkforward(cfg)
    timings["walkforward_s"] = round(time.perf_counter() - t0, 1)
    scores.to_csv(out / "scores.csv.gz", index=False, float_format="%.6g")
    fits.to_csv(out / "fits.csv", index=False)

    warnings.filterwarnings("ignore", category=RuntimeWarning)  # moyennes vides (repère ponctuel sans intervalle)
    t0 = time.perf_counter()
    per_mix = per_mix_summary(scores, args.n_boot, args.seed)
    pooled = pooled_summary(scores, args.n_boot, args.seed)
    rel = reliability(scores)
    pit_h = pit_histogram(scores)
    per_mix.to_csv(out / "per_mix.csv", index=False, float_format="%.6g")
    pooled.to_csv(out / "pooled.csv", index=False, float_format="%.6g")
    rel.to_csv(out / "reliability.csv", index=False, float_format="%.6g")
    pit_h.to_csv(out / "pit_hist.csv", index=False)
    ks = ks_summary(per_mix)
    ks.to_csv(out / "ks_summary.csv", index=False)
    timings["aggregate_s"] = round(time.perf_counter() - t0, 1)

    rr = checks.rising_rates(scores)
    rr.to_csv(out / "checks" / "rising_rates.csv", index=False, float_format="%.6g")
    rec = checks.recent_episode(scores)
    rec.to_csv(out / "checks" / "recent_2021_2023.csv", index=False, float_format="%.6g")
    hmm = checks.hmm_usd1926(pools, args.seed) if "USD1926" in pools else {}
    (out / "checks" / "hmm_usd1926.json").write_text(json.dumps(hmm, indent=2), encoding="utf-8")
    hb = checks.historical_bond_mdd(pools)
    hb.to_csv(out / "checks" / "historical_mdd_windows.csv", index=False, float_format="%.6g")
    mono, dups = pd.DataFrame(), {}
    if args.ref:
        ref = Path(args.ref)
        mono = checks.monotonicity_reference(ref / "table" / "scenarios.parquet")
        mono.to_csv(out / "checks" / "monotonicity_reference.csv", index=False)
        dups = checks.sensitivity_duplicates(ref)
        (out / "checks" / "sensitivity_duplicates.json").write_text(json.dumps(dups, indent=2), encoding="utf-8")

    write_tables(out, pooled, per_mix, rel, rr, rec, hmm, hb, mono, dups, la, fits, ks)
    timings["total_s"] = round(time.perf_counter() - t_start, 1)
    manifest = {
        "what": "validation walk-forward hors échantillon des scénarios (volet C)",
        "config": {k: v for k, v in asdict(cfg).items()},
        "n_boot_origins": args.n_boot,
        "data_sha256": inputs.data_sha256,
        "data_version": inputs.data_version,
        "input_files_sha256": inputs.files_sha256,
        "scenarios_package_sha": package_sha(),
        "validation_code_sha": validation_sha(),
        "ref_run": args.ref,
        "n_score_rows": int(len(scores)),
        "timings": timings,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "pools": {k: p.describe() | {"name": p.name} for k, p in pools.items()},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"output": str(out), "rows": len(scores), **timings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
