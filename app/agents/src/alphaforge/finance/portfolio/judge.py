"""F4 — Contrôle des plafonds du Judge : déterministe et non contournable.

Le Judge (LLM) appelle ``check`` et ne peut que lire le verdict : aucune fonction n'accepte de
paramètre de dérogation, et le verdict ne dépend que des contrôles. Toute limite bloquante
violée donne ``refuse`` ; l'agent propose alors l'alternative encadrée (``framed_alternative``).

Règle de composition : quand plusieurs limites visent la même chose (même type, même cible,
même sens), c'est la plus stricte qui s'applique (« le plafond le plus bas l'emporte »). Règle
**inspirée** du barème de profil de l'AMF et de 31-103CP (min(tolérance, capacité)), étendue
aux limites par choix de conception — ce n'est pas une règle réglementaire.
SIMULATION SEULEMENT.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, NamedTuple

import numpy as np

from ..backtest import metrics as bt_metrics
from ..contracts import ConstraintCheck, Fact, PolicySpec, Source, TraceEvent
from ..observability.telemetry import current_ids, traced_tool
from .analysis import (
    MIN_HELD_WEIGHT,
    LongHistory,
    cdar_compounded,
    cvar_rolling,
    long_history_returns,
    loss_2022,
)
from .compile import LinearRow, RiskRow, compile_policy
from .market import ReturnWindow, returns_window
from .scenario_risk import evaluate_prob_loss

TOL = 1e-4


@dataclass(frozen=True)
class JudgeReport:
    verdict: str  # approuve | refuse
    checks: tuple[ConstraintCheck, ...]
    facts: tuple[Fact, ...]
    trace: TraceEvent
    blocking_violations: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    superseded: dict = field(default_factory=dict)  # rule_id -> rule_id plus strict qui s'applique
    # TraceEvent enfants (outil scenario_risk de PROB_LOSS) : leurs Facts sont dans ``facts`` avec leur propre
    # trace_id ; à absorber avec ``trace`` (FactBook.absorb_report). Vide sans limite PROB_LOSS.
    child_traces: tuple[TraceEvent, ...] = ()

    @property
    def approved(self) -> bool:
        return self.verdict == "approuve"


def _source(window: ReturnWindow, processing: str) -> Source:
    return Source(
        dataset="alphaforge.finance.backtest (rendements mensuels, data/long)",
        sha256=window.data_version,
        processing=processing,
    )


@dataclass(frozen=True)
class _Control:
    """Un contrôle avant sa mise en forme : le ConstraintCheck et le Fact qui porte sa valeur."""

    rule_id: str
    description: str
    derived_from: str
    limit: float
    value: float
    processing: str
    unit: str = "poids"
    violated: bool = False
    active: bool = False
    blocking: bool = True
    status: str = "FAIT"
    source: Source | None = None  # None : la fenêtre de rendements ; PROB_LOSS : la table de scénarios


@dataclass
class _Ledger:
    """Contrôles et Facts d'un appel de ``check``, dans l'ordre où ils sont faits."""

    trace_id: str
    window: ReturnWindow
    checks: list[ConstraintCheck] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    child_traces: list[TraceEvent] = field(default_factory=list)  # outil scenario_risk (PROB_LOSS)
    warnings: list[str] = field(default_factory=list)  # avertissements des contrôles (PROB_LOSS)

    @property
    def verdict(self) -> str:
        return "refuse" if self.blocking else "approuve"

    def record(self, control: _Control) -> None:
        fact_id = f"{self.trace_id}:{control.rule_id}"
        self.facts.append(
            Fact(
                fact_id=fact_id,
                label_fr=control.description,
                value=round(float(control.value), 6),
                unit=control.unit,
                as_of=self.window.as_of.date(),
                status=control.status,
                sources=[control.source or _source(self.window, control.processing)],
                trace_id=self.trace_id,
            )
        )
        self.checks.append(
            ConstraintCheck(
                rule_id=control.rule_id,
                description_fr=control.description,
                derived_from=control.derived_from,
                limit=control.limit,
                value_fact_id=fact_id,
                active=control.active,
                violated=control.violated,
                blocking=control.blocking,
            )
        )
        if control.violated and control.blocking:
            self.blocking.append(control.rule_id)

    def trace_event(self, policy: PolicySpec, weights: dict[str, float], started: datetime) -> TraceEvent:
        verdict = self.verdict
        otel_trace_id, otel_span_id = current_ids()
        return TraceEvent(
            otel_trace_id=otel_trace_id,
            otel_span_id=otel_span_id,
            trace_id=self.trace_id,
            agent="judge",
            tool="portfolio.judge.check",
            inputs={
                "policy_id": policy.policy_id,
                "as_of": str(self.window.as_of.date()),
                "weights": {asset: round(x, 6) for asset, x in weights.items() if abs(x) > MIN_HELD_WEIGHT},
            },
            output_summary=f"{verdict} ; {len(self.blocking)} violation(s) bloquante(s)",
            fact_ids=[fact.fact_id for fact in self.facts if fact.trace_id == self.trace_id],
            started_utc=started,
            ended_utc=datetime.now(UTC),
            status="ok" if not self.blocking else "refus",
            data_version=self.window.data_version,
        )


def _finite_weights(weights: dict[str, float]) -> dict[str, float]:
    """Poids fournis en flottants, sans les valeurs non numériques (NaN, infinies)."""
    proposed = {asset: float(x) for asset, x in weights.items()}
    return {asset: x for asset, x in proposed.items() if np.isfinite(x)}


def _rejected_weight(rule_id: str, description: str, derived_from: str, value: float) -> _Control:
    """Poids refusé d'office (non numérique, hors univers) : violation bloquante."""
    return _Control(rule_id, description, derived_from, 0.0, value, "poids proposé", violated=True)


def _check_structure(ledger: _Ledger, weights: dict[str, float], policy: PolicySpec, investable: list[str]) -> None:
    """Structure, sur TOUS les poids fournis (y compris hors univers) : finitude, actifs connus,
    exclusions, positivité, somme = 1. Le vecteur investissable ne sert qu'après."""
    finite = _finite_weights(weights)
    for asset in sorted(weights.keys() - finite.keys()):
        description = f"Poids non numérique pour {asset}"
        ledger.record(_rejected_weight(f"fini[{asset}]", description, "définition d'un portefeuille", -1.0))
    for asset in sorted(name for name, x in finite.items() if abs(x) > TOL and name not in investable):
        description = f"{asset} n'est pas investissable : {policy.excluded.get(asset, 'hors univers investissable')}"
        ledger.record(_rejected_weight(f"univers[{asset}]", description, "policy.universe/excluded", finite[asset]))
    lowest = min(finite.values()) if finite else 0.0
    ledger.record(
        _Control(
            "positivite",
            "Aucune vente à découvert (poids minimal)",
            "simulation long-only",
            0.0,
            float(lowest),
            "min de tous les poids fournis",
            violated=lowest < -TOL,
        )
    )
    total = float(sum(finite.values()))
    ledger.record(
        _Control(
            "somme_poids",
            "Somme des poids",
            "définition d'un portefeuille",
            1.0,
            total,
            "somme des poids",
            violated=abs(total - 1) > TOL,
            active=True,
        )
    )


def _check_linear_limits(
    ledger: _Ledger, rows: list[LinearRow], weights: np.ndarray, superseded: dict[str, str]
) -> None:
    """Limites linéaires (poids par titre, groupes, look-through)."""
    for row in rows:
        share = float(row.vector @ weights)
        limit = row.limit
        note = f" (remplacée par {superseded[limit.rule_id]}, plus stricte)" if limit.rule_id in superseded else ""
        processing = f"{limit.kind} = vecteur·poids" + (" (look-through)" if limit.kind == "exposure" else "")
        for side, bound in (("max", row.hi), ("min", row.lo)):
            if bound is None:
                continue
            ledger.record(
                _Control(
                    f"{row.rule_id}:{side}",
                    (limit.description_fr or f"{limit.kind} {side} {row.rule_id}") + note,
                    limit.derived_from,
                    bound,
                    share,
                    processing,
                    unit="part du portefeuille",
                    violated=share > bound + TOL if side == "max" else share < bound - TOL,
                    active=abs(share - bound) <= TOL,
                    blocking=limit.blocking,
                )
            )


class _Measurement(NamedTuple):
    value: float
    processing: str
    status: str = "FAIT"
    unverifiable: bool = False  # mesure impossible (2022 non couvert) : refus prudent


def _long_description(history: LongHistory, what: str) -> str:
    extra = f", proxys {history.proxies_used}" if history.proxies_used else ""
    extra += f", + borne Σwδ={history.excluded_bound:.4f} pour {history.excluded}" if history.excluded else ""
    return f"{what}, série longue {history.start}–{history.end}{extra}"


@dataclass
class _RiskMeter:
    """Mesure les limites de risque comme l'engine. L'historique long n'est chargé qu'une fois, au premier besoin."""

    policy: PolicySpec
    as_of: Any
    window: ReturnWindow
    returns: np.ndarray  # rendements mensuels du portefeuille sur la fenêtre
    held: dict[str, float]  # poids investissables détenus
    _long_history: LongHistory | None = None

    def long_history(self) -> LongHistory:
        if self._long_history is None:
            self._long_history = long_history_returns(self.held, self.policy, self.as_of)
        return self._long_history

    def measure(self, row: RiskRow) -> _Measurement:
        if row.measure == "CVAR12M":  # contrôle seulement, sur l'historique long
            return self._rolling_cvar_12m()
        if row.measure == "MDD" and self.policy.history_proxies:
            return self._long_drawdown()
        if row.measure == "STRESS_2022":
            return self._loss_2022()
        window = self.window
        value = _risk_value(row.measure, self.returns, self.policy.cvar_beta)
        return _Measurement(
            value, f"{row.measure} historique {window.start.date()}–{window.end.date()} ({window.n_obs} mois)"
        )

    def _rolling_cvar_12m(self) -> _Measurement:
        history = self.long_history()
        series = history.returns.to_numpy()
        # Portefeuille entièrement couvert par des bornes : la borne agrégée est la mesure.
        measured = 0.0 if series.size == 0 else cvar_rolling(series, 12, self.policy.cvar_beta)
        what = f"CVaR {self.policy.cvar_beta:.0%} des rendements composés 12 mois glissants"
        return _Measurement(measured + history.excluded_bound, _long_description(history, what), history.status)

    def _long_drawdown(self) -> _Measurement:
        history = self.long_history()
        series = history.returns.to_numpy()
        value = (0.0 if series.size == 0 else bt_metrics.max_drawdown(series)) + history.excluded_bound
        return _Measurement(value, _long_description(history, "drawdown maximal composé"), history.status)

    def _loss_2022(self) -> _Measurement:
        loss, processing = loss_2022(self.held, self.policy.currency)
        if loss is None:  # non vérifiable = refus prudent
            return _Measurement(float("nan"), processing, unverifiable=True)
        return _Measurement(loss, processing)


def _risk_control(row: RiskRow, measurement: _Measurement) -> _Control:
    value, processing = measurement.value, measurement.processing
    unavailable = not measurement.unverifiable and not np.isfinite(value)
    if unavailable:  # mesure indisponible sur une limite = refus prudent
        processing += " ; MESURE INDISPONIBLE (historique insuffisant) : refus prudent"
    is_measured = value == value  # NaN : aucune valeur à rapporter
    return _Control(
        f"{row.rule_id}:max",
        row.limit.description_fr or f"{row.measure} maximal",
        row.limit.derived_from,
        row.hi,
        value if is_measured else -1.0,
        processing,
        unit="perte (fraction)" if row.measure != "VOL" else "volatilité annualisée",
        violated=measurement.unverifiable or unavailable or value > row.hi + TOL,
        active=is_measured and abs(value - row.hi) <= TOL,
        blocking=row.limit.blocking,
        status=measurement.status,
    )


def _check_prob_loss(ledger: _Ledger, row: RiskRow, held: dict[str, float], policy: PolicySpec) -> None:
    """PROB_LOSS : contrôle seulement, lu dans la table de scénarios précalculée (sans LLM). Non vérifiable = violé ;
    les Facts et le TraceEvent de l'outil suivent le contrôle, avec leur propre trace_id."""
    result = evaluate_prob_loss(row.limit, held, policy, ledger.trace_id)
    selector = row.limit.selector
    description = row.limit.description_fr or (
        f"P(perte > {selector.loss_level:.0%} sur {selector.horizon_years} ans), borne haute IC 90 %"
    )
    ledger.record(
        _Control(
            f"{row.rule_id}:max",
            description,
            row.limit.derived_from,
            row.hi,
            result.value if result.unverifiable is None else -1.0,
            result.processing,
            unit="probabilité (fraction)",
            violated=result.violated,
            active=result.active,
            blocking=row.limit.blocking,
            status="HYPOTHESE",
            source=result.source.model_copy(update={"processing": result.processing}),
        )
    )
    ledger.facts.extend(result.facts)
    ledger.child_traces.extend(result.traces)
    ledger.warnings.extend(result.warnings)


def _risk_value(measure: str, r: np.ndarray, beta: float) -> float:
    if measure == "CVAR":
        return bt_metrics.var_cvar(r, alpha=1 - beta)[1]
    if measure == "CDAR":
        return cdar_compounded(r, beta)
    if measure == "MDD":
        return bt_metrics.max_drawdown(r)
    return bt_metrics.volatility(r)                     # VOL annualisée (ddof=1)


def _supersession(policy: PolicySpec) -> dict[str, str]:
    """Pour chaque limite rendue inutile par une limite plus stricte sur la même cible."""
    groups: dict[tuple, list] = {}
    for lim in policy.limits:
        if not lim.blocking:
            # une limite non bloquante (ex. strat.* de l'étape 0) ne remplace ni ne masque jamais une limite
            # bloquante : elle reste contrôlée et affichée, sans effet sur le verdict
            continue
        key = (lim.kind, json.dumps(lim.selector.model_dump(), sort_keys=True))
        groups.setdefault(key, []).append(lim)
    out = {}
    for lims in groups.values():
        maxes = [lim for lim in lims if lim.max is not None]
        mins = [lim for lim in lims if lim.min is not None]
        if len(maxes) > 1:
            tight = min(maxes, key=lambda lim: lim.max)
            out.update({lim.rule_id: tight.rule_id for lim in maxes if lim is not tight and lim.max > tight.max})
        if len(mins) > 1:
            tight = max(mins, key=lambda lim: lim.min)
            out.update({lim.rule_id: tight.rule_id for lim in mins if lim is not tight and lim.min < tight.min})
    return out


@traced_tool("portfolio.judge.check", lambda r: {"verdict": r.verdict, "n_blocking": len(r.blocking_violations),
                                                   "n_checks": len(r.checks)})
def check(weights: dict[str, float], policy: PolicySpec, as_of,
          window: ReturnWindow | None = None, trace_id: str = "judge-check") -> JudgeReport:
    started = datetime.now(UTC)
    compiled = compile_policy(policy, as_of)
    window = window or returns_window(policy, as_of, compiled.assets)
    ledger = _Ledger(trace_id, window)
    superseded = _supersession(policy)
    _check_structure(ledger, weights, policy, compiled.assets)
    finite = _finite_weights(weights)
    vector = np.array([finite.get(asset, 0.0) for asset in compiled.assets])
    _check_linear_limits(ledger, compiled.rows, vector, superseded)
    portfolio_returns = window.returns[compiled.assets].to_numpy() @ vector
    held = {asset: float(x) for asset, x in zip(compiled.assets, vector, strict=True) if x > MIN_HELD_WEIGHT}
    meter = _RiskMeter(policy, as_of, window, portfolio_returns, held)
    for row in compiled.risk_rows:
        if row.measure == "PROB_LOSS":  # sans limite PROB_LOSS, la table de scénarios n'est jamais lue
            _check_prob_loss(ledger, row, held, policy)
        else:
            ledger.record(_risk_control(row, meter.measure(row)))
    trace = ledger.trace_event(policy, weights, started)
    return JudgeReport(
        ledger.verdict,
        tuple(ledger.checks),
        tuple(ledger.facts),
        trace,
        tuple(ledger.blocking),
        tuple(compiled.warnings) + tuple(ledger.warnings),
        superseded,
        tuple(ledger.child_traces),
    )


@traced_tool(
    "portfolio.judge.framed_alternative",
    lambda result: {"method": result[2], "approved": bool(result[1].approved)},
)
def framed_alternative(weights: dict[str, float], policy: PolicySpec, as_of):
    """Proposition encadrée après un refus : la plus proche de la demande qui respecte le mandat.

    1) projection sur les limites linéaires ; 2) si une limite de risque reste violée,
    allocation optimale du mandat (F2). Renvoie (poids, rapport du Judge, méthode).
    """
    from .optimizer import optimize, project

    projected = project(policy, weights, as_of)
    report = check(projected, policy, as_of, trace_id="judge-check-projection")
    if report.approved:
        return projected, report, "projection sur les limites du mandat"
    result = optimize(policy, as_of)
    if result.status != "optimal":
        return None, report, f"aucune alternative réalisable : {result.infeasible_rules}"
    optimum_report = check(result.weights, policy, as_of, trace_id="judge-check-optimum")
    return result.weights, optimum_report, "allocation optimale du mandat (F2)"
