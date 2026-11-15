"""Schéma de la table de scénarios (v0.2) et identifiants de mélanges.

Module **sans dépendance lourde** (bibliothèque standard seulement) : l'outil du runtime AgentCore peut l'importer
pour lire les tables précalculées, sans numpy ni pandas.

Une ligne par (``model_id``, ``family``, ``mix_id``, ``horizon_years``, ``basis``, ``metric``). Voir README.md,
section « Schéma ».
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

SCHEMA_VERSION = "0.2"

# Blocs d'actifs, dans l'ordre canonique de mix_id. CRYPTO n'apparaît dans mix_id que si son poids est > 0.
BLOCKS = ("CA_EQ", "US_MKT", "BONDS", "CASH", "GOLD", "CRYPTO")
BLOCK_CODES = {"CA_EQ": "ca", "US_MKT": "us", "BONDS": "bd", "CASH": "cs", "GOLD": "gd", "CRYPTO": "cr"}
CODE_BLOCKS = {code: block for block, code in BLOCK_CODES.items()}
CORE_BLOCKS = BLOCKS[:5]

FAMILIES = ("CAD77", "CAD71", "USD1926")
HORIZONS = (1, 3, 5, 10, 15, 20, 30)
BASES = ("nominal", "real")

RET_QUANTILES = (5, 10, 50, 90)
LOSS_THRESHOLDS = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50)  # perte cumulée à l'horizon, en %
MDD_THRESHOLDS = (10, 15, 20, 25, 30, 35, 40, 45, 50)  # perte maximale (drawdown) sur l'horizon, en %

METRICS: tuple[str, ...] = (
    *(f"ret_ann_p{q:02d}" for q in RET_QUANTILES),
    "wealth_p10",
    "mdd_p50",
    "mdd_p90",
    "cvar95_12m",
    *(f"p_loss_gt_{x:02d}" for x in LOSS_THRESHOLDS),
    *(f"p_mdd_gt_{x:02d}" for x in MDD_THRESHOLDS),
)

# Colonnes de la table longue (ordre d'écriture). Types du parquet (Athena) : string, int32, int64, float64, bool.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("schema_version", "string"),
    ("model_id", "string"),
    ("family", "string"),
    ("currency", "string"),
    ("mix_id", "string"),
    ("horizon_years", "int32"),
    ("basis", "string"),
    ("metric", "string"),
    ("value", "float64"),
    ("ci_lo", "float64"),
    ("ci_hi", "float64"),
    ("n_paths", "int32"),
    ("n_boot", "int32"),
    ("seed", "int64"),
    ("fitted_through", "string"),
    ("window_start", "string"),
    ("n_hist_months", "int32"),
    ("hypothese", "bool"),
    ("data_sha256", "string"),
    ("code_sha", "string"),
)
COLUMN_NAMES = tuple(name for name, _ in COLUMNS)

_MIX_RE = re.compile(r"^ca(\d{2,3})-us(\d{2,3})-bd(\d{2,3})-cs(\d{2,3})-gd(\d{2,3})(?:-cr(\d{2,3}))?$")


def mix_id(weights: Mapping[str, float]) -> str:
    """Identifiant d'un mélange : poids en % entiers multiples de 5, par exemple ``ca15-us25-bd45-cs10-gd05``.

    Lève ``ValueError`` si un poids n'est pas un multiple de 5 % ou si la somme ne fait pas 100 %.
    """
    unknown = set(weights) - set(BLOCKS)
    if unknown:
        raise ValueError(f"blocs inconnus : {sorted(unknown)}")
    pct = {}
    for block in BLOCKS:
        raw = float(weights.get(block, 0.0)) * 100.0
        value = round(raw)
        if abs(raw - value) > 1e-6 or value % 5 or value < 0:
            raise ValueError(f"poids de {block} non multiple de 5 % : {raw}")
        pct[block] = value
    if sum(pct.values()) != 100:
        raise ValueError(f"la somme des poids vaut {sum(pct.values())} %, pas 100 %")
    parts = [f"{BLOCK_CODES[b]}{pct[b]:02d}" for b in CORE_BLOCKS]
    if pct["CRYPTO"]:
        parts.append(f"cr{pct['CRYPTO']:02d}")
    return "-".join(parts)


def parse_mix_id(value: str) -> dict[str, float]:
    """Inverse de :func:`mix_id` : renvoie les poids (fractions) des six blocs."""
    match = _MIX_RE.match(value)
    if not match:
        raise ValueError(f"mix_id invalide : {value!r}")
    numbers = [int(g) if g is not None else 0 for g in match.groups()]
    if sum(numbers) != 100:
        raise ValueError(f"mix_id {value!r} : somme {sum(numbers)} %")
    return {block: n / 100.0 for block, n in zip(BLOCKS, numbers, strict=True)}


def l1_distance(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    return float(sum(abs(float(a.get(k, 0.0)) - float(b.get(k, 0.0))) for k in BLOCKS))


def nearest_mix(weights: Mapping[str, float], candidates: Iterable[str]) -> tuple[str, float]:
    """Mélange de la grille le plus proche (distance L1 sur les poids). Aucune extrapolation hors de la grille.

    En cas d'égalité, l'identifiant le plus petit dans l'ordre lexicographique gagne (résultat déterministe).
    """
    best: tuple[float, str] | None = None
    for cand in candidates:
        dist = l1_distance(weights, parse_mix_id(cand))
        key = (round(dist, 12), cand)
        if best is None or key < best:
            best = key
    if best is None:
        raise ValueError("aucun mélange candidat")
    return best[1], best[0]


def validate_rows(rows: Iterable[Mapping[str, object]]) -> list[str]:
    """Contrôle léger d'une table (liste de dictionnaires). Renvoie la liste des erreurs (vide si tout va bien)."""
    errors: list[str] = []
    seen: set[tuple] = set()
    for i, row in enumerate(rows):
        missing = [c for c in COLUMN_NAMES if c not in row]
        if missing:
            errors.append(f"ligne {i} : colonnes manquantes {missing}")
            continue
        key = (row["model_id"], row["family"], row["mix_id"], row["horizon_years"], row["basis"], row["metric"])
        if key in seen:
            errors.append(f"ligne {i} : clé en double {key}")
        seen.add(key)
        if row["metric"] not in METRICS:
            errors.append(f"ligne {i} : métrique inconnue {row['metric']!r}")
        if row["family"] not in FAMILIES:
            errors.append(f"ligne {i} : famille inconnue {row['family']!r}")
        if row["basis"] not in BASES:
            errors.append(f"ligne {i} : base inconnue {row['basis']!r}")
        try:
            parse_mix_id(str(row["mix_id"]))
        except ValueError as exc:
            errors.append(f"ligne {i} : {exc}")
        metric = str(row["metric"])
        value = row["value"]
        if isinstance(value, float) and value != value:  # NaN
            errors.append(f"ligne {i} : valeur NaN pour {metric}")
            continue
        if metric.startswith("p_") and not (0.0 <= float(value) <= 1.0):
            errors.append(f"ligne {i} : probabilité hors [0, 1] pour {metric} : {value}")
        if metric.startswith("mdd_") and not (0.0 <= float(value) <= 1.0):
            errors.append(f"ligne {i} : perte maximale hors [0, 1] : {value}")
        lo, hi = row["ci_lo"], row["ci_hi"]
        if isinstance(lo, float) and isinstance(hi, float) and lo == lo and hi == hi and lo > hi + 1e-12:
            errors.append(f"ligne {i} : ci_lo > ci_hi pour {metric}")
    return errors
