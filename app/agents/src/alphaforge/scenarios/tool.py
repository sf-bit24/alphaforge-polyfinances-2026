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
  (``horizon_exact = false``), avec la même probabilité à l'horizon supérieur, à titre de comparaison : ce n'est pas
  un encadrement garanti (une probabilité de perte n'est pas monotone en horizon). Refus sous le plus petit ou
  au-dessus du plus grand horizon.
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
from dataclasses import dataclass
from typing import Any

from .. import clock
from . import tool_facts
from .tool_render import render_fr
from .tool_table import (
    BLOCKS,
    DEGRADED_HORIZONS,
    SHORT_HISTORY_BLOCKS,
    UNVALIDATED_BLOCKS,
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


class RefusalError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


# --------------------------------------------------------------------------- entrées


def normalize_weights(weights: Mapping[str, Any]) -> tuple[dict[str, float], list[str]]:
    """Valide et renormalise les poids; renvoie (poids des six blocs, signalements)."""
    if not isinstance(weights, Mapping) or not weights:
        raise RefusalError("bad_weights", "poids absents : un dictionnaire bloc -> poids est attendu")
    out = dict.fromkeys(BLOCKS, 0.0)
    flags: list[str] = []
    for raw_key, raw_value in weights.items():
        key = str(raw_key).strip()
        block = key.upper() if key.upper() in BLOCKS else CODES.get(key.lower())
        if block is None:
            raise RefusalError("bad_weights", f"bloc inconnu {raw_key!r}; blocs admis : {', '.join(BLOCKS)}")
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise RefusalError("bad_weights", f"poids illisible pour {block} : {raw_value!r}") from exc
        if not math.isfinite(value) or value < 0:
            raise RefusalError("bad_weights", f"poids négatif ou non fini pour {block} : {raw_value!r}")
        out[block] += value
    total = sum(out.values())
    if abs(total - 1.0) <= SUM_TOLERANCE:
        scale = total
    elif abs(total - 100.0) <= 100 * SUM_TOLERANCE:
        scale = total
        flags.append("poids lus en pourcentages")
    else:
        raise RefusalError(
            "bad_weights",
            f"la somme des poids vaut {total:g} : attendu 1 (fractions) ou 100 (pourcentages), à 2 % près",
        )
    if abs(total - 1.0) > 1e-9 and abs(total - 100.0) > 1e-9:
        flags.append(f"poids renormalisés (somme {total:g})")
    return {block: weight / scale for block, weight in out.items()}, flags


def _risky_weight(weights: Mapping[str, float]) -> float:
    return sum(weight for block, weight in weights.items() if block not in DEFENSIVE_BLOCKS)


def snap_mix(weights: Mapping[str, float], candidates: list[str], max_l1: float = MAX_L1_DISTANCE) -> dict[str, Any]:
    """Mélange de la grille le plus proche en L1; refus au-delà de ``max_l1`` (jamais d'extrapolation)."""
    if not candidates:
        raise RefusalError("no_grid", "aucun mélange dans la table pour ce modèle, cette famille et cette base")
    scored = []
    for mix in candidates:
        grid = parse_mix_id(mix)
        distance = round(sum(abs(weights.get(block, 0.0) - grid[block]) for block in BLOCKS), 10)
        scored.append((distance, -_risky_weight(grid), mix, grid))
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    best = scored[0]
    ties = [item[2] for item in scored[1:] if abs(item[0] - best[0]) <= 1e-9]
    if best[0] > max_l1 + 1e-9:
        raise RefusalError(
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
        raise RefusalError("no_grid", "aucun horizon disponible pour ce mélange")
    if requested in available:
        return {"requested": requested, "used": requested, "exact": True, "upper": None, "available": available}
    if requested < available[0] or requested > available[-1]:
        raise RefusalError(
            "out_of_grid",
            f"horizon {requested} ans hors de la grille ({available[0]}–{available[-1]} ans); aucune extrapolation",
            {"available_horizons": available},
        )
    lower = max(horizon for horizon in available if horizon < requested)
    upper = min(horizon for horizon in available if horizon > requested)
    return {"requested": requested, "used": lower, "exact": False, "upper": upper, "available": available}


def pick_loss_bucket(
    loss_threshold_cad: float | None, amount_cad: float | None, levels: list[int]
) -> dict[str, Any] | None:
    """Convertit le seuil en % du montant et choisit le palier par arrondi vers le bas (voir docstring du module)."""
    if loss_threshold_cad is None:
        return None
    if amount_cad is None:
        raise RefusalError(
            "bad_threshold", "un seuil en dollars demande amount_cad (montant investi) pour le convertir en %"
        )
    try:
        threshold, amount = float(loss_threshold_cad), float(amount_cad)
    except (TypeError, ValueError) as exc:
        raise RefusalError("bad_threshold", "seuil ou montant illisible") from exc
    if not (math.isfinite(threshold) and math.isfinite(amount)) or amount <= 0 or threshold <= 0:
        raise RefusalError("bad_threshold", "seuil et montant doivent être des nombres positifs")
    threshold_pct = threshold / amount * 100
    if threshold_pct > 100 + 1e-9:
        raise RefusalError(
            "bad_threshold", f"seuil de perte ({threshold_pct:.1f} % du montant) supérieur au montant investi"
        )
    if not levels:
        raise RefusalError("no_grid", "aucun palier p_loss_gt_XX dans la table")
    below = [candidate for candidate in levels if candidate <= threshold_pct + 1e-9]
    lower_bound = not below
    level = max(below) if below else min(levels)
    return {
        "loss_threshold_cad": threshold,
        "amount_cad": amount,
        "requested_pct": threshold_pct / 100,
        "bucket_metric": f"p_loss_gt_{level:02d}",
        "bucket_pct": level / 100,
        "bucket_cad": amount * level / 100,
        "exact": abs(level - threshold_pct) <= 1e-9,
        "is_lower_bound": lower_bound,
        "rule": (
            "seuil sous le plus petit palier : la probabilité du plus petit palier est un minorant (« au moins »)"
            if lower_bound
            else "seuil arrondi vers le bas au palier disponible : la probabilité n'est pas sous-estimée"
        ),
    }


# --------------------------------------------------------------------------- calcul


def _metric_view(row: Row) -> dict[str, Any]:
    return {
        "value": row.value,
        "ci_lo": row.ci_lo,
        "ci_hi": row.ci_hi,
        "hypothese": row.hypothese,
        "n_paths": row.n_paths,  # borne « < 1/n_paths » d'une probabilité nulle (tool_render.prob)
        "fact_id": tool_facts.fact_id(row),
    }


def _wanted_metrics(available: dict[str, Row], bucket: dict[str, Any] | None) -> list[str]:
    loss_metrics = sorted((metric for metric in available if loss_level(metric) is not None), key=loss_level)
    wanted = [metric for metric in KEY_METRICS if metric in available]
    if bucket is None:
        return wanted + loss_metrics
    index = loss_metrics.index(bucket["bucket_metric"])
    return wanted + loss_metrics[max(0, index - 1) : index + 2]  # palier retenu et ses voisins


def compute_scenario_risk(  # noqa: PLR0913 - signature publique, appelée par mot-clé (outil Strands, tests)
    table: ScenarioTable,
    weights: Mapping[str, Any],
    horizon_years: int,
    loss_threshold_cad: float | None = None,
    amount_cad: float | None = None,
    family: str = "CAD77",
    model_id: str | None = None,
    basis: str = "nominal",
    include_sensitivity: bool = False,  # noqa: FBT001, FBT002 - signature publique (paramètre de l'outil Strands)
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
    trace_id = tool_facts.trace_id_for(request, table.run_id)
    try:
        return _compute(table, request, trace_id, started, max_l1)
    except RefusalError as refusal:
        return _refusal(table, request, trace_id, started, refusal)


@dataclass(frozen=True)
class _GridPoint:
    """Demande rattachée à la grille : modèle principal, mélange et horizon retenus, lignes de la table à ce point."""

    table: ScenarioTable
    model_id: str
    family: str
    basis: str
    weights: dict[str, float]
    weight_flags: list[str]
    grid: dict[str, Any]
    horizon: dict[str, Any]
    bucket: dict[str, Any] | None
    rows: dict[str, Row]
    wanted: list[str]

    @property
    def head_row(self) -> Row:
        return self.rows[self.wanted[0]]

    @property
    def currency(self) -> str | None:
        return tool_facts.currency_of(self.table, self.head_row)

    @property
    def hypothese(self) -> bool:
        return any(row.hypothese for row in self.rows.values()) or any(
            self.weights[block] > 0 for block in SHORT_HISTORY_BLOCKS
        )

    def metrics(self, model_id: str, horizon_years: int) -> dict[str, Row]:
        return self.table.metrics(model_id, self.family, self.grid["mix_id"], horizon_years, self.basis)


def _check_family(table: ScenarioTable, family: str) -> None:
    if family not in table.families():
        raise RefusalError("no_grid", f"famille {family!r} absente; familles disponibles : {table.families()}")


def _primary_model(table: ScenarioTable, request: dict[str, Any]) -> str:
    primary = request["model_id"] or table.default_model
    visible = [model for model in table.models if table.display(model) != "hidden"]
    if primary not in visible:
        raise RefusalError("no_grid", f"modèle {primary!r} absent ou masqué; modèles disponibles : {visible}")
    if table.display(primary) == "sensitivity_only" and not request["include_sensitivity"]:
        raise RefusalError(
            "sensitivity_only",
            f"modèle {primary!r} réservé à l'analyse de sensibilité : le demander avec include_sensitivity = true",
        )
    return primary


def _whole_years(raw_horizon: Any) -> int:
    if isinstance(raw_horizon, bool) or not isinstance(raw_horizon, int | float) or raw_horizon != int(raw_horizon):
        raise RefusalError("bad_horizon", "horizon_years doit être un nombre entier d'années")
    return int(raw_horizon)


def _locate(table: ScenarioTable, request: dict[str, Any], max_l1: float) -> _GridPoint:
    """Valide la demande et la rattache à la grille; refus si elle en sort (aucune extrapolation)."""
    family, basis = request["family"], request["basis"]
    _check_family(table, family)
    primary = _primary_model(table, request)
    horizon_requested = _whole_years(request["horizon_years"])
    weights, weight_flags = normalize_weights(request["weights"])
    grid = snap_mix(weights, table.mixes(primary, family, basis), max_l1)
    horizon = pick_horizon(horizon_requested, table.horizons(primary, family, grid["mix_id"], basis))
    rows = table.metrics(primary, family, grid["mix_id"], horizon["used"], basis)
    levels = sorted(level for level in (loss_level(metric) for metric in rows) if level is not None)
    bucket = pick_loss_bucket(request["loss_threshold_cad"], request["amount_cad"], levels)
    wanted = _wanted_metrics(rows, bucket)
    if not wanted:
        raise RefusalError("no_grid", "aucune métrique pour ce point de la grille")
    return _GridPoint(
        table=table,
        model_id=primary,
        family=family,
        basis=basis,
        weights=weights,
        weight_flags=weight_flags,
        grid=grid,
        horizon=horizon,
        bucket=bucket,
        rows=rows,
        wanted=wanted,
    )


def _listed_models(table: ScenarioTable, primary: str, *, include_sensitivity: bool) -> list[str]:
    # Affichage (volet C) : default et compare toujours; sensitivity_only sur demande; hidden jamais.
    shown = {"default", "compare"} | ({"sensitivity_only"} if include_sensitivity else set())
    return [model for model in table.models if table.display(model) in shown or model == primary]


def _model_spread(all_models: list[dict[str, Any]], compare: list[str]) -> dict[str, Any]:
    spread = {}
    for metric in compare:
        values = [
            (entry["model_id"], entry["metrics"][metric]["value"]) for entry in all_models if metric in entry["metrics"]
        ]
        if len(values) >= 2:
            low, high = min(values, key=lambda pair: pair[1]), max(values, key=lambda pair: pair[1])
            spread[metric] = {"min": low[1], "min_model": low[0], "max": high[1], "max_model": high[0]}
    return spread


class _Figures:
    """Nombres cités pour un point de grille. ``facts`` garde l'ordre de citation : métriques principales, distance
    L1, montant en dollars, horizon supérieur, puis les autres modèles."""

    def __init__(self, point: _GridPoint, request: dict[str, Any], trace_id: str):
        self.point = point
        self.trace_id = trace_id
        self.facts: list[dict[str, Any]] = []
        self.primary = {metric: self._cite(point.rows[metric]) for metric in point.wanted}
        self.l1_fact_id = self._cite_l1_distance()
        self.wealth_cad = self._wealth_in_cad(request["amount_cad"])
        focus = point.bucket["bucket_metric"] if point.bucket else None
        self.upper = self._upper_horizon(focus)
        # Tous les modèles, côte à côte, sur le même point de grille : leur désaccord est une incertitude à montrer.
        compare = [
            metric
            for metric in (focus, "ret_ann_p10", "ret_ann_p50", "mdd_p90", "cvar95_12m")
            if metric and metric in point.rows
        ]
        self.listed = _listed_models(point.table, point.model_id, include_sensitivity=request["include_sensitivity"])
        self.all_models = [self._model_entry(model_id, compare) for model_id in self.listed]
        self.spread = _model_spread(self.all_models, compare)

    def _cite(self, row: Row) -> dict[str, Any]:
        """Vue de la ligne pour le modèle; ses trois Facts (valeur, bornes de l'IC) rejoignent ``facts``."""
        self.facts += tool_facts.row_facts(self.point.table, row, self.trace_id)
        return _metric_view(row)

    def _cite_l1_distance(self) -> str:
        fact_id = f"scn.tool.{self.trace_id}.l1_distance"
        self.facts.append(
            tool_facts.simple_fact(
                fact_id,
                "distance L1 entre le mélange demandé et le mélange de la grille",
                self.point.grid["l1_distance"],
                "ratio",
                self.trace_id,
                self.point.table,
            )
        )
        return fact_id

    def _wealth_in_cad(self, amount_cad: Any) -> dict[str, Any] | None:
        rows = self.point.rows
        if not amount_cad or "wealth_p10" not in rows:
            return None
        try:
            amount = float(amount_cad)
        except (TypeError, ValueError):
            return None
        if not amount > 0:  # écarte aussi NaN
            return None
        row, currency = rows["wealth_p10"], self.point.currency
        fact_id = f"scn.tool.{self.trace_id}.wealth_p10_amount"
        self.facts.append(
            tool_facts.simple_fact(
                fact_id,
                f"patrimoine final au 10e centile pour {amount:.0f} investis ({row.family})",
                row.value * amount,
                currency or "CAD",
                self.trace_id,
                self.point.table,
                status="HYPOTHESE" if row.hypothese else "FAIT",
                currency=currency,
            )
        )
        return {
            "value": row.value * amount,
            "ci_lo": row.ci_lo * amount,
            "ci_hi": row.ci_hi * amount,
            "fact_id": fact_id,
        }

    def _upper_horizon(self, focus: str | None) -> dict[str, Any] | None:
        horizon = self.point.horizon
        if horizon["exact"] or not focus:
            return None
        upper_rows = self.point.metrics(self.point.model_id, horizon["upper"])
        if focus not in upper_rows:
            return None
        return {"horizon_years": horizon["upper"], "metric": focus, **self._cite(upper_rows[focus])}

    def _model_entry(self, model_id: str, compare: list[str]) -> dict[str, Any]:
        table = self.point.table
        rows = self.point.metrics(model_id, self.point.horizon["used"])
        # Les Facts du modèle principal sont déjà cités avec ses métriques principales.
        view = _metric_view if model_id == self.point.model_id else self._cite
        return {
            "model_id": model_id,
            "name": table.model_info(model_id).get("name") or model_id,
            "display": table.display(model_id),
            "available": bool(rows),
            "fitted_through": next(iter(rows.values())).fitted_through if rows else None,
            "metrics": {metric: view(rows[metric]) for metric in compare if metric in rows},
        }


def _envelope(status: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "tool": tool_facts.TOOL_NAME,
        "simulation_only": True,
        "disclaimer_fr": DISCLAIMER_FR,
        "request": request,
    }


def _run_info(table: ScenarioTable, family: str) -> dict[str, Any]:
    return {
        "run_id": table.run_id,
        "table_key": table.table_key,
        "table_sha256": table.table_sha256,
        "code_sha": table.code_sha,
        "data_sha256": table.data_sha256(family),
    }


def _validation_flags(
    table: ScenarioTable, model_id: str, horizon: int, basis: str, mix_weights: Mapping[str, float]
) -> dict[str, Any]:
    """``validated`` : horizon dans les horizons validés hors échantillon, base nominale et mélange sans or ni
    crypto (blocs non testés hors échantillon, VALIDATION.md) (volet C)."""
    horizons, declared = table.validated_horizons(model_id)
    reasons = []
    if horizon not in horizons:
        reasons.append(f"horizon {horizon} ans hors des horizons validés {horizons}")
    if basis not in VALIDATED_BASES:
        reasons.append(f"base {basis} non validée")
    untested = [block for block in UNVALIDATED_BLOCKS if mix_weights.get(block, 0.0) > 0]
    if untested:
        reasons.append(f"mélange avec {', '.join(untested)} : blocs non testés hors échantillon")
    return {
        "validated": not reasons,
        "validation_reasons": reasons,
        "validated_horizons": horizons,
        "validated_horizons_declared": declared,
        "degraded_calibration": horizon in DEGRADED_HORIZONS and not reasons,
    }


def _ok_result(point: _GridPoint, request: dict[str, Any], figures: _Figures) -> dict[str, Any]:
    table, family, head_row = point.table, point.family, point.head_row
    model_info = table.model_info(point.model_id)
    return {
        **_envelope("ok", request),
        "model_id": point.model_id,
        "model_name": model_info.get("name") or point.model_id,
        "family": family,
        "basis": point.basis,
        "currency": point.currency,
        "fitted_through": head_row.fitted_through,
        "window_start": head_row.window_start or table.family_info(family).get("window_start"),
        "n_paths": head_row.n_paths,
        "seed": head_row.seed,
        "hypothese": point.hypothese,
        "run": _run_info(table, family),
        "data_sha256": table.data_sha256(family),
        "code_sha": table.code_sha,
        "weights_normalized": point.weights,
        "weight_flags": point.weight_flags,
        "grid": {**point.grid, "l1_fact_id": figures.l1_fact_id},
        "horizon": point.horizon,
        "threshold": point.bucket,
        "primary": figures.primary,
        "wealth_p10_amount": figures.wealth_cad,
        "upper_horizon": figures.upper,
        "all_models": figures.all_models,
        "model_spread": figures.spread,
        "model_assumptions": model_info.get("assumptions") or [],
        "validation": model_info.get("validation"),
        "validation_by_model": {model: table.model_info(model).get("validation") for model in figures.listed},
        "display": table.display(point.model_id),
        **_validation_flags(table, point.model_id, point.horizon["used"], point.basis, point.grid["mix_weights"]),
        "integrity": {key: value for key, value in table.integrity.items() if key != "units"},
        "table_warnings": list(table.warnings),
        "facts": figures.facts,
    }


def _add_explanation(result: dict[str, Any], table: ScenarioTable, trace_id: str, started: str) -> None:
    explanation = render_fr(result)
    result["explanation"] = explanation
    result["explanation_facts"] = [
        statement for key in ("data_used", "why", "limits", "what_would_change") for statement in explanation[key]
    ]
    result["trace_event"] = tool_facts.trace_event(
        trace_id=trace_id,
        inputs=result["request"],
        started_utc=started,
        ended_utc=clock.iso(ms=True),
        status="ok",
        output_summary=explanation["headline"],
        fact_ids=[fact["fact_id"] for fact in result["facts"]],
        table=table,
        family=result["family"],
        seed=result["seed"],
    )


def _compute(
    table: ScenarioTable, request: dict[str, Any], trace_id: str, started: str, max_l1: float
) -> dict[str, Any]:
    point = _locate(table, request, max_l1)
    result = _ok_result(point, request, _Figures(point, request, trace_id))
    _add_explanation(result, table, trace_id, started)
    return result


def _refusal(
    table: ScenarioTable | None, request: dict[str, Any], trace_id: str, started: str, refusal: RefusalError
) -> dict[str, Any]:
    family = request.get("family")
    return {
        **_envelope("refus", request),
        "error": {"code": refusal.code, "message": refusal.message, "details": refusal.details},
        "run": (
            {"run_id": table.run_id, "table_sha256": table.table_sha256, "code_sha": table.code_sha}
            if table is not None
            else None
        ),
        "facts": [],
        "explanation_facts": [],
        "trace_event": tool_facts.trace_event(
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


_COMPACT_KEYS = (
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


def compact_for_model(result: dict[str, Any]) -> dict[str, Any]:
    """Ce que le LLM reçoit : nombres et fact_id, sans la liste complète des Facts (gardée dans le registre)."""
    if result["status"] != "ok":
        return {key: result[key] for key in ("status", "tool", "error", "disclaimer_fr")} | {
            "trace_id": result["trace_event"]["trace_id"]
        }
    out = {key: result[key] for key in _COMPACT_KEYS}
    out["run_id"] = result["run"]["run_id"]
    out["trace_id"] = result["trace_event"]["trace_id"]
    out["explanation"] = {
        key: [statement["text_fr"] for statement in statements]
        for key, statements in result["explanation"].items()
        if isinstance(statements, list)
    }
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
  (horizon.exact = false), and the same probability at the next higher grid horizon is shown for comparison. It is
  NOT a guaranteed bound: the value at the requested horizon may lie outside the two. Outside the grid: refusal.
- loss_threshold_cad and amount_cad: a loss threshold in dollars and the amount invested. The threshold is
  converted to a % and rounded DOWN to the nearest available level, so the probability is not understated.
- family: historical data family, "CAD77" (CAD, 1977+), "CAD71" (CAD, 1971+) or "USD1926" (USD, 1926+).
- model_id: main model (default: the table's default model). basis: "nominal" (default) or "real" (after inflation).
- include_sensitivity: also show the sensitivity-only models (regime models), only for a sensitivity analysis. A
  sensitivity-only model_id is refused unless include_sensitivity is true.

If validated is false (horizon beyond the out-of-sample validated horizons, real basis, or a mix with GOLD or
CRYPTO, blocks never tested out of sample), say clearly that the
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
                key: kwargs.get(key)
                for key in (
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
                tool_facts.trace_id_for(request, None),
                clock.iso(ms=True),
                RefusalError("table_unavailable", f"table de scénarios indisponible : {exc}"),
            )
        else:
            result = compute_scenario_risk(table, max_l1=self.max_l1, **kwargs)
        with self._lock:
            self.ledger.append(result)
        return result

    def facts(self) -> list[dict[str, Any]]:
        return [fact for result in self.ledger for fact in result["facts"]]

    def trace_events(self) -> list[dict[str, Any]]:
        return [result["trace_event"] for result in self.ledger]

    def tool(self) -> Any:
        from strands import tool

        owner = self

        @tool(name="scenario_risk", description=TOOL_DESCRIPTION, inputSchema=INPUT_SCHEMA)
        def scenario_risk(  # noqa: PLR0913 - signature imposée par @tool (paramètres de l'outil, noms figés)
            weights: dict,
            horizon_years: int,
            loss_threshold_cad: float | None = None,
            amount_cad: float | None = None,
            family: str = "CAD77",
            model_id: str | None = None,
            basis: str = "nominal",
            include_sensitivity: bool = False,  # noqa: FBT001, FBT002 - signature imposée par @tool
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
