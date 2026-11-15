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

import numpy as np

from ..contracts import ConstraintCheck, Fact, PolicySpec, Source, TraceEvent
from ..observability.telemetry import current_ids, traced_tool
from ._engine import bt_metrics
from .analysis import cdar_compounded, cvar_rolling, long_history_returns, loss_2022
from .compile import compile_policy
from .market import ReturnWindow, returns_window

TOL = 1e-4
P = 12


@dataclass(frozen=True)
class JudgeReport:
    verdict: str                               # approuve | refuse
    checks: tuple[ConstraintCheck, ...]
    facts: tuple[Fact, ...]
    trace: TraceEvent
    blocking_violations: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    superseded: dict = field(default_factory=dict)   # rule_id -> rule_id plus strict qui s'applique

    @property
    def approved(self) -> bool:
        return self.verdict == "approuve"


def _source(win: ReturnWindow, processing: str) -> Source:
    return Source(dataset="engine:research/backtest (rendements mensuels)", sha256=win.data_version,
                  processing=processing)


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
    comp = compile_policy(policy, as_of)
    win = window or returns_window(policy, as_of, comp.assets)
    checks: list[ConstraintCheck] = []
    facts: list[Fact] = []
    blocking: list[str] = []
    superseded = _supersession(policy)

    def add(rule_id, desc, derived, limit, value, unit, violated, active, blocking_flag, processing,
            status="FAIT"):
        fid = f"{trace_id}:{rule_id}"
        facts.append(Fact(fact_id=fid, label_fr=desc, value=round(float(value), 6), unit=unit,
                          as_of=win.as_of.date(), status=status, sources=[_source(win, processing)],
                          trace_id=trace_id))
        checks.append(ConstraintCheck(rule_id=rule_id, description_fr=desc, derived_from=derived,
                                      limit=limit, value_fact_id=fid, active=active,
                                      violated=violated, blocking=blocking_flag))
        if violated and blocking_flag:
            blocking.append(rule_id)

    # 1. Structure : actifs connus, exclusions, positivité, somme = 1
    stray = sorted(a for a, x in weights.items() if x > TOL and a not in comp.assets)
    for a in stray:
        reason = policy.excluded.get(a, "hors univers investissable")
        add(f"univers[{a}]", f"{a} n'est pas investissable : {reason}", "policy.universe/excluded",
            0.0, weights[a], "poids", True, False, True, "poids proposé")
    w = np.array([float(weights.get(a, 0.0)) for a in comp.assets])
    neg = float(min(w.min(), 0.0))
    add("positivite", "Aucune vente à découvert (poids minimal)", "simulation long-only", 0.0,
        float(w.min()), "poids", neg < -TOL, False, True, "min des poids")
    total = float(w.sum() + sum(weights.get(a, 0.0) for a in stray))
    add("somme_poids", "Somme des poids", "définition d'un portefeuille", 1.0, total, "poids",
        abs(total - 1) > TOL, True, True, "somme des poids")

    # 2. Limites linéaires (poids par titre, groupes, look-through)
    for row in comp.rows:
        x = float(row.vector @ w)
        lim = row.limit
        for side, bound in (("max", row.hi), ("min", row.lo)):
            if bound is None:
                continue
            viol = x > bound + TOL if side == "max" else x < bound - TOL
            note = f" (remplacée par {superseded[lim.rule_id]}, plus stricte)" if lim.rule_id in superseded else ""
            desc = (lim.description_fr or f"{lim.kind} {side} {row.rule_id}") + note
            add(f"{row.rule_id}:{side}", desc, lim.derived_from, bound, x,
                "part du portefeuille", viol, abs(x - bound) <= TOL, lim.blocking,
                f"{lim.kind} = vecteur·poids" + (" (look-through)" if lim.kind == "exposure" else ""))

    # 3. Limites de risque, mesurées comme l'engine
    r = (win.returns[comp.assets].to_numpy() @ w)
    long = None
    held_w = {a: float(x) for a, x in zip(comp.assets, w, strict=True) if x > 1e-9}

    def long_hist():
        nonlocal long
        if long is None:
            long = long_history_returns(held_w, policy, as_of)
        return long

    def long_desc(lh, what):
        extra = f", proxys {lh.proxies_used}" if lh.proxies_used else ""
        extra += f", + borne Σwδ={lh.excluded_bound:.4f} pour {lh.excluded}" if lh.excluded else ""
        return f"{what}, série longue {lh.start}–{lh.end}{extra}"

    for rr in comp.risk_rows:
        status = "FAIT"
        violated_override = None
        if rr.measure == "CVAR12M":       # contrôle seulement, sur l'historique long
            lh = long_hist()
            val = cvar_rolling(lh.returns.to_numpy(), 12, policy.cvar_beta) + lh.excluded_bound
            what = f"CVaR {policy.cvar_beta:.0%} des rendements composés 12 mois glissants"
            status, proc = lh.status, long_desc(lh, what)
        elif rr.measure == "MDD" and policy.history_proxies:
            lh = long_hist()
            val = bt_metrics.max_drawdown(lh.returns.to_numpy()) + lh.excluded_bound
            status, proc = lh.status, long_desc(lh, "drawdown maximal composé")
        elif rr.measure == "STRESS_2022":
            v2022, proc = loss_2022(held_w, policy.currency)
            if v2022 is None:               # non vérifiable = refus prudent
                val, violated_override = float("nan"), True
            else:
                val = v2022
        else:
            val = _risk_value(rr.measure, r, policy.cvar_beta)
            proc = f"{rr.measure} historique {win.start.date()}–{win.end.date()} ({win.n_obs} mois)"
        viol = violated_override if violated_override is not None else val > rr.hi + TOL
        add(f"{rr.rule_id}:max", rr.limit.description_fr or f"{rr.measure} maximal", rr.limit.derived_from,
            rr.hi, val if val == val else -1.0, "perte (fraction)" if rr.measure != "VOL" else "volatilité annualisée",
            viol, val == val and abs(val - rr.hi) <= TOL, rr.limit.blocking, proc, status)

    verdict = "refuse" if blocking else "approuve"
    otel_tid, otel_sid = current_ids()
    trace = TraceEvent(otel_trace_id=otel_tid, otel_span_id=otel_sid, trace_id=trace_id, agent="judge",
                       tool="portfolio.judge.check",
                       inputs={"policy_id": policy.policy_id, "as_of": str(win.as_of.date()),
                               "weights": {a: round(x, 6) for a, x in weights.items() if abs(x) > 1e-9}},
                       output_summary=f"{verdict} ; {len(blocking)} violation(s) bloquante(s)",
                       fact_ids=[f.fact_id for f in facts], started_utc=started,
                       ended_utc=datetime.now(UTC), status="ok" if not blocking else "refus",
                       data_version=win.data_version)
    return JudgeReport(verdict, tuple(checks), tuple(facts), trace, tuple(blocking),
                       tuple(comp.warnings), superseded)


@traced_tool("portfolio.judge.framed_alternative", lambda r: {"method": r[2], "approved": bool(r[1].approved)})
def framed_alternative(weights: dict[str, float], policy: PolicySpec, as_of):
    """Proposition encadrée après un refus : la plus proche de la demande qui respecte le mandat.

    1) projection sur les limites linéaires ; 2) si une limite de risque reste violée,
    allocation optimale du mandat (F2). Renvoie (poids, rapport du Judge, méthode).
    """
    from .optimizer import optimize, project

    proj = project(policy, weights, as_of)
    rep = check(proj, policy, as_of, trace_id="judge-check-projection")
    if rep.approved:
        return proj, rep, "projection sur les limites du mandat"
    res = optimize(policy, as_of)
    if res.status != "optimal":
        return None, rep, f"aucune alternative réalisable : {res.infeasible_rules}"
    rep2 = check(res.weights, policy, as_of, trace_id="judge-check-optimum")
    return res.weights, rep2, "allocation optimale du mandat (F2)"
