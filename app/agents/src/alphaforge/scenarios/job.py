"""Job de précalcul des scénarios (local ou SageMaker Processing).

    python -m alphaforge.scenarios.job --config small --input <données longues> --output <dossier> [--run-id <id>]

``--input`` : le dossier des données longues reconstruites par ``alphaforge.finance.backtest.build_data``
(``ALPHAFORGE_BT_DATA``; sous SageMaker Processing, ``run.sh`` le passe). ``--config`` : chemin d'un YAML/JSON, ou
nom d'une configuration livrée (``small``, ``full``). Sortie par défaut : ``/opt/ml/processing/output``. Aucun appel
AWS (boto3) n'est fait dans le job.

``run_id`` du manifeste : ``--run-id``, sinon ``ALPHAFORGE_RUN_ID`` (posé par Step Functions), sinon le nom du
dossier de sortie. Il doit être le nom du dossier ``scenarios/output/<run_id>/`` où la sortie est publiée : l'outil
refuse un manifeste dont le ``run_id`` diffère. Un ``run_id`` illisible fait échouer le job avant le calcul.

Sorties (dans ``--output``) :

- ``table/scenarios.parquet`` : table longue complète (schéma v0.2, pour Athena) ;
- ``runtime/scenarios_runtime.json`` et ``runtime/scenarios_runtime.csv`` : sous-ensemble compact pour l'outil ;
- ``historical_reference.csv`` : repères historiques (2022 seul, pire 12 mois…), non simulés ;
- ``sensitivity_block_length.csv`` : sensibilité du bootstrap stationnaire à la longueur moyenne de bloc ;
- ``fits.json`` : détails des ajustements (longueurs de bloc, BIC, matrices de transition…) ;
- ``manifest.json`` : configuration, graine, ``data_sha256``, ``code_sha``, nombre de lignes, durées.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import os
import platform
import re
import subprocess  # lecture facultative du SHA git, commande fixe
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from . import schema
from .data import FAMILY_SPECS, Inputs, Pool, build_pool, load_inputs, sha256_file
from .engine import BASES, SimulationConfig, historical_reference, run_pool, simulate_metrics, to_rows
from .grid import enumerate_mixes
from .models import StationaryBootstrap, make_model, rng_for

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = "/opt/ml/processing/input/data"
DEFAULT_OUTPUT = "/opt/ml/processing/output"
# Même motif que l'outil (tool_table.RUN_ID_PATTERN) : une clé S3 et un nom de dossier sûrs.
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# Modules du volet B (générateurs et job) : l'empreinte ne dépend pas des fichiers de l'outil (tool*.py).
_CODE_FILES = ("schema.py", "grid.py", "data.py", "bootstrap.py", "hmm.py", "models.py", "engine.py", "job.py")


def package_sha() -> str:
    """Empreinte (sha256, 12 caractères) des modules du job et des configurations livrées : disponible sans git."""
    digest = hashlib.sha256()
    paths = (
        [PACKAGE_DIR / name for name in _CODE_FILES]
        + sorted((PACKAGE_DIR / "configs").glob("*.yaml"))
        + ([VALIDATION_FILE] if VALIDATION_FILE.exists() else [])
    )
    for path in paths:
        digest.update(path.relative_to(PACKAGE_DIR).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def code_sha() -> str:
    """``ALPHAFORGE_RELEASE`` (SHA court du commit, posé par l'infrastructure) s'il est défini et différent de
    ``dev`` ; sinon l'empreinte des modules (``package_sha``)."""
    release = os.environ.get("ALPHAFORGE_RELEASE", "").strip()
    return release if release and release != "dev" else package_sha()


# Résumés hors échantillon du volet C (analyse/scenarios-validation/VALIDATION.md), versionnés avec le code.
VALIDATION_FILE = PACKAGE_DIR / "validation" / "models_validation.json"
# Affichage conseillé par le volet C : default (un seul), compare, sensitivity_only, hidden.
DISPLAY = {
    "sbb_ca": "default",
    "sbb": "compare",
    "hmm_rs": "sensitivity_only",
    "hmm_rs_ca": "sensitivity_only",
    "hmm_rs_fl": "sensitivity_only",
    "iid": "hidden",
    "iid_ca": "hidden",
}
VALIDATED_HORIZONS = [1, 3, 5, 10]
VALIDATION_NOTE = "5 et 10 ans : mise en garde forte ; 15–30 ans, base réelle, or et crypto : non validés"
DISCLAIMER = "Simulation : modèle, pas prévision. Aucun conseil financier personnalisé."
LICENCE = (
    "Table dérivée de sources publiques (Ken French, FRED, OCDE, Banque du Canada, Shiller, datahub, Yahoo) : "
    "voir alphaforge/data/long/SOURCES.md ; données brutes non redistribuées."
)
# Sorties du job (chemins relatifs à --output), listées dans le manifeste avec leur sha256.
OUTPUT_FILES = {
    "table": "table/scenarios.parquet",
    "runtime_json": "runtime/scenarios_runtime.json",
    "runtime_csv": "runtime/scenarios_runtime.csv",
    "historical_reference": "historical_reference.csv",
    "sensitivity": "sensitivity_block_length.csv",
    "fits": "fits.json",
}


def _validation_texts() -> dict[str, str]:
    if not VALIDATION_FILE.exists():
        return {}
    return json.loads(VALIDATION_FILE.read_text(encoding="utf-8"))


MODEL_DESCRIPTIONS = {
    "sbb": "bootstrap stationnaire par blocs (Politis-Romano), mois historiques tirés ensemble",
    "iid": "tirages mensuels indépendants (référence naïve, sans dépendance temporelle)",
    "hmm_rs": "régimes cachés (HMM gaussien, K par BIC) puis rééchantillonnage des mois historiques par régime",
}


def _model_entry(model_id: str, validation: dict[str, str]) -> dict[str, Any]:
    base = model_id[:-3] if model_id.endswith("_ca") else model_id
    base = "hmm_rs" if base == "hmm_rs_fl" else base
    name = MODEL_DESCRIPTIONS.get(base, model_id)
    if model_id.startswith("hmm_rs_fl"):
        name += ", départ dans le régime filtré du dernier mois"
    assumptions = [
        "stationnarité : la distribution des mois de la fenêtre historique est celle des mois futurs",
        "rebalancement mensuel vers les poids cibles, sans frais, impôts ni flux",
    ]
    if model_id.endswith("_ca"):
        name += ", niveau des taux ancré sur les 12 derniers mois de la fenêtre"
        assumptions.append("le cash et l'inflation restent en moyenne à leur niveau des 12 derniers mois")
    # validation : résumé hors échantillon du volet C (None si le modèle n'y figure pas)
    return {
        "model_id": model_id,
        "name": name,
        "assumptions": assumptions,
        "validation": validation.get(model_id),
        "display": DISPLAY.get(model_id, "hidden"),
    }


def git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],  # noqa: S607
            cwd=PACKAGE_DIR,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def load_config(value: str) -> dict[str, Any]:
    path = Path(value)
    if not path.exists():
        path = PACKAGE_DIR / "configs" / f"{value}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"configuration introuvable : {value}")
    text = path.read_text(encoding="utf-8")
    config = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    config["_source"] = str(path.name)
    return config


def _pools(config: dict[str, Any]) -> list[tuple[str, bool]]:
    out = []
    for family in config["families"]:
        if family not in FAMILY_SPECS:
            raise ValueError(f"famille inconnue {family}")
        out.append((family, False))
        if config.get("crypto", {}).get("enabled") and family in config["crypto"].get("families", []):
            out.append((family, True))
    return out


def _grid_for(config: dict[str, Any], pool) -> list[str]:
    key = "crypto" if pool.hypothese else "core"
    grid = config["grid"][key]
    ranges = grid.get(pool.family, grid.get("default"))
    anchors = config["grid"].get("anchors", {}).get(pool.family, [])
    if pool.hypothese:
        anchors = config["grid"].get("anchors_crypto", {}).get(pool.family, [])
    return enumerate_mixes(pool.blocks, ranges, anchors, max_mixes=int(config["grid"].get("max_mixes", 5000)))


def _sensitivity(config: dict[str, Any], pool, mixes: list[str], horizons: list[int], seed: int) -> list[dict]:
    sensitivity = config.get("sensitivity", {})
    if not sensitivity.get("enabled", False):
        return []
    targets = list(dict.fromkeys(mix for mix in sensitivity.get("mixes", []) if mix in mixes)) or mixes[:3]
    rows = []
    for block_length in sensitivity.get("block_lengths", [1, 3, 6, 12, 24]):
        fitted = StationaryBootstrap(block_length=float(block_length)).fit(pool, config.get("fitted_through"))
        n_paths = int(sensitivity.get("n_paths", 2000))
        values = simulate_metrics(
            fitted, targets, horizons, n_paths, rng_for(seed, pool.name, "sens", int(block_length))
        )
        cells = itertools.product(("nominal",), enumerate(targets), enumerate(horizons), enumerate(schema.METRICS))
        for basis, (m_i, mix), (h_i, horizon), (k, metric) in cells:
            if metric not in sensitivity.get("metrics", schema.METRICS):
                continue
            rows.append(
                {
                    "family": pool.family,
                    "pool": pool.name,
                    "mean_block": block_length,
                    "mix_id": mix,
                    "horizon_years": horizon,
                    "basis": basis,
                    "metric": metric,
                    "value": float(values[basis][k, h_i, m_i]),
                }
            )
    return rows


def _write_parquet(table: pd.DataFrame, path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    types = {
        "string": pa.string(),
        "int32": pa.int32(),
        "int64": pa.int64(),
        "float64": pa.float64(),
        "bool": pa.bool_(),
    }
    arrow_schema = pa.schema([(name, types[type_name]) for name, type_name in schema.COLUMNS])
    pq.write_table(pa.Table.from_pandas(table, schema=arrow_schema, preserve_index=False), path, compression="snappy")


RUNTIME_UNITS = {
    "ret_ann_*": "rendement annualisé (fraction)",
    "wealth_p10": "richesse finale pour 1 placé (p10)",
    "mdd_*": "perte maximale depuis un sommet (fraction positive)",
    "cvar95_12m": "perte moyenne des 5 % pires années (fraction positive ; négatif = gain)",
    "p_*": "probabilité (0-1)",
}


def _runtime_subset(table: pd.DataFrame, runtime: dict[str, Any]) -> pd.DataFrame:
    """Lignes retenues pour l'outil (modèles, bases, métriques), valeurs arrondies à ``digits`` décimales."""
    subset = table
    if runtime.get("models"):
        subset = subset[subset["model_id"].isin(runtime["models"])]
    if runtime.get("bases"):
        subset = subset[subset["basis"].isin(runtime["bases"])]
    if runtime.get("metrics"):
        subset = subset[subset["metric"].isin(runtime["metrics"])]
    digits = int(runtime.get("digits", 4))
    subset = subset.copy()
    for column in ("value", "ci_lo", "ci_hi"):
        subset[column] = subset[column].round(digits)
    return subset


def _runtime_mixes(group: pd.DataFrame) -> dict[str, Any]:
    """``{mix_id: {basis: {horizon: {metric: [value, ci_lo, ci_hi]}}}}``, NaN écrit ``null``."""
    mixes: dict[str, Any] = {}
    for row in group.itertuples(index=False):
        cell = mixes.setdefault(row.mix_id, {}).setdefault(row.basis, {}).setdefault(str(row.horizon_years), {})
        cell[row.metric] = [_num(row.value), _num(row.ci_lo), _num(row.ci_hi)]
    return mixes


def _runtime_tables(subset: pd.DataFrame) -> dict[str, Any]:
    """Une entrée par (modèle, famille, pool crypto), sous la clé ``model_id|famille`` (suffixe ``+CRYPTO``)."""
    tables: dict[str, Any] = {}
    for (model_id, family, hypothese), group in subset.groupby(["model_id", "family", "hypothese"], sort=True):
        key = f"{model_id}|{family}{'+CRYPTO' if hypothese else ''}"
        first = group.iloc[0]
        tables[key] = {
            "model_id": model_id,
            "family": family,
            "currency": first["currency"],
            "hypothese": bool(hypothese),
            "window_start": first["window_start"],
            "fitted_through": first["fitted_through"],
            "n_hist_months": int(first["n_hist_months"]),
            "n_paths": int(first["n_paths"]),
            "n_boot": int(first["n_boot"]),
            "seed": int(first["seed"]),
            "mixes": _runtime_mixes(group),
        }
    return tables


def _runtime_outputs(table: pd.DataFrame, config: dict[str, Any], out_dir: Path, meta: dict[str, Any]) -> int:
    subset = _runtime_subset(table, config.get("runtime", {}))
    out_dir.mkdir(parents=True, exist_ok=True)
    subset.to_csv(out_dir / "scenarios_runtime.csv", index=False)  # mêmes colonnes que la table (schema.COLUMNS)
    doc = {
        **meta,
        "value_order": ["value", "ci_lo", "ci_hi"],
        "units": RUNTIME_UNITS,
        "tables": _runtime_tables(subset),
    }
    (out_dir / "scenarios_runtime.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    return len(subset)


def _num(x: float) -> float | None:
    return None if x != x else float(x)


def _horizons(config: dict[str, Any]) -> list[int]:
    return [int(horizon) for horizon in config.get("horizons", schema.HORIZONS)]


def _model_params(config: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    """Paramètres du modèle ; une variante ``*_ca`` reprend ceux du modèle de base sauf mention explicite."""
    params = config.get("model_params", {})
    base = model_id[:-3] if model_id.endswith("_ca") else model_id
    return params.get(model_id) or params.get(base)


def _run_task(config: dict[str, Any], pool, mixes: list[str], model_id: str, code_sha_value: str):
    """Une tâche (pool, modèle) ; exécutable dans un processus séparé (graines dérivées du pool et du modèle)."""
    simulation = config["simulation"]
    seed = int(config["seed"])
    horizons = _horizons(config)
    model = make_model(model_id, _model_params(config, model_id))
    settings = SimulationConfig(
        seed=seed,
        n_paths=int(simulation["n_paths"]),
        n_boot=int(simulation["n_boot"]),
        n_paths_boot=int(simulation["n_paths_boot"]),
        ci_level=float(simulation.get("ci_level", 0.90)),
        mem_budget_mb=float(simulation.get("mem_budget_mb", 512)),
    )
    result = run_pool(model, pool, mixes, horizons, settings)
    key = f"{model_id}|{pool.name}"
    print(f"[scenarios] {key}: {len(mixes)} mélanges, {result.timings}", file=sys.stderr, flush=True)
    columns = to_rows(result, seed=seed, code_sha=code_sha_value, schema_version=schema.SCHEMA_VERSION)
    return key, columns, {**result.fit_info, "bootstrap": result.boot_info}, result.timings


def resolve_run_id(run_id: str | None, output_dir: str) -> str:
    """``run_id`` explicite, sinon ``ALPHAFORGE_RUN_ID``, sinon le nom du dossier de sortie (essai local)."""
    value = run_id or os.environ.get("ALPHAFORGE_RUN_ID") or Path(output_dir).resolve().name
    if not RUN_ID_PATTERN.match(value):
        raise ValueError(f"run_id invalide {value!r} : passer --run-id (motif {RUN_ID_PATTERN.pattern})")
    return value


def _validate_df(table: pd.DataFrame) -> list[str]:
    errors = []
    duplicates = table.duplicated(["model_id", "family", "mix_id", "horizon_years", "basis", "metric"]).sum()
    if duplicates:
        errors.append(f"{duplicates} clés en double")
    if table["value"].isna().any():
        errors.append("valeurs NaN")
    bounded = table["metric"].str.startswith("p_") | table["metric"].str.startswith("mdd_")
    if ((table.loc[bounded, "value"] < 0) | (table.loc[bounded, "value"] > 1)).any():
        errors.append("probabilité ou perte maximale hors [0, 1]")
    if (table["ci_lo"] > table["ci_hi"] + 1e-12).any():
        errors.append("ci_lo > ci_hi")
    unknown = set(table["metric"]) - set(schema.METRICS)
    if unknown:
        errors.append(f"métriques inconnues {sorted(unknown)}")
    # contrôle complet ligne à ligne sur un échantillon (mix_id, familles, bases)
    sample = table.sample(min(len(table), 2000), random_state=0).to_dict("records")
    errors += schema.validate_rows(sample)
    return errors


def _check_table(table: pd.DataFrame) -> None:
    errors = schema.validate_rows(table.head(0).to_dict("records")) if table.empty else _validate_df(table)
    if errors:
        raise ValueError("table invalide : " + "; ".join(errors[:10]))


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def _families(pools_meta: list[dict]) -> dict[str, Any]:
    """Pools de chaque famille (``core_pool``, ``crypto_pool``) et sa devise."""
    families: dict[str, Any] = {}
    for meta_pool in pools_meta:
        entry = families.setdefault(meta_pool["family"], {})
        entry["crypto_pool" if meta_pool["hypothese"] else "core_pool"] = meta_pool
        entry["currency"] = meta_pool["currency"]
    return families


@dataclass
class _JobRun:
    """Une exécution du job : configuration et entrées, plus ce qui s'accumule avant l'écriture des sorties."""

    config: dict[str, Any]
    out: Path
    run_id: str
    started: float
    seed: int
    horizons: list[int]
    code_sha: str
    inputs: Inputs
    timings: dict[str, Any] = field(default_factory=dict)
    pools_meta: list[dict] = field(default_factory=list)
    historical_rows: list[dict] = field(default_factory=list)
    sensitivity_rows: list[dict] = field(default_factory=list)
    fits: dict[str, Any] = field(default_factory=dict)
    columns: dict[str, list] = field(default_factory=lambda: {name: [] for name in schema.COLUMN_NAMES})

    def prepare_pools(self) -> dict[tuple[str, bool], tuple[Pool, list[str]]]:
        """Pools et grilles de mélanges ; repères historiques et sensibilité calculés au passage, pool par pool."""
        pools = {}
        for family, crypto in _pools(self.config):
            pool = build_pool(self.inputs, family, crypto=crypto)
            if self.config.get("fitted_through"):
                pool = pool.truncate(self.config["fitted_through"])
            mixes = _grid_for(self.config, pool)
            pools[(family, crypto)] = (pool, mixes)
            self.pools_meta.append({**pool.describe(), "n_mixes": len(mixes)})
            self.historical_rows += historical_reference(pool, mixes, self.horizons)
            started = time.perf_counter()
            self.sensitivity_rows += _sensitivity(self.config, pool, mixes, self.horizons, self.seed)
            self.timings[f"{pool.name}|sensitivity_s"] = round(time.perf_counter() - started, 3)
        return pools

    def run_tasks(self, pools: dict[tuple[str, bool], tuple[Pool, list[str]]], workers: int | None) -> list[tuple]:
        """Une tâche par (pool, modèle), dans un ordre fixe ; en parallèle si plus d'un processus est demandé."""
        tasks = [(family, crypto, model_id) for (family, crypto) in pools for model_id in self.config["models"]]
        workers = max(1, min(int(workers or self.config.get("workers", 1)), len(tasks)))
        if workers == 1:
            return [
                _run_task(self.config, *pools[(family, crypto)], model_id, self.code_sha)
                for family, crypto, model_id in tasks
            ]
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_run_task, self.config, *pools[(family, crypto)], model_id, self.code_sha)
                for family, crypto, model_id in tasks
            ]
            return [future.result() for future in futures]

    def add_task_results(self, results: list[tuple]) -> None:
        for key, columns, fit_info, task_timings in results:  # ordre des tâches : sortie déterministe
            self.fits[key] = fit_info
            self.timings[key] = task_timings
            for name in self.columns:
                self.columns[name] += columns[name]

    def table_meta(self) -> dict[str, Any]:
        """En-tête commun du JSON compact et du manifeste (``generated_utc`` : heure de l'appel)."""
        return {
            "schema_version": schema.SCHEMA_VERSION,
            "data_sha256": self.inputs.data_sha256,
            "code_sha": self.code_sha,
            "generated_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
            "metrics": list(schema.METRICS),
            "horizons": self.horizons,
            "bases": list(BASES),
            "disclaimer": DISCLAIMER,
        }

    def write_diagnostics(self) -> None:
        """Repères historiques, sensibilité à la longueur de bloc et détails des ajustements."""
        pd.DataFrame(self.historical_rows).to_csv(self.out / "historical_reference.csv", index=False)
        pd.DataFrame(self.sensitivity_rows).to_csv(self.out / "sensitivity_block_length.csv", index=False)
        (self.out / "fits.json").write_text(json.dumps(self.fits, ensure_ascii=False, indent=1, default=_json_default))

    def manifest(self, meta: dict[str, Any], rows: dict[str, int]) -> dict[str, Any]:
        """Manifeste du run ; à construire après l'écriture des sorties, dont il donne les sha256."""
        outputs_sha = {rel: sha256_file(self.out / rel) for rel in OUTPUT_FILES.values()}
        validation = _validation_texts()
        return {
            **{k: meta[k] for k in ("schema_version", "data_sha256", "code_sha", "generated_utc")},
            "run_id": self.run_id,
            "release": os.environ.get("ALPHAFORGE_RELEASE") or None,
            "package_sha": package_sha(),
            "git_sha": git_sha(),
            "starter_dir": os.environ.get("ALPHAFORGE_STARTER_DIR") or None,
            "seed": self.seed,
            "default_model": self.config.get("default_model", "sbb_ca"),
            "models": [_model_entry(model_id, validation) for model_id in self.config["models"]],
            "validated_horizons": VALIDATED_HORIZONS,
            "validation_note": VALIDATION_NOTE,
            "validation_source": validation.get("_source"),
            "families": _families(self.pools_meta),
            "licence": LICENCE,
            "disclaimer": meta["disclaimer"],
            "table": {
                "file": OUTPUT_FILES["runtime_csv"],
                "format": "csv",
                "sha256": outputs_sha[OUTPUT_FILES["runtime_csv"]],
            },
            "outputs_sha256": outputs_sha,
            "config": dict(self.config),
            "input": {
                "dir": self.inputs.input_dir,
                "files_sha256": self.inputs.files_sha256,
                "data_version": self.inputs.data_version,
            },
            "pools": self.pools_meta,
            "rows": rows,
            "outputs": dict(OUTPUT_FILES),
            "timings": {**self.timings, "total_s": round(time.perf_counter() - self.started, 3)},
            "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
        }


def run(
    config: dict[str, Any], input_dir: str, output_dir: str, workers: int | None = None, run_id: str | None = None
) -> dict[str, Any]:
    """Exécute le job et écrit ses sorties dans ``output_dir`` ; renvoie le manifeste (écrit aussi en JSON)."""
    started = time.perf_counter()
    config = copy.deepcopy(config)
    run_id = resolve_run_id(run_id, output_dir)
    out = Path(output_dir)
    (out / "table").mkdir(parents=True, exist_ok=True)
    job_run = _JobRun(
        config=config,
        out=out,
        run_id=run_id,
        started=started,
        seed=int(config["seed"]),
        horizons=_horizons(config),
        code_sha=code_sha(),
        inputs=load_inputs(input_dir),
    )
    pools = job_run.prepare_pools()
    job_run.add_task_results(job_run.run_tasks(pools, workers))
    table = pd.DataFrame(job_run.columns, columns=list(schema.COLUMN_NAMES))
    _check_table(table)
    _write_parquet(table, out / "table" / "scenarios.parquet")
    meta = job_run.table_meta()
    n_runtime = _runtime_outputs(table, config, out / "runtime", meta)
    job_run.write_diagnostics()
    rows = {
        "table": len(table),
        "runtime": n_runtime,
        "historical_reference": len(job_run.historical_rows),
        "sensitivity": len(job_run.sensitivity_rows),
    }
    manifest = job_run.manifest(meta, rows)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=_json_default))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m alphaforge.scenarios.job", description=__doc__.split("\n")[0])
    parser.add_argument("--config", default=os.environ.get("SCENARIOS_CONFIG", "small"))
    parser.add_argument("--input", default=os.environ.get("SCENARIOS_INPUT", DEFAULT_INPUT))
    parser.add_argument("--output", default=os.environ.get("SCENARIOS_OUTPUT", DEFAULT_OUTPUT))
    parser.add_argument("--seed", type=int, default=None, help="remplace la graine de la configuration")
    parser.add_argument("--workers", type=int, default=None, help="processus parallèles (une tâche = pool × modèle)")
    parser.add_argument("--fitted-through", default=None, help="YYYY-MM : n'utilise aucun mois postérieur")
    parser.add_argument(
        "--run-id", default=None, help="run_id du manifeste (défaut : ALPHAFORGE_RUN_ID, sinon le nom de --output)"
    )
    args = parser.parse_args(argv)
    try:
        run_id = resolve_run_id(args.run_id, args.output)
    except ValueError as exc:
        parser.error(str(exc))
    config = load_config(args.config)
    if args.seed is not None:
        config["seed"] = args.seed
    if args.fitted_through:
        config["fitted_through"] = args.fitted_through
    manifest = run(config, args.input, args.output, workers=args.workers, run_id=run_id)
    print(json.dumps({"rows": manifest["rows"], "total_s": manifest["timings"]["total_s"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
