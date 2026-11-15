"""Lecture seule de la table de scénarios précalculée, sans dépendance lourde (outil ``scenario_risk``).

Le runtime AgentCore n'installe ni numpy, ni pandas, ni pyarrow : ce module n'utilise que la bibliothèque
standard (``json``, ``csv``, ``hashlib``, ``gzip``) et ``schema.py`` du volet modèles (lui aussi sans dépendance
lourde). La table est produite par le volet B/D (job SageMaker ou calcul local) et publiée dans le magasin du
projet (``store/``, dossier local en développement, bucket S3 en AWS) :

```
scenarios/latest.json                     pointeur (Step Functions) : {"run_id": "<run_id>", ...}
scenarios/output/<run_id>/manifest.json   manifeste du job : schema_version, data_sha256, code_sha (= release),
                                          table = {"file": "runtime/scenarios_runtime.csv", "format": "csv"}
scenarios/output/<run_id>/runtime/        sortie compacte lue par l'outil (CSV, ou JSON du job)
scenarios/output/<run_id>/table/          scenarios.parquet, réservé à Athena (jamais lu ici : pas de pyarrow)
```

Le chemin de la table vient **toujours** du manifeste (``manifest["table"]``); repli signalé sur
``manifest["outputs"]["runtime_csv" | "runtime_json"]`` s'il manque; sinon erreur claire (aucun chemin par défaut).

Contrôles d'intégrité (refus si l'un échoue, jamais de lecture partielle silencieuse) :
- ``schema_version`` lisible (0.1 ou 0.2); ``code_sha`` et ``data_sha256`` de chaque ligne (CSV) ou du document
  (JSON) égaux à ceux du manifeste. Si le CSV n'a pas les colonnes de provenance, elles sont prises au manifeste
  et ``warnings`` le dit;
- sha256 du fichier déclaré par ``manifest["table"]["sha256"]`` (ou ``manifest["outputs_sha256"][<chemin>]``) et
  égal à celui du fichier lu. Non déclaré : refus (aucune table non vérifiée n'est lue);
- run figé (``ScenarioTableLoader(run_id=...)``) : ``scenarios/output/<run_id>/_done.json`` doit exister avec
  ``status = "ok"`` (marqueur de Step Functions), comme pour un run désigné par ``latest.json``, qui n'est écrit
  qu'après ce marqueur;
- nombres lisibles et finis, ci_lo <= ci_hi. Une valeur absente (NaN du job, JSON) retire la métrique, signalé;
  un IC qui n'encadre pas la valeur est gardé tel quel et compté dans ``integrity["ci_not_enclosing"]``
  (l'IC vient du bootstrap des paramètres, la valeur de l'ajustement complet : rien ne garantit l'inclusion).

Compatibilité : schéma 0.1 (sans ``basis`` : la ligne vaut ``nominal``) et 0.2 (``basis`` ∈ nominal, real).

Unités attendues (contrat avec le volet B) : probabilités, rendements et pertes en **fraction**
(0.12 = 12 %); ``wealth_p10`` en **multiple du capital initial**; ``p_loss_gt_20`` = P(perte cumulée à
l'horizon > 20 %).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any

from ..store import Store
from . import schema

SUPPORTED_SCHEMAS = ("0.1", "0.2")
LATEST_KEY = "scenarios/latest.json"
OUTPUT_PREFIX = "scenarios/output/"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Colonnes indispensables à l'outil; les autres colonnes du schéma 0.2 sont lues si présentes.
REQUIRED_COLUMNS = (
    "model_id",
    "family",
    "mix_id",
    "horizon_years",
    "metric",
    "value",
    "ci_lo",
    "ci_hi",
)
# Provenance par ligne (schéma 0.2) : lue si présente, sinon prise au niveau du manifeste et signalée.
PROVENANCE_COLUMNS = ("n_paths", "seed", "fitted_through", "data_sha256", "code_sha")
MANIFEST_KEYS = ("schema_version", "code_sha", "data_sha256")
DISPLAYS = ("default", "compare", "sensitivity_only", "hidden")
# Horizons validés hors échantillon par le volet C (2026-11-14), si le manifeste ne les déclare pas.
VALIDATED_HORIZONS_FALLBACK = (1, 3, 5, 10)
VALIDATED_BASES = ("nominal",)
# Horizons validés mais dont la calibration se dégrade (volet C) : mise en garde forte.
DEGRADED_HORIZONS = (5, 10)
_REL_PATH = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*(/[A-Za-z0-9_-][A-Za-z0-9._-]*)*$")
# Noms lisibles des modèles du job (configs/*.yaml), utilisés si le manifeste n'en donne pas.
MODEL_NAMES_FR = {
    "sbb": "bootstrap stationnaire par blocs",
    "iid": "tirages mensuels indépendants",
    "hmm_rs": "régimes cachés (HMM) avec rééchantillonnage par régime",
}
BLOCKS = schema.BLOCKS
SHORT_HISTORY_BLOCKS = frozenset({"CRYPTO"})  # historique 2014+ : chiffres HYPOTHESE
# Blocs absents des mélanges testés hors échantillon (VALIDATION.md, « or et crypto non testés ») : un mélange qui
# en contient n'est jamais « validé ».
UNVALIDATED_BLOCKS = ("GOLD", "CRYPTO")
_PLOSS = re.compile(r"^p_loss_gt_(\d{2})$")
_PMDD = re.compile(r"^p_mdd_gt_(\d{2})$")
_FLOAT_TOL = 1e-9

Key = tuple[str, str, str, int, str, str]  # model_id, family, mix_id, horizon_years, basis, metric


class ScenarioTableError(Exception):
    """Table absente, illisible ou dont l'intégrité n'est pas vérifiée."""


def parse_mix_id(mix_id: str) -> dict[str, float]:
    try:
        return schema.parse_mix_id(str(mix_id))
    except ValueError as exc:
        raise ScenarioTableError(str(exc)) from exc


def loss_level(metric: str) -> int | None:
    """Seuil (points de %) d'une métrique ``p_loss_gt_XX``; None sinon."""
    match = _PLOSS.match(metric)
    return int(match.group(1)) if match else None


def mdd_level(metric: str) -> int | None:
    match = _PMDD.match(metric)
    return int(match.group(1)) if match else None


def sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class Row:
    model_id: str
    family: str
    mix_id: str
    horizon_years: int
    basis: str
    metric: str
    value: float
    ci_lo: float
    ci_hi: float
    n_paths: int | None
    seed: int | None
    fitted_through: str
    data_sha256: str
    code_sha: str
    currency: str | None = None
    window_start: str | None = None
    n_boot: int | None = None
    hypothese: bool = False


@dataclass
class ScenarioTable:
    """Table chargée et vérifiée, indexée pour la recherche (aucun calcul de modèle ici)."""

    run_id: str
    manifest: dict[str, Any]
    table_key: str
    table_sha256: str
    rows: dict[Key, Row] = field(default_factory=dict)
    integrity: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def code_sha(self) -> str:
        return str(self.manifest["code_sha"])

    def data_sha256(self, family: str) -> str:
        declared = self.manifest["data_sha256"]
        if isinstance(declared, dict):
            return str(declared.get(family, ""))
        return str(declared)

    @property
    def models(self) -> list[str]:
        """Modèles présents, dans l'ordre du manifeste s'il en donne un."""
        found = sorted({key[0] for key in self.rows})
        config = self.manifest.get("config") if isinstance(self.manifest.get("config"), dict) else {}
        runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
        listed = self.manifest.get("models") or runtime.get("models") or config.get("models") or []
        declared = [m.get("model_id") if isinstance(m, dict) else str(m) for m in listed]
        return [m for m in declared if m in found] + [m for m in found if m not in declared]

    def _declared_display(self) -> dict[str, str]:
        out = {}
        for entry in self.manifest.get("models") or []:
            if isinstance(entry, dict) and entry.get("display") in DISPLAYS:
                out[str(entry.get("model_id"))] = entry["display"]
        return out

    def display(self, model_id: str) -> str:
        """Rôle d'affichage : ``manifest.models[].display`` (default, compare, sensitivity_only, hidden).

        Repli si aucun modèle ne déclare ``display`` : ``sbb_ca`` est ``default`` s'il existe, sinon
        ``manifest.default_model`` (puis le premier modèle); ``iid*`` est ``hidden``, ``hmm*`` est
        ``sensitivity_only``, les autres ``compare``. Un modèle absent de la liste déclarée est ``hidden``.
        """
        declared = self._declared_display()
        if declared:
            return declared.get(model_id, "hidden")
        models = self.models
        wanted = self.manifest.get("default_model")
        fallback = "sbb_ca" if "sbb_ca" in models else (wanted if wanted in models else (models[0] if models else None))
        if model_id == fallback:
            return "default"
        if model_id.startswith("iid"):
            return "hidden"
        if model_id.startswith("hmm"):
            return "sensitivity_only"
        return "compare"

    @property
    def default_model(self) -> str | None:
        for model in self.models:
            if self.display(model) == "default":
                return model
        visible = [m for m in self.models if self.display(m) != "hidden"]
        return visible[0] if visible else None

    def validated_horizons(self, model_id: str) -> tuple[list[int], bool]:
        """(horizons validés hors échantillon, déclarés par le manifeste ?). Repli : VALIDATED_HORIZONS_FALLBACK."""
        info = self.model_info(model_id)
        for value in (info.get("validated_horizons"), self.manifest.get("validated_horizons")):
            if isinstance(value, list) and value:
                return sorted(int(h) for h in value), True
        return list(VALIDATED_HORIZONS_FALLBACK), False

    def model_info(self, model_id: str) -> dict[str, Any]:
        """Description du modèle par le manifeste (nom, hypothèses, validation hors échantillon); vide si absente."""
        for entry in self.manifest.get("models") or []:
            if isinstance(entry, dict) and entry.get("model_id") == model_id:
                return entry
        base = model_id[:-3] if model_id.endswith("_ca") else model_id
        if base in MODEL_NAMES_FR:
            suffix = ", taux ancrés sur les 12 derniers mois" if model_id.endswith("_ca") else ""
            return {"model_id": model_id, "name": MODEL_NAMES_FR[base] + suffix}
        return {}

    def family_info(self, family: str) -> dict[str, Any]:
        info = (self.manifest.get("families") or {}).get(family)
        return info if isinstance(info, dict) else {}

    def families(self) -> list[str]:
        return sorted({key[1] for key in self.rows})

    def mixes(self, model_id: str, family: str, basis: str) -> list[str]:
        return sorted({k[2] for k in self.rows if k[0] == model_id and k[1] == family and k[4] == basis})

    def horizons(self, model_id: str, family: str, mix_id: str, basis: str) -> list[int]:
        return sorted(
            {k[3] for k in self.rows if k[0] == model_id and k[1] == family and k[2] == mix_id and k[4] == basis}
        )

    def metrics(self, model_id: str, family: str, mix_id: str, horizon: int, basis: str) -> dict[str, Row]:
        prefix = (model_id, family, mix_id, horizon, basis)
        return {k[5]: row for k, row in self.rows.items() if k[:5] == prefix}

    def source(self) -> dict[str, Any]:
        """Provenance au format ``Source`` de ``alphaforge.finance.contracts.decision``."""
        return {
            "dataset": f"scenarios:{self.run_id}",
            "url": None,
            "licence": self.manifest.get("licence"),
            "retrieved_utc": self.manifest.get("created_utc") or self.manifest.get("generated_utc"),
            "sha256": self.table_sha256,
            "processing": (
                f"table de scénarios précalculée (schéma {self.manifest.get('schema_version')}), "
                f"objet {self.table_key}, code {self.code_sha}"
            ),
        }


def _to_float(text: Any, what: str) -> float:
    try:
        value = float(text)
    except (TypeError, ValueError) as exc:
        raise ScenarioTableError(f"{what} illisible : {text!r}") from exc
    if value != value or value in (float("inf"), float("-inf")):
        raise ScenarioTableError(f"{what} non fini : {text!r}")
    return value


def _to_int(text: Any, what: str, *, optional: bool = False) -> int | None:
    if optional and (text is None or str(text).strip() == ""):
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError) as exc:
        raise ScenarioTableError(f"{what} illisible : {text!r}") from exc


def _to_bool(text: Any) -> bool:
    return str(text).strip().lower() in ("true", "1", "yes", "vrai")


def _opt(raw: dict[str, Any], name: str) -> str | None:
    value = (raw.get(name) or "").strip()
    return value or None


def _manifest_default(manifest: dict[str, Any], name: str) -> Any:
    """Valeur de repli au niveau du manifeste (``fitted_through``, ``n_paths``, ``seed``), sinon None."""
    if manifest.get(name) not in (None, ""):
        return manifest[name]
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    if name == "n_paths":
        sim = config.get("simulation") if isinstance(config.get("simulation"), dict) else {}
        return sim.get("n_paths")
    return config.get(name)


def parse_table(
    run_id: str, manifest: dict[str, Any], table_key: str, body: bytes, *, expected_sha256: str | None = None
) -> ScenarioTable:
    """Vérifie le manifeste et le fichier CSV, puis indexe les lignes. Fonction pure (testable sans magasin)."""
    missing = [k for k in MANIFEST_KEYS if k not in manifest]
    if missing:
        raise ScenarioTableError(f"manifeste incomplet : {missing}")
    version = ".".join(str(manifest["schema_version"]).split(".")[:2])
    if version not in SUPPORTED_SCHEMAS:
        raise ScenarioTableError(f"schéma {manifest['schema_version']!r} non pris en charge ({SUPPORTED_SCHEMAS})")
    if manifest.get("run_id", run_id) != run_id:
        raise ScenarioTableError(f"manifeste du run {manifest['run_id']!r}, attendu {run_id!r}")
    actual_sha = sha256_hex(body)
    if not expected_sha256:
        raise ScenarioTableError(f"sha256 de {table_key} non déclaré par le manifeste : table non vérifiable")
    if expected_sha256 != actual_sha:
        raise ScenarioTableError(f"sha256 de {table_key} ({actual_sha}) différent du manifeste ({expected_sha256})")

    table = ScenarioTable(run_id=run_id, manifest=manifest, table_key=table_key, table_sha256=actual_sha)
    table.integrity = {"format": "csv", "file_sha256_verified": True, "ci_not_enclosing": 0}
    text = (gzip.decompress(body) if table_key.endswith(".gz") else body).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    absent = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if absent:
        raise ScenarioTableError(f"colonnes absentes : {absent}")
    no_prov = [c for c in PROVENANCE_COLUMNS if c not in (reader.fieldnames or [])]
    table.integrity["row_provenance"] = not no_prov
    if no_prov:
        table.warnings.append(f"colonnes de provenance absentes du CSV, prises au manifeste : {no_prov}")
    fallback = {
        "n_paths": _manifest_default(manifest, "n_paths"),
        "seed": _manifest_default(manifest, "seed"),
        "fitted_through": _manifest_default(manifest, "fitted_through"),
        "data_sha256": None,
        "code_sha": str(manifest["code_sha"]),
    }
    for line, raw in enumerate(reader, start=2):
        for column in no_prov:
            value = fallback[column]
            if column == "data_sha256":
                value = table.data_sha256(raw["family"].strip())
            raw[column] = "" if value is None else str(value)
        where = f"ligne {line}"
        mix = raw["mix_id"].strip()
        weights = parse_mix_id(mix)
        row = Row(
            model_id=raw["model_id"].strip(),
            family=raw["family"].strip(),
            mix_id=mix,
            horizon_years=_to_int(raw["horizon_years"], f"{where} horizon_years"),
            basis=_opt(raw, "basis") or "nominal",
            metric=raw["metric"].strip(),
            value=_to_float(raw["value"], f"{where} value"),
            ci_lo=_to_float(raw["ci_lo"], f"{where} ci_lo"),
            ci_hi=_to_float(raw["ci_hi"], f"{where} ci_hi"),
            n_paths=_to_int(raw["n_paths"], f"{where} n_paths", optional=True),
            seed=_to_int(raw["seed"], f"{where} seed", optional=True),
            fitted_through=raw["fitted_through"].strip(),
            data_sha256=raw["data_sha256"].strip(),
            code_sha=raw["code_sha"].strip(),
            currency=_opt(raw, "currency"),
            window_start=_opt(raw, "window_start"),
            n_boot=_to_int(raw.get("n_boot"), f"{where} n_boot", optional=True),
            # Un mélange avec crypto est toujours HYPOTHESE, même si la colonne manque.
            hypothese=_to_bool(raw.get("hypothese")) or any(weights[b] > 0 for b in SHORT_HISTORY_BLOCKS),
        )
        if row.ci_lo > row.ci_hi + _FLOAT_TOL:
            raise ScenarioTableError(f"{where} : ci_lo > ci_hi")
        _count_enclosing(table, row)
        if row.code_sha != table.code_sha:
            raise ScenarioTableError(f"{where} : code_sha {row.code_sha} différent du manifeste {table.code_sha}")
        if row.data_sha256 != table.data_sha256(row.family):
            raise ScenarioTableError(f"{where} : data_sha256 différent du manifeste pour {row.family}")
        key = (row.model_id, row.family, row.mix_id, row.horizon_years, row.basis, row.metric)
        if key in table.rows:
            raise ScenarioTableError(f"{where} : ligne en double {key}")
        table.rows[key] = row
    if not table.rows:
        raise ScenarioTableError("table vide")
    return table


def _count_enclosing(table: ScenarioTable, row: Row) -> None:
    if not row.ci_lo - _FLOAT_TOL <= row.value <= row.ci_hi + _FLOAT_TOL:
        table.integrity["ci_not_enclosing"] = table.integrity.get("ci_not_enclosing", 0) + 1


def parse_runtime_json(
    run_id: str, manifest: dict[str, Any], key: str, body: bytes, *, expected_sha256: str | None = None
) -> ScenarioTable:
    """Lit ``scenarios_runtime.json`` du job (tables par modèle et famille, valeurs [value, ci_lo, ci_hi])."""
    missing = [k for k in MANIFEST_KEYS if k not in manifest]
    if missing:
        raise ScenarioTableError(f"manifeste incomplet : {missing}")
    actual_sha = sha256_hex(body)
    if not expected_sha256:
        raise ScenarioTableError(f"sha256 de {key} non déclaré par le manifeste : table non vérifiable, refusée")
    if expected_sha256 != actual_sha:
        raise ScenarioTableError(f"sha256 de {key} ({actual_sha}) différent du manifeste ({expected_sha256})")
    try:
        doc = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ScenarioTableError(f"{key} illisible") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("tables"), dict):
        raise ScenarioTableError(f"{key} : clé « tables » absente")
    for name in MANIFEST_KEYS:
        if str(doc.get(name)) != str(manifest[name]):
            raise ScenarioTableError(f"{key} : {name} {doc.get(name)!r} différent du manifeste {manifest[name]!r}")
    version = ".".join(str(doc["schema_version"]).split(".")[:2])
    if version not in SUPPORTED_SCHEMAS:
        raise ScenarioTableError(f"schéma {doc['schema_version']!r} non pris en charge ({SUPPORTED_SCHEMAS})")
    if list(doc.get("value_order") or ["value", "ci_lo", "ci_hi"]) != ["value", "ci_lo", "ci_hi"]:
        raise ScenarioTableError(f"{key} : value_order inattendu {doc.get('value_order')!r}")

    table = ScenarioTable(run_id=run_id, manifest=manifest, table_key=key, table_sha256=actual_sha)
    table.integrity = {
        "format": "runtime_json",
        "file_sha256_verified": True,
        "ci_not_enclosing": 0,
        "units": doc.get("units"),
    }
    skipped = 0
    for name, sub in doc["tables"].items():
        if not isinstance(sub, dict) or not isinstance(sub.get("mixes"), dict):
            raise ScenarioTableError(f"{key} : table {name!r} mal formée")
        where = f"table {name}"
        common = {
            "model_id": str(sub["model_id"]),
            "family": str(sub["family"]),
            "n_paths": _to_int(sub.get("n_paths"), f"{where} n_paths", optional=True),
            "seed": _to_int(sub.get("seed"), f"{where} seed", optional=True),
            "fitted_through": str(sub.get("fitted_through") or ""),
            "data_sha256": str(doc["data_sha256"]),
            "code_sha": str(doc["code_sha"]),
            "currency": sub.get("currency"),
            "window_start": sub.get("window_start"),
            "n_boot": _to_int(sub.get("n_boot"), f"{where} n_boot", optional=True),
        }
        for mix, by_basis in sub["mixes"].items():
            weights = parse_mix_id(mix)
            hyp = bool(sub.get("hypothese")) or any(weights[b] > 0 for b in SHORT_HISTORY_BLOCKS)
            for basis, by_h in by_basis.items():
                for horizon, metrics in by_h.items():
                    for metric, triple in metrics.items():
                        if not isinstance(triple, list) or len(triple) != 3 or any(v is None for v in triple):
                            skipped += 1
                            continue
                        row = Row(
                            mix_id=mix,
                            horizon_years=_to_int(horizon, f"{where} horizon"),
                            basis=str(basis),
                            metric=str(metric),
                            value=_to_float(triple[0], f"{where} {metric}"),
                            ci_lo=_to_float(triple[1], f"{where} {metric} ci_lo"),
                            ci_hi=_to_float(triple[2], f"{where} {metric} ci_hi"),
                            hypothese=hyp,
                            **common,
                        )
                        if row.ci_lo > row.ci_hi + _FLOAT_TOL:
                            raise ScenarioTableError(f"{where} {mix} {metric} : ci_lo > ci_hi")
                        _count_enclosing(table, row)
                        rkey = (row.model_id, row.family, row.mix_id, row.horizon_years, row.basis, row.metric)
                        if rkey in table.rows:
                            raise ScenarioTableError(f"{where} : ligne en double {rkey}")
                        table.rows[rkey] = row
    if skipped:
        table.warnings.append(f"{skipped} valeur(s) absente(s) (NaN) ignorée(s)")
    if not table.rows:
        raise ScenarioTableError("table vide")
    return table


def _rel_path(value: Any, what: str) -> str:
    text = str(value or "")
    if not _REL_PATH.match(text) or ".." in text:
        raise ScenarioTableError(f"chemin {what} invalide : {text!r}")
    return text


def _table_entry(manifest: dict[str, Any]) -> tuple[str, str, str | None, str | None]:
    """(chemin relatif, format, sha256 attendu ou None, note) de la table à lire, d'après le manifeste.

    Contrat : ``manifest["table"] = {"file": "runtime/scenarios_runtime.csv", "format": "csv", "sha256": "…"}``
    (``sha256`` obligatoire, ici ou dans ``outputs_sha256``). Repli tolérant et signalé si ``table`` manque : une
    sortie compacte déclarée dans ``manifest["outputs"]`` (``runtime_csv`` puis ``runtime_json``). Jamais de chemin
    par défaut silencieux.
    """
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    declared = manifest.get("outputs_sha256") if isinstance(manifest.get("outputs_sha256"), dict) else {}
    entry = manifest.get("table")
    note = None
    if isinstance(entry, dict) and entry.get("file"):
        path = _rel_path(entry["file"], "manifest.table.file")
        fmt = str(entry.get("format") or "").lower()
    elif outputs.get("runtime_csv") or outputs.get("runtime_json"):
        key = "runtime_csv" if outputs.get("runtime_csv") else "runtime_json"
        path = _rel_path(outputs[key], f"manifest.outputs.{key}")
        fmt = ""
        note = f"manifest.table absent : repli sur manifest.outputs.{key} = {path}"
    else:
        raise ScenarioTableError(
            'manifeste sans "table" : attendu {"file": "runtime/scenarios_runtime.csv", "format": "csv"} '
            "(ou une sortie outputs.runtime_csv / outputs.runtime_json); aucune table par défaut n'est supposée"
        )
    if not fmt:
        fmt = "json" if path.endswith(".json") else "csv" if path.endswith((".csv", ".csv.gz")) else ""
    if fmt not in ("csv", "json"):
        raise ScenarioTableError(f"format de table non lisible sans dépendance lourde : {fmt or path!r} (csv ou json)")
    expected = (entry.get("sha256") if isinstance(entry, dict) else None) or declared.get(path) or None
    return path, fmt, expected, note


class ScenarioTableLoader:
    """Charge la table depuis le magasin et la garde en mémoire (lecture seule).

    ``load()`` sert le cache; ``load(refresh=True)`` relit ``scenarios/latest.json`` et ne recharge la
    table que si le run_id a changé. ``run_id`` fixe un run précis (rejeu de démonstration).
    """

    def __init__(self, store: Store, *, run_id: str | None = None):
        self.store = store
        self.pinned_run_id = run_id
        self._cache: ScenarioTable | None = None
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._cache = None

    def _current_run_id(self) -> str:
        if self.pinned_run_id:
            run_id = self.pinned_run_id
        else:
            pointer = self.store.get_json(LATEST_KEY)
            if not isinstance(pointer, dict) or not pointer.get("run_id"):
                raise ScenarioTableError(f"pointeur {LATEST_KEY} absent ou sans run_id")
            run_id = str(pointer["run_id"])
        if not RUN_ID_PATTERN.match(run_id):
            raise ScenarioTableError(f"run_id invalide : {run_id!r}")
        return run_id

    def load(self, *, refresh: bool = False) -> ScenarioTable:
        with self._lock:
            if self._cache is not None and not refresh:
                return self._cache
            run_id = self._current_run_id()
            if self._cache is not None and self._cache.run_id == run_id:
                return self._cache
            prefix = f"{OUTPUT_PREFIX}{run_id}/"
            if self.pinned_run_id:
                marker = self.store.get_json(prefix + "_done.json")
                if not isinstance(marker, dict) or marker.get("status") != "ok":
                    state = marker.get("status") if isinstance(marker, dict) else "absent"
                    raise ScenarioTableError(f"run {run_id} non terminé avec succès : {prefix}_done.json {state!r}")
            manifest = self.store.get_json(prefix + "manifest.json")
            if not isinstance(manifest, dict):
                raise ScenarioTableError(f"manifeste absent : {prefix}manifest.json")
            path, fmt, expected, note = _table_entry(manifest)
            obj = self.store.get(prefix + path)
            if obj is None:
                raise ScenarioTableError(f"table absente : {prefix}{path}")
            parser = parse_runtime_json if fmt == "json" else parse_table
            self._cache = parser(run_id, manifest, prefix + path, obj.body, expected_sha256=expected)
            if note:
                self._cache.warnings.insert(0, note)
            return self._cache


def build_manifest(
    run_id: str, table_body: bytes, *, code_sha: str, data_sha256: str | dict[str, str], **extra: Any
) -> dict[str, Any]:
    """Aide pour le producteur de la table et les tests : manifeste minimal cohérent avec ``table_body``."""
    return {
        "schema_version": extra.pop("schema_version", schema.SCHEMA_VERSION),
        "run_id": run_id,
        "code_sha": code_sha,
        "data_sha256": data_sha256,
        "table": {"file": extra.pop("table_file", "table.csv"), "sha256": sha256_hex(table_body)},
        **extra,
    }


def dumps_table(rows: list[dict[str, Any]]) -> bytes:
    """Écrit des lignes en CSV avec les colonnes de schema.COLUMN_NAMES (aide producteur et tests)."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(schema.COLUMN_NAMES), lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in schema.COLUMN_NAMES})
    return out.getvalue().encode("utf-8")
