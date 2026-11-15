"""``Fact`` et ``TraceEvent`` de l'outil ``scenario_risk``, au format de contracts/decision.py (v0.1.0).

Le contrat vit sur la branche ``feat/finance-engine`` (pydantic, ``extra="forbid"``) et n'est pas encore sur
master : on ne l'importe pas. Ce module produit des dictionnaires **avec exactement les mêmes clés**, que le Judge
ou l'agent d'explicabilité valident par ``Fact.model_validate(d)`` / ``TraceEvent.model_validate(d)`` une fois le
contrat fusionné. Correspondance :

| contrat (decision.py)        | valeur produite ici                                                        |
| ---------------------------- | -------------------------------------------------------------------------- |
| ``Fact.fact_id``             | ``scn.<model>.<famille>.<mix>.<H>y.<base>.<métrique>[.ci_lo|.ci_hi]``       |
| ``Fact.value`` / ``unit``    | fraction (``ratio``, 0.12 = 12 %), ou ``CAD`` pour un montant              |
| ``Fact.as_of``               | ``fitted_through`` du modèle (fin de mois, ISO)                            |
| ``Fact.status``              | ``FAIT`` (calculé par le modèle sur les données), ``HYPOTHESE`` si le      |
|                              | mélange contient un bloc à historique court (crypto 2014+)                 |
| ``Fact.sources[0]``          | ``Source`` de la table : ``dataset=scenarios:<run_id>``, ``sha256`` du fichier |
| ``TraceEvent.tool``          | ``scenario_risk``                                                          |
| ``TraceEvent.data_version``  | ``data_sha256`` de la famille (manifeste)                                  |
| ``TraceEvent.code_version``  | ``code_sha`` du calcul (manifeste)                                         |
| ``TraceEvent.seed``          | graine de la ligne principale                                              |
| ``TraceEvent.model_id``      | ``None`` : aucun LLM n'intervient dans l'outil (le modèle de scénarios     |
|                              | est dans ``inputs``/``output_summary``)                                    |
| ``TraceEvent.status``        | ``ok`` ou ``refus`` (hors grille, entrées invalides, table absente)        |

Les phrases (``Statement`` : ``text_fr``, ``fact_ids``, ``label``) sont construites par tool_render.py.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from typing import Any

from .tool_table import Row, ScenarioTable

TOOL_NAME = "scenario_risk"
AGENT_NAME = "scenarios"
_SAFE = re.compile(r"[^A-Za-z0-9_-]+")
CONTRACT_FACT_KEYS = (
    "fact_id",
    "label_fr",
    "value",
    "unit",
    "currency",
    "as_of",
    "published",
    "status",
    "sources",
    "trace_id",
)
CONTRACT_TRACE_KEYS = (
    "trace_id",
    "parent_id",
    "agent",
    "tool",
    "inputs",
    "output_summary",
    "fact_ids",
    "started_utc",
    "ended_utc",
    "status",
    "message",
    "data_version",
    "code_version",
    "seed",
    "model_id",
    "otel_trace_id",
    "otel_span_id",
)

METRIC_LABELS_FR = {
    "ret_ann_p05": "rendement annualisé, 5e centile",
    "ret_ann_p10": "rendement annualisé, 10e centile",
    "ret_ann_p50": "rendement annualisé, médiane",
    "ret_ann_p90": "rendement annualisé, 90e centile",
    "wealth_p10": "patrimoine final, 10e centile (multiple du capital initial)",
    "mdd_p50": "perte maximale en cours de route, médiane",
    "mdd_p90": "perte maximale en cours de route, 90e centile",
    "cvar95_12m": "CVaR 95 % sur 12 mois",
}


def metric_label_fr(metric: str) -> str:
    if metric in METRIC_LABELS_FR:
        return METRIC_LABELS_FR[metric]
    if metric.startswith("p_loss_gt_"):
        return f"probabilité d'une perte cumulée de plus de {int(metric[-2:])} % à l'horizon"
    if metric.startswith("p_mdd_gt_"):
        return f"probabilité d'une perte maximale de plus de {int(metric[-2:])} % en cours de route"
    return metric


def as_of_date(fitted_through: str) -> str | None:
    """``2026-10`` -> ``2026-10-31``; une date complète est rendue telle quelle; None si illisible."""
    text = (fitted_through or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    match = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


def fact_id(row: Row, suffix: str = "") -> str:
    parts = [row.model_id, row.family, row.mix_id, f"{row.horizon_years}y", row.basis, row.metric]
    base = "scn." + ".".join(_SAFE.sub("_", p) for p in parts)
    return base + (f".{suffix}" if suffix else "")


def trace_id_for(inputs: dict[str, Any], run_id: str | None) -> str:
    digest = hashlib.sha256(json.dumps([inputs, run_id], sort_keys=True, default=str).encode()).hexdigest()
    return f"tr_scn_{digest[:12]}"


def source_of(table: ScenarioTable, row: Row) -> dict[str, Any]:
    source = table.source()
    source["processing"] = (
        f"{source['processing']}; modèle {row.model_id}, famille {row.family}, base {row.basis}, "
        f"{row.n_paths} trajectoires, graine {row.seed}, ajusté jusqu'à {row.fitted_through}"
    )
    return source


def currency_of(table: ScenarioTable, row: Row) -> str | None:
    value = (
        row.currency
        or table.family_info(row.family).get("currency")
        or ("USD" if row.family.startswith("USD") else "CAD")
    )
    return value if value in ("CAD", "USD", "EUR") else None


def row_facts(table: ScenarioTable, row: Row, trace_id: str) -> list[dict[str, Any]]:
    """Trois Facts par ligne : valeur, borne basse et borne haute de l'IC à 90 %."""
    label = metric_label_fr(row.metric)
    context = f"{row.model_id}, {row.family}, {row.mix_id}, {row.horizon_years} ans, {row.basis}"
    common = {
        "unit": "ratio",
        "currency": currency_of(table, row),
        "as_of": as_of_date(row.fitted_through),
        "published": None,
        "status": "HYPOTHESE" if row.hypothese else "FAIT",
        "sources": [source_of(table, row)],
        "trace_id": trace_id,
    }
    return [
        {"fact_id": fact_id(row), "label_fr": f"{label} ({context})", "value": row.value, **common},
        {
            "fact_id": fact_id(row, "ci_lo"),
            "label_fr": f"{label}, IC 90 % borne basse ({context})",
            "value": row.ci_lo,
            **common,
        },
        {
            "fact_id": fact_id(row, "ci_hi"),
            "label_fr": f"{label}, IC 90 % borne haute ({context})",
            "value": row.ci_hi,
            **common,
        },
    ]


def simple_fact(
    fid: str,
    label_fr: str,
    value: Any,
    unit: str,
    trace_id: str,
    table: ScenarioTable | None,
    *,
    status: str = "FAIT",
    currency: str | None = None,
) -> dict[str, Any]:
    """Fact calculé par l'outil lui-même (distance L1, seuil converti, montant en CAD)."""
    source = (
        table.source()
        if table is not None
        else {
            "dataset": "tool:scenario_risk",
            "url": None,
            "licence": None,
            "retrieved_utc": None,
            "sha256": None,
            "processing": None,
        }
    )
    source = {**source, "processing": f"calcul de l'outil {TOOL_NAME} : {label_fr}"}
    return {
        "fact_id": fid,
        "label_fr": label_fr,
        "value": value,
        "unit": unit,
        "currency": currency,
        "as_of": None,
        "published": None,
        "status": status,
        "sources": [source],
        "trace_id": trace_id,
    }


def trace_event(
    *,
    trace_id: str,
    inputs: dict[str, Any],
    started_utc: str,
    ended_utc: str,
    status: str,
    output_summary: str,
    fact_ids: list[str],
    table: ScenarioTable | None,
    family: str | None,
    seed: int | None,
    message: str | None = None,
    parent_id: str | None = None,
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "parent_id": parent_id,
        "agent": AGENT_NAME,
        "tool": TOOL_NAME,
        "inputs": inputs,
        "output_summary": output_summary,
        "fact_ids": fact_ids,
        "started_utc": started_utc,
        "ended_utc": ended_utc,
        "status": status,
        "message": message,
        "data_version": table.data_sha256(family) if table is not None and family else None,
        "code_version": table.code_sha if table is not None else None,
        "seed": seed,
        "model_id": None,
        "otel_trace_id": None,
        "otel_span_id": None,
    }
