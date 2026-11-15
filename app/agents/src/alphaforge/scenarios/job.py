"""Job de précalcul des scénarios (local ou SageMaker Processing).

    python -m alphaforge.scenarios.job --config small --input <processed> --output <dossier>

``--config`` : chemin d'un YAML/JSON, ou nom d'une configuration livrée (``small``, ``full``). Sous SageMaker
Processing, les valeurs par défaut sont les montages standard ``/opt/ml/processing/input/data`` et
``/opt/ml/processing/output`` : aucun appel AWS (boto3) n'est fait dans le job.

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
import json
import os
import platform
import subprocess  # noqa: S404 - lecture facultative du SHA git, commande fixe
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from . import schema
from .data import FAMILY_SPECS, build_pool, load_inputs
from .engine import BASES, historical_reference, run_pool, simulate_metrics, to_rows
from .grid import enumerate_mixes
from .models import StationaryBootstrap, make_model, rng_for

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = "/opt/ml/processing/input/data"
DEFAULT_OUTPUT = "/opt/ml/processing/output"


# Modules du volet B (générateurs et job) : l'empreinte ne dépend pas des fichiers de l'outil (tool*.py).
_CODE_FILES = ("schema.py", "grid.py", "data.py", "bootstrap.py", "hmm.py", "models.py", "engine.py", "job.py")


def package_sha() -> str:
    """Empreinte (sha256, 12 caractères) des modules du job et des configurations livrées : disponible sans git."""
    h = hashlib.sha256()
    paths = (
        [PACKAGE_DIR / name for name in _CODE_FILES]
        + sorted((PACKAGE_DIR / "configs").glob("*.yaml"))
        + ([VALIDATION_FILE] if VALIDATION_FILE.exists() else [])
    )
    for path in paths:
        h.update(path.relative_to(PACKAGE_DIR).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:12]


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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_sha() -> str | None:
    try:
        out = subprocess.run(  # noqa: S603
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
    cfg = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    cfg["_source"] = str(path.name)
    return cfg


def _pools(cfg: dict[str, Any]) -> list[tuple[str, bool]]:
    out = []
    for family in cfg["families"]:
        if family not in FAMILY_SPECS:
            raise ValueError(f"famille inconnue {family}")
        out.append((family, False))
        if cfg.get("crypto", {}).get("enabled") and family in cfg["crypto"].get("families", []):
            out.append((family, True))
    return out


def _grid_for(cfg: dict[str, Any], pool) -> list[str]:
    key = "crypto" if pool.hypothese else "core"
    grid = cfg["grid"][key]
    ranges = grid.get(pool.family, grid.get("default"))
    anchors = cfg["grid"].get("anchors", {}).get(pool.family, [])
    if pool.hypothese:
        anchors = cfg["grid"].get("anchors_crypto", {}).get(pool.family, [])
    return enumerate_mixes(pool.blocks, ranges, anchors, max_mixes=int(cfg["grid"].get("max_mixes", 5000)))


def _sensitivity(cfg: dict[str, Any], pool, mixes: list[str], horizons: list[int], seed: int) -> list[dict]:
    sens = cfg.get("sensitivity", {})
    if not sens.get("enabled", False):
        return []
    targets = list(dict.fromkeys(m for m in sens.get("mixes", []) if m in mixes)) or mixes[:3]
    rows = []
    for L in sens.get("block_lengths", [1, 3, 6, 12, 24]):
        model = StationaryBootstrap(block_length=float(L))
        fitted = model.fit(pool, cfg.get("fitted_through"))
        vals = simulate_metrics(
            fitted, targets, horizons, int(sens.get("n_paths", 2000)), rng_for(seed, pool.name, "sens", int(L))
        )
        for basis in ("nominal",):
            for m_i, mid in enumerate(targets):
                for h_i, H in enumerate(horizons):
                    for k, metric in enumerate(schema.METRICS):
                        if metric not in sens.get("metrics", schema.METRICS):
                            continue
                        rows.append(
                            {
                                "family": pool.family,
                                "pool": pool.name,
                                "mean_block": L,
                                "mix_id": mid,
                                "horizon_years": H,
                                "basis": basis,
                                "metric": metric,
                                "value": float(vals[basis][k, h_i, m_i]),
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
    arrow_schema = pa.schema([(name, types[t]) for name, t in schema.COLUMNS])
    pq.write_table(pa.Table.from_pandas(table, schema=arrow_schema, preserve_index=False), path, compression="snappy")


def _runtime_outputs(table: pd.DataFrame, cfg: dict[str, Any], out_dir: Path, meta: dict[str, Any]) -> int:
    rt = cfg.get("runtime", {})
    sub = table
    if rt.get("models"):
        sub = sub[sub["model_id"].isin(rt["models"])]
    if rt.get("bases"):
        sub = sub[sub["basis"].isin(rt["bases"])]
    if rt.get("metrics"):
        sub = sub[sub["metric"].isin(rt["metrics"])]
    digits = int(rt.get("digits", 4))
    sub = sub.copy()
    for c in ("value", "ci_lo", "ci_hi"):
        sub[c] = sub[c].round(digits)
    out_dir.mkdir(parents=True, exist_ok=True)
    sub.to_csv(out_dir / "scenarios_runtime.csv", index=False)  # mêmes colonnes que la table (schema.COLUMNS)
    tables: dict[str, Any] = {}
    group_cols = ["model_id", "family", "hypothese"]
    for (model_id, family, hyp), g in sub.groupby(group_cols, sort=True):
        key = f"{model_id}|{family}{'+CRYPTO' if hyp else ''}"
        first = g.iloc[0]
        mixes: dict[str, Any] = {}
        for row in g.itertuples(index=False):
            cell = mixes.setdefault(row.mix_id, {}).setdefault(row.basis, {}).setdefault(str(row.horizon_years), {})
            cell[row.metric] = [_num(row.value), _num(row.ci_lo), _num(row.ci_hi)]
        tables[key] = {
            "model_id": model_id,
            "family": family,
            "currency": first["currency"],
            "hypothese": bool(hyp),
            "window_start": first["window_start"],
            "fitted_through": first["fitted_through"],
            "n_hist_months": int(first["n_hist_months"]),
            "n_paths": int(first["n_paths"]),
            "n_boot": int(first["n_boot"]),
            "seed": int(first["seed"]),
            "mixes": mixes,
        }
    doc = {
        **meta,
        "value_order": ["value", "ci_lo", "ci_hi"],
        "units": {
            "ret_ann_*": "rendement annualisé (fraction)",
            "wealth_p10": "richesse finale pour 1 placé (p10)",
            "mdd_*": "perte maximale depuis un sommet (fraction positive)",
            "cvar95_12m": "perte moyenne des 5 % pires années (fraction positive ; négatif = gain)",
            "p_*": "probabilité (0-1)",
        },
        "tables": tables,
    }
    (out_dir / "scenarios_runtime.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
    return len(sub)


def _num(x: float) -> float | None:
    return None if x != x else float(x)


def _model_params(cfg: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    """Paramètres du modèle ; une variante ``*_ca`` reprend ceux du modèle de base sauf mention explicite."""
    params = cfg.get("model_params", {})
    base = model_id[:-3] if model_id.endswith("_ca") else model_id
    return params.get(model_id) or params.get(base)


def _run_task(cfg: dict[str, Any], pool, mixes: list[str], model_id: str, csha: str):
    """Une tâche (pool, modèle) ; exécutable dans un processus séparé (graines dérivées du pool et du modèle)."""
    sim = cfg["simulation"]
    seed = int(cfg["seed"])
    horizons = [int(h) for h in cfg.get("horizons", schema.HORIZONS)]
    model = make_model(model_id, _model_params(cfg, model_id))
    res = run_pool(
        model,
        pool,
        mixes,
        horizons,
        seed=seed,
        n_paths=int(sim["n_paths"]),
        n_boot=int(sim["n_boot"]),
        n_paths_boot=int(sim["n_paths_boot"]),
        ci_level=float(sim.get("ci_level", 0.90)),
        mem_budget_mb=float(sim.get("mem_budget_mb", 512)),
    )
    key = f"{model_id}|{pool.name}"
    print(f"[scenarios] {key}: {len(mixes)} mélanges, {res.timings}", file=sys.stderr, flush=True)
    cols = to_rows(res, seed=seed, code_sha=csha, schema_version=schema.SCHEMA_VERSION)
    return key, cols, {**res.fit_info, "bootstrap": res.boot_info}, res.timings


def run(cfg: dict[str, Any], input_dir: str, output_dir: str, workers: int | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    cfg = copy.deepcopy(cfg)
    out = Path(output_dir)
    (out / "table").mkdir(parents=True, exist_ok=True)
    seed = int(cfg["seed"])
    horizons = [int(h) for h in cfg.get("horizons", schema.HORIZONS)]
    csha = code_sha()
    inputs = load_inputs(input_dir)
    timings: dict[str, Any] = {}
    all_cols: dict[str, list] = {k: [] for k in schema.COLUMN_NAMES}
    hist_rows: list[dict] = []
    sens_rows: list[dict] = []
    fits: dict[str, Any] = {}
    pools_meta: list[dict] = []

    pools = {}
    for family, crypto in _pools(cfg):
        pool = build_pool(inputs, family, crypto=crypto)
        if cfg.get("fitted_through"):
            pool = pool.truncate(cfg["fitted_through"])
        mixes = _grid_for(cfg, pool)
        pools[(family, crypto)] = (pool, mixes)
        pools_meta.append({**pool.describe(), "n_mixes": len(mixes)})
        hist_rows += historical_reference(pool, mixes, horizons)
        t0 = time.perf_counter()
        sens_rows += _sensitivity(cfg, pool, mixes, horizons, seed)
        timings[f"{pool.name}|sensitivity_s"] = round(time.perf_counter() - t0, 3)

    tasks = [(family, crypto, model_id) for (family, crypto) in pools for model_id in cfg["models"]]
    workers = max(1, min(int(workers or cfg.get("workers", 1)), len(tasks)))
    if workers == 1:
        results = [_run_task(cfg, pools[(f, c)][0], pools[(f, c)][1], m, csha) for f, c, m in tasks]
    else:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_run_task, cfg, pools[(f, c)][0], pools[(f, c)][1], m, csha) for f, c, m in tasks]
            results = [fut.result() for fut in futures]
    for key, cols, fit_info, task_timings in results:  # ordre des tâches : sortie déterministe
        fits[key] = fit_info
        timings[key] = task_timings
        for k in all_cols:
            all_cols[k] += cols[k]

    table = pd.DataFrame(all_cols, columns=list(schema.COLUMN_NAMES))
    errors = schema.validate_rows(table.head(0).to_dict("records")) if table.empty else _validate_df(table)
    if errors:
        raise ValueError("table invalide : " + "; ".join(errors[:10]))
    _write_parquet(table, out / "table" / "scenarios.parquet")
    meta = {
        "schema_version": schema.SCHEMA_VERSION,
        "data_sha256": inputs.data_sha256,
        "code_sha": csha,
        "generated_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metrics": list(schema.METRICS),
        "horizons": horizons,
        "bases": list(BASES),
        "disclaimer": "Simulation : modèle, pas prévision. Aucun conseil financier personnalisé.",
    }
    n_runtime = _runtime_outputs(table, cfg, out / "runtime", meta)
    pd.DataFrame(hist_rows).to_csv(out / "historical_reference.csv", index=False)
    pd.DataFrame(sens_rows).to_csv(out / "sensitivity_block_length.csv", index=False)
    (out / "fits.json").write_text(json.dumps(fits, ensure_ascii=False, indent=1, default=_json_default))
    outputs = {
        "table": "table/scenarios.parquet",
        "runtime_json": "runtime/scenarios_runtime.json",
        "runtime_csv": "runtime/scenarios_runtime.csv",
        "historical_reference": "historical_reference.csv",
        "sensitivity": "sensitivity_block_length.csv",
        "fits": "fits.json",
    }
    outputs_sha = {rel: _sha256(out / rel) for rel in outputs.values()}
    validation = _validation_texts()
    families: dict[str, Any] = {}
    for meta_pool in pools_meta:
        entry = families.setdefault(meta_pool["family"], {})
        entry["crypto_pool" if meta_pool["hypothese"] else "core_pool"] = meta_pool
        entry["currency"] = meta_pool["currency"]
    manifest = {
        **{k: meta[k] for k in ("schema_version", "data_sha256", "code_sha", "generated_utc")},
        "run_id": os.environ.get("ALPHAFORGE_RUN_ID") or None,
        "release": os.environ.get("ALPHAFORGE_RELEASE") or None,
        "package_sha": package_sha(),
        "git_sha": git_sha(),
        "starter_dir": os.environ.get("ALPHAFORGE_STARTER_DIR") or None,
        "seed": seed,
        "default_model": cfg.get("default_model", "sbb_ca"),
        "models": [_model_entry(m, validation) for m in cfg["models"]],
        "validated_horizons": VALIDATED_HORIZONS,
        "validation_note": VALIDATION_NOTE,
        "validation_source": validation.get("_source"),
        "families": families,
        "licence": (
            "Table dérivée de sources publiques (Ken French, FRED, OCDE, Banque du Canada, Shiller, datahub, Yahoo) : "
            "voir research/backtest/data/SOURCES.md ; données brutes non redistribuées."
        ),
        "disclaimer": meta["disclaimer"],
        "table": {
            "file": outputs["runtime_csv"],
            "format": "csv",
            "sha256": outputs_sha[outputs["runtime_csv"]],
        },
        "outputs_sha256": outputs_sha,
        "config": {k: v for k, v in cfg.items()},
        "input": {"dir": inputs.input_dir, "files_sha256": inputs.files_sha256, "data_version": inputs.data_version},
        "pools": pools_meta,
        "rows": {
            "table": len(table),
            "runtime": n_runtime,
            "historical_reference": len(hist_rows),
            "sensitivity": len(sens_rows),
        },
        "outputs": outputs,
        "timings": {**timings, "total_s": round(time.perf_counter() - started, 3)},
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=_json_default))
    return manifest


def _validate_df(table: pd.DataFrame) -> list[str]:
    errors = []
    dup = table.duplicated(["model_id", "family", "mix_id", "horizon_years", "basis", "metric"]).sum()
    if dup:
        errors.append(f"{dup} clés en double")
    if table["value"].isna().any():
        errors.append("valeurs NaN")
    prob = table["metric"].str.startswith("p_") | table["metric"].str.startswith("mdd_")
    if ((table.loc[prob, "value"] < 0) | (table.loc[prob, "value"] > 1)).any():
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


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m alphaforge.scenarios.job", description=__doc__.split("\n")[0])
    parser.add_argument("--config", default=os.environ.get("SCENARIOS_CONFIG", "small"))
    parser.add_argument("--input", default=os.environ.get("SCENARIOS_INPUT", DEFAULT_INPUT))
    parser.add_argument("--output", default=os.environ.get("SCENARIOS_OUTPUT", DEFAULT_OUTPUT))
    parser.add_argument("--seed", type=int, default=None, help="remplace la graine de la configuration")
    parser.add_argument("--workers", type=int, default=None, help="processus parallèles (une tâche = pool × modèle)")
    parser.add_argument("--fitted-through", default=None, help="YYYY-MM : n'utilise aucun mois postérieur")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    if args.seed is not None:
        cfg["seed"] = args.seed
    if args.fitted_through:
        cfg["fitted_through"] = args.fitted_through
    manifest = run(cfg, args.input, args.output, workers=args.workers)
    print(json.dumps({"rows": manifest["rows"], "total_s": manifest["timings"]["total_s"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
