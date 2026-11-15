"""Outil Strands ``scenario_risk`` : lit la table de scénarios précalculée, ne calcule aucun modèle.

Simulation seulement, jamais un conseil. « Le code calcule, le modèle explique, chaque nombre cite sa source » :
- ``compute_scenario_risk`` (déterministe, sans LLM) fait la lecture, le rattachement à la grille et la
  conversion du seuil, puis produit les ``Fact``/``TraceEvent`` (tool_facts.py) et l'explication (tool_render.py);
- ``make_scenario_risk_tool`` enveloppe ce calcul dans un ``@tool`` Strands. Le modèle reçoit une version compacte
  (nombres, ``fact_id``, explication); les ``Fact`` et le ``TraceEvent`` complets restent dans
  ``ScenarioRiskTool.ledger`` pour le Judge et l'agent d'explicabilité, qui les citent sans recopier de chiffres.
- L'appel de l'outil apparaît aussi dans la trace de l'agent (``agentkit.TraceHooks``, étape ``tool``).

Règles (documentées, testées, aucune extrapolation) :
- Poids : blocs ``CA_EQ, US_MKT, BONDS, CASH, GOLD, CRYPTO`` (ou codes ``ca, us, bd, cs, gd, cr``), positifs;
  somme entre 0.98 et 1.02 (fractions) ou entre 98 et 102 (pourcentages), puis renormalisés à 1. Sinon refus.
- Mélange : le plus proche de la grille en distance L1 (somme des écarts absolus des poids). Refus si la distance
  dépasse ``MAX_L1_DISTANCE`` = 0.10, soit 10 points de pondération déplacés au total (par exemple 5 points d'un
  bloc vers un autre). En cas d'égalité, le mélange le plus risqué (plus de poids hors BONDS et CASH) est retenu,
  puis l'ordre lexicographique : en cas de doute, on ne choisit pas le mélange le plus rassurant.
- Horizon : exact s'il est dans la grille; sinon l'horizon de la grille immédiatement inférieur, signalé
  (``horizon_exact = false``), avec la même probabilité à l'horizon supérieur pour encadrer. Refus sous le plus
  petit ou au-dessus du plus grand horizon.
- Seuil de perte : ``loss_threshold_cad / amount_cad`` en %, **arrondi vers le bas** au palier ``p_loss_gt_XX``
  disponible. Comme P(perte > 15 %) >= P(perte > 17,6 %), la probabilité affichée n'est jamais inférieure à celle
  du seuil demandé (majorant). Sous le plus petit palier, la probabilité du plus petit palier est un minorant
  (« au moins »), signalé ``is_lower_bound``. Seuil > 100 % du montant : refus.
"""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Mapping
from typing import Any

from .. import clock
from . import tool_facts as tf
from .tool_render import render_fr
from .tool_table import (
    BLOCKS,
    DEGRADED_HORIZONS,
    SHORT_HISTORY_BLOCKS,
    VALIDATED_BASES,
    Row,
    ScenarioTable,
    ScenarioTableError,
    ScenarioTableLoader,
    loss_level,
    parse_mix_id,
)

MAX_L1_DISTANCE = 0.10
SUM_TOLERANCE = 0.02
CODES = {"ca": "CA_EQ", "us": "US_MKT", "bd": "BONDS", "cs": "CASH", "gd": "GOLD", "cr": "CRYPTO"}
DEFENSIVE_BLOCKS = frozenset({"BONDS", "CASH"})
KEY_METRICS = (
    "ret_ann_p05",
    "ret_ann_p10",
    "ret_ann_p50",
    "ret_ann_p90",
    "wealth_p10",
    "mdd_p50",
    "mdd_p90",
    "cvar95_12m",
)
DISCLAIMER_FR = (
    "Simulation éducative fondée sur un modèle statistique de données historiques : ce n'est ni une prévision, "
    "ni un conseil financier personnalisé."
)


class Refusal(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


# --------------------------------------------------------------------------- entrées


def normalize_weights(weights: Mapping[str, Any]) -> tuple[dict[str, float], list[str]]:
    """Valide et renormalise les poids; renvoie (poids des six blocs, signalements)."""
    if not isinstance(weights, Mapping) or not weights:
        raise Refusal("bad_weights", "poids absents : un dictionnaire bloc -> poids est attendu")
    out = dict.fromkeys(BLOCKS, 0.0)
    flags: list[str] = []
    for raw_key, raw_value in weights.items():
        key = str(raw_key).strip()
        block = key.upper() if key.upper() in BLOCKS else CODES.get(key.lower())
        if block is None:
            raise Refusal("bad_weights", f"bloc inconnu {raw_key!r}; blocs admis : {', '.join(BLOCKS)}")
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise Refusal("bad_weights", f"poids illisible pour {block} : {raw_value!r}") from exc
        if not math.isfinite(value) or value < 0:
            raise Refusal("bad_weights", f"poids négatif ou non fini pour {block} : {raw_value!r}")
        out[block] += value
    total = sum(out.values())
    if abs(total - 1.0) <= SUM_TOLERANCE:
        scale = total
    elif abs(total - 100.0) <= 100 * SUM_TOLERANCE:
        scale = total
        flags.append("poids lus en pourcentages")
    else:
        raise Refusal(
            "bad_weights",
            f"la somme des poids vaut {total:g} : attendu 1 (fractions) ou 100 (pourcentages), à 2 % près",
        )
    if abs(total - 1.0) > 1e-9 and abs(total - 100.0) > 1e-9:
        flags.append(f"poids renormalisés (somme {total:g})")
    return {b: v / scale for b, v in out.items()}, flags


def _risky_weight(weights: Mapping[str, float]) -> float:
    return sum(v for b, v in weights.items() if b not in DEFENSIVE_BLOCKS)


def snap_mix(weights: Mapping[str, float], candidates: list[str], max_l1: float = MAX_L1_DISTANCE) -> dict[str, Any]:
    """Mélange de la grille le plus proche en L1; refus au-delà de ``max_l1`` (jamais d'extrapolation)."""
    if not candidates:
        raise Refusal("no_grid", "aucun mélange dans la table pour ce modèle, cette famille et cette base")
    scored = []
    for mix in candidates:
        grid = parse_mix_id(mix)
        distance = round(sum(abs(weights.get(b, 0.0) - grid[b]) for b in BLOCKS), 10)
        scored.append((distance, -_risky_weight(grid), mix, grid))
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    best = scored[0]
    ties = [item[2] for item in scored[1:] if abs(item[0] - best[0]) <= 1e-9]
    if best[0] > max_l1 + 1e-9:
        raise Refusal(
            "out_of_grid",
            f"mélange trop éloigné de la grille : distance L1 {best[0]:.2f} > tolérance {max_l1:.2f}; "
            "aucune extrapolation. Rapprocher le mélange d'un point de la grille.",
            {"nearest_mix_id": best[2], "l1_distance": best[0], "max_l1_distance": max_l1},
        )
    return {
        "mix_id": best[2],
        "mix_weights": best[3],
        "l1_distance": best[0],
        "max_l1_distance": max_l1,
        "ties": ties,
        "tie_rule": "le plus risqué (poids hors BONDS et CASH), puis ordre lexicographique" if ties else None,
    }


def pick_horizon(requested: int, available: list[int]) -> dict[str, Any]:
    if not available:
        raise Refusal("no_grid", "aucun horizon disponible pour ce mélange")
    if requested in available:
        return {"requested": requested, "used": requested, "exact": True, "upper": None, "available": available}
    if requested < available[0] or requested > available[-1]:
        raise Refusal(
            "out_of_grid",
            f"horizon {requested} ans hors de la grille ({available[0]}–{available[-1]} ans); aucune extrapolation",
            {"available_horizons": available},
        )
    lower = max(h for h in available if h < requested)
    upper = min(h for h in available if h > requested)
    return {"requested": requested, "used": lower, "exact": False, "upper": upper, "available": available}


def pick_loss_bucket(
    loss_threshold_cad: float | None, amount_cad: float | None, levels: list[int]
) -> dict[str, Any] | None:
    """Convertit le seuil en % du montant et choisit le palier par arrondi vers le bas (voir docstring du module)."""
    if loss_threshold_cad is None:
        return None
    if amount_cad is None:
        raise Refusal(
            "bad_threshold", "un seuil en dollars demande amount_cad (montant investi) pour le convertir en %"
        )
    try:
        threshold, amount = float(loss_threshold_cad), float(amount_cad)
    except (TypeError, ValueError) as exc:
        raise Refusal("bad_threshold", "seuil ou montant illisible") from exc
    if not (math.isfinite(threshold) and math.isfinite(amount)) or amount <= 0 or threshold <= 0:
        raise Refusal("bad_threshold", "seuil et montant doivent être des nombres positifs")
    pct = threshold / amount * 100
    if pct > 100 + 1e-9:
        raise Refusal("bad_threshold", f"seuil de perte ({pct:.1f} % du montant) supérieur au montant investi")
    if not levels:
        raise Refusal("no_grid", "aucun palier p_loss_gt_XX dans la table")
    below = [lv for lv in levels if lv <= pct + 1e-9]
    lower_bound = not below
    level = max(below) if below else min(levels)
    return {
        "loss_threshold_cad": threshold,
        "amount_cad": amount,
        "requested_pct": pct / 100,
        "bucket_metric": f"p_loss_gt_{level:02d}",
        "bucket_pct": level / 100,
        "bucket_cad": amount * level / 100,
        "exact": abs(level - pct) <= 1e-9,
        "is_lower_bound": lower_bound,
        "rule": (
            "seuil sous le plus petit palier : la probabilité du plus petit palier est un minorant (« au moins »)"
            if lower_bound
            else "seuil arrondi vers le bas au palier disponible : la probabilité n'est pas sous-estimée"
        ),
    }


# --------------------------------------------------------------------------- calcul


def _metric_view(row: Row, fid: bool = True) -> dict[str, Any]:
    out = {"value": row.value, "ci_lo": row.ci_lo, "ci_hi": row.ci_hi, "hypothese": row.hypothese}
    if fid:
        out["fact_id"] = tf.fact_id(row)
    return out


def _wanted_metrics(available: dict[str, Row], bucket: dict[str, Any] | None) -> list[str]:
    loss_metrics = sorted((m for m in available if loss_level(m) is not None), key=loss_level)
    wanted = [m for m in KEY_METRICS if m in available]
    if bucket is None:
        return wanted + loss_metrics
    index = loss_metrics.index(bucket["bucket_metric"])
    return wanted + loss_metrics[max(0, index - 1) : index + 2]  # palier retenu et ses voisins


def compute_scenario_risk(
    table: ScenarioTable,
    weights: Mapping[str, Any],
    horizon_years: int,
    loss_threshold_cad: float | None = None,
    amount_cad: float | None = None,
    family: str = "CAD77",
    model_id: str | None = None,
    basis: str = "nominal",
    include_sensitivity: bool = False,
    *,
    max_l1: float = MAX_L1_DISTANCE,
) -> dict[str, Any]:
    """Résultat complet (nombres, Facts, TraceEvent, explication). Ne lève pas : un refus est un résultat."""
    started = clock.iso(ms=True)
    request = {
        "weights": dict(weights) if isinstance(weights, Mapping) else weights,
        "horizon_years": horizon_years,
        "loss_threshold_cad": loss_threshold_cad,
        "amount_cad": amount_cad,
        "family": family,
        "model_id": model_id,
        "basis": basis,
        "include_sensitivity": bool(include_sensitivity),
    }
    trace_id = tf.trace_id_for(request, table.run_id)
    try:
        return _compute(table, request, trace_id, started, max_l1)
    except Refusal as refusal:
        return _refusal(table, request, trace_id, started, refusal)


def _compute(
    table: ScenarioTable, request: dict[str, Any], trace_id: str, started: str, max_l1: float
) -> dict[str, Any]:
    family, basis = request["family"], request["basis"]
    if family not in table.families():
        raise Refusal("no_grid", f"famille {family!r} absente; familles disponibles : {table.families()}")
    primary = request["model_id"] or table.default_model
    visible = [m for m in table.models if table.display(m) != "hidden"]
    if primary not in visible:
        raise Refusal("no_grid", f"modèle {primary!r} absent ou masqué; modèles disponibles : {visible}")
    raw_horizon = request["horizon_years"]
    if isinstance(raw_horizon, bool) or not isinstance(raw_horizon, int | float) or raw_horizon != int(raw_horizon):
        raise Refusal("bad_horizon", "horizon_years doit être un nombre entier d'années")
    horizon_requested = int(raw_horizon)

    weights, weight_flags = normalize_weights(request["weights"])
    grid = snap_mix(weights, table.mixes(primary, family, basis), max_l1)
    horizon = pick_horizon(horizon_requested, table.horizons(primary, family, grid["mix_id"], basis))
    rows = table.metrics(primary, family, grid["mix_id"], horizon["used"], basis)
    levels = sorted(lv for lv in (loss_level(m) for m in rows) if lv is not None)
    bucket = pick_loss_bucket(request["loss_threshold_cad"], request["amount_cad"], levels)
    wanted = _wanted_metrics(rows, bucket)
    if not wanted:
        raise Refusal("no_grid", "aucune métrique pour ce point de la grille")

    facts: list[dict[str, Any]] = []
    primary_metrics: dict[str, Any] = {}
    for metric in wanted:
        primary_metrics[metric] = _metric_view(rows[metric])
        facts += tf.row_facts(table, rows[metric], trace_id)

    head_row = rows[wanted[0]]
    currency = tf.currency_of(table, head_row)
    hypothese = any(r.hypothese for r in rows.values()) or any(weights[b] > 0 for b in SHORT_HISTORY_BLOCKS)

    l1_fid = f"scn.tool.{trace_id}.l1_distance"
    facts.append(
        tf.simple_fact(
            l1_fid,
            "distance L1 entre le mélange demandé et le mélange de la grille",
            grid["l1_distance"],
            "ratio",
            trace_id,
            table,
        )
    )
    grid["l1_fact_id"] = l1_fid

    wealth_cad = None
    if request["amount_cad"] and "wealth_p10" in rows:
        try:
            amount = float(request["amount_cad"])
        except (TypeError, ValueError):
            amount = None
        if amount and amount > 0:
            row = rows["wealth_p10"]
            wid = f"scn.tool.{trace_id}.wealth_p10_amount"
            wealth_cad = {
                "value": row.value * amount,
                "ci_lo": row.ci_lo * amount,
                "ci_hi": row.ci_hi * amount,
                "fact_id": wid,
            }
            facts.append(
                tf.simple_fact(
                    wid,
                    f"patrimoine final au 10e centile pour {amount:.0f} investis ({row.family})",
                    row.value * amount,
                    currency or "CAD",
                    trace_id,
                    table,
                    status="HYPOTHESE" if row.hypothese else "FAIT",
                    currency=currency,
                )
            )

    upper = None
    focus = bucket["bucket_metric"] if bucket else None
    if not horizon["exact"] and focus:
        upper_rows = table.metrics(primary, family, grid["mix_id"], horizon["upper"], basis)
        if focus in upper_rows:
            upper = {"horizon_years": horizon["upper"], "metric": focus, **_metric_view(upper_rows[focus])}
            facts += tf.row_facts(table, upper_rows[focus], trace_id)

    # Tous les modèles, côte à côte, sur le même point de grille : leur désaccord est une incertitude à montrer.
    compare = [m for m in (focus, "ret_ann_p10", "ret_ann_p50", "mdd_p90", "cvar95_12m") if m and m in rows]
    # Affichage (volet C) : default et compare toujours; sensitivity_only sur demande; hidden jamais.
    shown = {"default", "compare"} | ({"sensitivity_only"} if request["include_sensitivity"] else set())
    listed = [m for m in table.models if table.display(m) in shown or m == primary]
    all_models = []
    for other in listed:
        other_rows = table.metrics(other, family, grid["mix_id"], horizon["used"], basis)
        entry: dict[str, Any] = {
            "model_id": other,
            "name": table.model_info(other).get("name") or other,
            "display": table.display(other),
            "available": bool(other_rows),
            "fitted_through": next(iter(other_rows.values())).fitted_through if other_rows else None,
            "metrics": {},
        }
        for metric in compare:
            if metric in other_rows:
                entry["metrics"][metric] = _metric_view(other_rows[metric])
                if other != primary:
                    facts += tf.row_facts(table, other_rows[metric], trace_id)
        all_models.append(entry)
    spread = {}
    for metric in compare:
        values = [(e["model_id"], e["metrics"][metric]["value"]) for e in all_models if metric in e["metrics"]]
        if len(values) >= 2:
            low, high = min(values, key=lambda v: v[1]), max(values, key=lambda v: v[1])
            spread[metric] = {"min": low[1], "min_model": low[0], "max": high[1], "max_model": high[0]}

    result: dict[str, Any] = {
        "status": "ok",
        "tool": tf.TOOL_NAME,
        "simulation_only": True,
        "disclaimer_fr": DISCLAIMER_FR,
        "request": request,
        "model_id": primary,
        "model_name": table.model_info(primary).get("name") or primary,
        "family": family,
        "basis": basis,
        "currency": currency,
        "fitted_through": head_row.fitted_through,
        "window_start": head_row.window_start or table.family_info(family).get("window_start"),
        "n_paths": head_row.n_paths,
        "seed": head_row.seed,
        "hypothese": hypothese,
        "run": {
            "run_id": table.run_id,
            "table_key": table.table_key,
            "table_sha256": table.table_sha256,
            "code_sha": table.code_sha,
            "data_sha256": table.data_sha256(family),
        },
        "data_sha256": table.data_sha256(family),
        "code_sha": table.code_sha,
        "weights_normalized": weights,
        "weight_flags": weight_flags,
        "grid": grid,
        "horizon": horizon,
        "threshold": bucket,
        "primary": primary_metrics,
        "wealth_p10_amount": wealth_cad,
        "upper_horizon": upper,
        "all_models": all_models,
        "model_spread": spread,
        "model_assumptions": table.model_info(primary).get("assumptions") or [],
        "validation": table.model_info(primary).get("validation"),
        "validation_by_model": {m: table.model_info(m).get("validation") for m in listed},
        "display": table.display(primary),
        **_validation_flags(table, primary, horizon["used"], basis),
        "integrity": {k: v for k, v in table.integrity.items() if k != "units"},
        "table_warnings": list(table.warnings),
        "facts": facts,
    }
    explanation = render_fr(result)
    result["explanation"] = explanation
    result["explanation_facts"] = [
        s for key in ("data_used", "why", "limits", "what_would_change") for s in explanation[key]
    ]
    result["trace_event"] = tf.trace_event(
        trace_id=trace_id,
        inputs=request,
        started_utc=started,
        ended_utc=clock.iso(ms=True),
        status="ok",
        output_summary=explanation["headline"],
        fact_ids=[f["fact_id"] for f in facts],
        table=table,
        family=family,
        seed=head_row.seed,
    )
    return result


def _validation_flags(table: ScenarioTable, model_id: str, horizon: int, basis: str) -> dict[str, Any]:
    """``validated`` : horizon dans les horizons validés hors échantillon et base nominale (volet C)."""
    horizons, declared = table.validated_horizons(model_id)
    reasons = []
    if horizon not in horizons:
        reasons.append(f"horizon {horizon} ans hors des horizons validés {horizons}")
    if basis not in VALIDATED_BASES:
        reasons.append(f"base {basis} non validée")
    return {
        "validated": not reasons,
        "validation_reasons": reasons,
        "validated_horizons": horizons,
        "validated_horizons_declared": declared,
        "degraded_calibration": horizon in DEGRADED_HORIZONS and not reasons,
    }


def _refusal(
    table: ScenarioTable | None, request: dict[str, Any], trace_id: str, started: str, refusal: Refusal
) -> dict[str, Any]:
    family = request.get("family")
    return {
        "status": "refus",
        "tool": tf.TOOL_NAME,
        "simulation_only": True,
        "disclaimer_fr": DISCLAIMER_FR,
        "request": request,
        "error": {"code": refusal.code, "message": refusal.message, "details": refusal.details},
        "run": (
            {"run_id": table.run_id, "table_sha256": table.table_sha256, "code_sha": table.code_sha}
            if table is not None
            else None
        ),
        "facts": [],
        "explanation_facts": [],
        "trace_event": tf.trace_event(
            trace_id=trace_id,
            inputs=request,
            started_utc=started,
            ended_utc=clock.iso(ms=True),
            status="refus",
            output_summary=f"refus : {refusal.message}",
            fact_ids=[],
            table=table,
            family=family if table is not None and family in table.families() else None,
            seed=None,
            message=refusal.message,
        ),
    }


def compact_for_model(result: dict[str, Any]) -> dict[str, Any]:
    """Ce que le LLM reçoit : nombres et fact_id, sans la liste complète des Facts (gardée dans le registre)."""
    if result["status"] != "ok":
        return {k: result[k] for k in ("status", "tool", "error", "disclaimer_fr")} | {
            "trace_id": result["trace_event"]["trace_id"]
        }
    keep = (
        "status",
        "tool",
        "simulation_only",
        "disclaimer_fr",
        "model_id",
        "model_name",
        "family",
        "basis",
        "currency",
        "fitted_through",
        "window_start",
        "data_sha256",
        "code_sha",
        "hypothese",
        "integrity",
        "display",
        "validated",
        "validation_reasons",
        "degraded_calibration",
        "weight_flags",
        "grid",
        "horizon",
        "threshold",
        "primary",
        "wealth_p10_amount",
        "upper_horizon",
        "all_models",
        "model_spread",
    )
    out = {k: result[k] for k in keep}
    out["run_id"] = result["run"]["run_id"]
    out["trace_id"] = result["trace_event"]["trace_id"]
    out["explanation"] = {k: [s["text_fr"] for s in v] for k, v in result["explanation"].items() if isinstance(v, list)}
    out["headline"] = result["explanation"]["headline"]
    return out


# --------------------------------------------------------------------------- outil Strands

TOOL_DESCRIPTION = """Probabilistic risk of a simulated portfolio mix, read from a precomputed scenario table.

Returns, for the nearest mix of the precomputed grid and the given horizon: the probability of a cumulative loss
larger than a threshold (p_loss_gt_XX), annualized-return percentiles (p05, p10, p50, p90), the 10th percentile of
final wealth (multiple of the initial amount, and in dollars if amount_cad is given), the median and 90th percentile
of the maximum drawdown along the way, and the 12-month CVaR 95 %. Every number comes with a 90 % confidence
interval (ci_lo, ci_hi) and a fact_id that you must cite; the result also gives model_id, family, fitted_through
(last month of data used), data_sha256 and code_sha, and the same numbers for ALL available models side by side:
when models disagree, say so, it is part of the uncertainty.

This is a statistical model of past data, NOT a forecast and NEVER personalized advice. Do not round numbers away,
do not invent numbers that are not in the result, always show the interval and say which model produced it.

Arguments:
- weights: mix of the building blocks CA_EQ (Canadian equities), US_MKT (US equities), BONDS, CASH, GOLD, CRYPTO,
  as fractions summing to 1 (or percentages summing to 100). The tool snaps to the nearest grid mix and reports
  the L1 distance; it refuses (status "refus") if the mix is too far from the grid. It never extrapolates.
- horizon_years: integer horizon. If not in the grid, the nearest LOWER grid horizon is used and flagged
  (horizon.exact = false), with the next higher horizon shown to bracket it; outside the grid: refusal.
- loss_threshold_cad and amount_cad: a loss threshold in dollars and the amount invested. The threshold is
  converted to a % and rounded DOWN to the nearest available level, so the probability is not understated.
- family: historical data family, "CAD77" (CAD, 1977+), "CAD71" (CAD, 1971+) or "USD1926" (USD, 1926+).
- model_id: main model (default: the table's default model). basis: "nominal" (default) or "real" (after inflation).
- include_sensitivity: also show the sensitivity-only models (regime models), only for a sensitivity analysis.

If validated is false (horizon beyond the out-of-sample validated horizons, or real basis), say clearly that the
numbers are NOT validated out of sample. If degraded_calibration is true, say that calibration degrades at long
horizons.

On status "refus", read error.message and explain the refusal; do not guess numbers."""

INPUT_SCHEMA = {
    "json": {
        "type": "object",
        "properties": {
            "weights": {
                "type": "object",
                "description": (
                    'Block -> weight, e.g. {"CA_EQ": 0.15, "US_MKT": 0.25, "BONDS": 0.45, "CASH": 0.10, "GOLD": 0.05}'
                ),
                "additionalProperties": {"type": "number", "minimum": 0},
            },
            "horizon_years": {"type": "integer", "minimum": 1},
            "loss_threshold_cad": {"type": ["number", "null"], "exclusiveMinimum": 0},
            "amount_cad": {"type": ["number", "null"], "exclusiveMinimum": 0},
            "family": {"type": "string", "enum": ["CAD77", "CAD71", "USD1926"], "default": "CAD77"},
            "model_id": {"type": ["string", "null"]},
            "basis": {"type": "string", "enum": ["nominal", "real"], "default": "nominal"},
            "include_sensitivity": {"type": "boolean", "default": False},
        },
        "required": ["weights", "horizon_years"],
    }
}


class ScenarioRiskTool:
    """Outil Strands lié à un chargeur de table; garde chaque résultat complet dans ``ledger`` (Facts, trace)."""

    def __init__(self, loader: ScenarioTableLoader, *, max_l1: float = MAX_L1_DISTANCE):
        self.loader = loader
        self.max_l1 = max_l1
        self.ledger: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def run(self, **kwargs: Any) -> dict[str, Any]:
        try:
            table = self.loader.load()
        except ScenarioTableError as exc:
            request = {
                k: kwargs.get(k)
                for k in (
                    "weights",
                    "horizon_years",
                    "loss_threshold_cad",
                    "amount_cad",
                    "family",
                    "model_id",
                    "basis",
                    "include_sensitivity",
                )
            }
            result = _refusal(
                None,
                request,
                tf.trace_id_for(request, None),
                clock.iso(ms=True),
                Refusal("table_unavailable", f"table de scénarios indisponible : {exc}"),
            )
        else:
            result = compute_scenario_risk(table, max_l1=self.max_l1, **kwargs)
        with self._lock:
            self.ledger.append(result)
        return result

    def facts(self) -> list[dict[str, Any]]:
        return [f for r in self.ledger for f in r["facts"]]

    def trace_events(self) -> list[dict[str, Any]]:
        return [r["trace_event"] for r in self.ledger]

    def tool(self) -> Any:
        from strands import tool

        owner = self

        @tool(name="scenario_risk", description=TOOL_DESCRIPTION, inputSchema=INPUT_SCHEMA)
        def scenario_risk(
            weights: dict,
            horizon_years: int,
            loss_threshold_cad: float | None = None,
            amount_cad: float | None = None,
            family: str = "CAD77",
            model_id: str | None = None,
            basis: str = "nominal",
            include_sensitivity: bool = False,
        ) -> str:
            result = owner.run(
                weights=weights,
                horizon_years=horizon_years,
                loss_threshold_cad=loss_threshold_cad,
                amount_cad=amount_cad,
                family=family,
                model_id=model_id,
                basis=basis,
                include_sensitivity=include_sensitivity,
            )
            return json.dumps(compact_for_model(result), ensure_ascii=False, default=str)

        return scenario_risk


def make_scenario_risk_tool(store: Any, *, run_id: str | None = None) -> ScenarioRiskTool:
    """Outil sur le magasin du projet (``store.make_store(settings)``) : local en dev, S3 en AWS."""
    return ScenarioRiskTool(ScenarioTableLoader(store, run_id=run_id))
