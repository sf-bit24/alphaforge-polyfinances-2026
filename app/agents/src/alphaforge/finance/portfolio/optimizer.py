"""F2 — Optimiseur d'allocation stratégique sous les contraintes d'un PolicySpec.

Formulations convexes (cvxpy, solveur CLARABEL ; HiGHS en repli pour les LP) :
- CVaR historique (Rockafellar-Uryasev 2000), au niveau ``policy.cvar_beta`` ;
- CDaR sur le drawdown **arithmétique** (somme des rendements) — approximation convexe du
  drawdown composé, en général plus prudente ; le Judge (F4) vérifie le drawdown composé ;
- variance Ledoit-Wolf (objectif) ; une limite de volatilité utilise la covariance empirique
  (ddof=1), la même que le contrôle du Judge.

Le LLM ne fixe jamais un poids : il lit ce résultat. Chaque contrainte rend son multiplicateur
dual (« prix » de la contrainte), réutilisé par l'explication.
SIMULATION SEULEMENT — aucun conseil, aucun ordre.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np

from ..contracts import PolicySpec
from ..contracts.policy import CONTROL_ONLY_MEASURES
from ..observability.telemetry import traced_tool
from ._engine import ledoit_wolf
from .compile import CompiledPolicy, compile_policy
from .market import ReturnWindow, returns_window

P = 12
ACTIVE_TOL = 1e-6


@dataclass
class OptimizationResult:
    status: str                                  # optimal | infeasible | error
    weights: dict[str, float]
    objective: str
    risk_measure: str
    risk_value: float | None                     # mesure de l'objectif (mensuelle sauf VOL annualisée)
    expected_return_ann: float | None            # μ utilisé (HYPOTHESE), pas une prévision
    mu_source: str
    duals: dict[str, float] = field(default_factory=dict)
    active: dict[str, bool] = field(default_factory=dict)
    infeasible_rules: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    solver: str | None = None
    as_of: str | None = None
    window: tuple[str, str] | None = None
    n_obs: int | None = None
    data_version: str | None = None
    message: str | None = None


# --------------------------------------------------------------------------- briques convexes

def _cvar_expr(port_ret, beta: float, t: int):
    z = cp.Variable()
    u = cp.Variable(t, nonneg=True)
    return z + cp.sum(u) / ((1 - beta) * t), [u >= -port_ret - z]


def _drawdown_vars(port_ret, t: int):
    """Drawdown arithmétique : dd_t = max_{s≤t} C_s − C_t, avec C_0 = 0."""
    cum = cp.cumsum(port_ret)
    peak = cp.Variable(t)
    cons = [peak >= cum, peak >= 0, peak[1:] >= peak[:-1]]
    return peak - cum, cons


def _cdar_expr(dd, beta: float, t: int):
    z = cp.Variable()
    v = cp.Variable(t, nonneg=True)
    return z + cp.sum(v) / ((1 - beta) * t), [v >= dd - z]


def _mu(policy: PolicySpec, win: ReturnWindow) -> tuple[np.ndarray | None, str]:
    """μ mensuel tiré d'un prior sourcé (CMA, FP Canada…). Jamais de moyenne historique brute :
    sur 5 à 10 ans elle est dominée par quelques gagnants (biais du survivant, erreur d'estimation)."""
    if not policy.expected_returns:
        return None, "aucun : objectif min_risk, aucun rendement attendu n'est calculé"
    missing = [a for a in win.returns.columns if a not in policy.expected_returns]
    if missing:
        raise ValueError(f"expected_returns incomplet : {missing}")
    ann = np.array([policy.expected_returns[a] for a in win.returns.columns])
    return (1 + ann) ** (1 / P) - 1, f"prior : {policy.expected_returns_source}"


# --------------------------------------------------------------------------- problème

def _build(policy: PolicySpec, comp: CompiledPolicy, R: np.ndarray, mu: np.ndarray,
           prev: np.ndarray | None, skip: set[str]):
    t, n = R.shape
    w = cp.Variable(n, name="w")
    named: dict[str, cp.Constraint] = {}
    cons = [cp.sum(w) == 1, w >= 0]
    port = R @ w

    for row in comp.rows:
        if row.parent_rule_id in skip:
            continue
        x = row.vector @ w
        if row.hi is not None:
            named[f"{row.rule_id}:max"] = x <= row.hi
        if row.lo is not None:
            named[f"{row.rule_id}:min"] = x >= row.lo

    sample_cov = np.cov(R, rowvar=False, ddof=1)
    for rr in comp.risk_rows:
        if rr.rule_id in skip or rr.measure in CONTROL_ONLY_MEASURES:
            continue          # CVAR12M : contrôlée par le Judge, resserrer la CVaR mensuelle si besoin
        if rr.measure == "CVAR":
            expr, aux = _cvar_expr(port, policy.cvar_beta, t)
        elif rr.measure == "CDAR":
            dd, aux = _drawdown_vars(port, t)
            expr, aux2 = _cdar_expr(dd, policy.cvar_beta, t)
            aux += aux2
        elif rr.measure == "MDD":
            dd, aux = _drawdown_vars(port, t)
            expr = cp.max(dd)
        else:  # VOL annualisée, covariance empirique (comme le Judge)
            expr = np.sqrt(P) * cp.norm(np.linalg.cholesky(sample_cov + 1e-12 * np.eye(n)).T @ w)
            aux = []
        cons += aux
        named[f"{rr.rule_id}:max"] = expr <= rr.hi

    turnover = None
    if prev is not None:
        turnover = cp.norm1(w - prev)
        if policy.max_turnover is not None:
            named["max_turnover:max"] = turnover <= policy.max_turnover
    cost = (policy.transaction_cost_bps / 1e4) * turnover if turnover is not None else 0

    if policy.risk_measure == "CVAR":
        risk, aux = _cvar_expr(port, policy.cvar_beta, t)
    elif policy.risk_measure == "CDAR":
        dd, aux = _drawdown_vars(port, t)
        risk, aux2 = _cdar_expr(dd, policy.cvar_beta, t)
        aux += aux2
    else:
        lw = ledoit_wolf(R)
        risk, aux = cp.quad_form(w, cp.psd_wrap(lw)), []
    cons += aux

    if policy.objective == "min_risk":
        obj = cp.Minimize(risk + cost)
    else:
        lam = policy.risk_aversion
        penalty = 0.5 * lam * risk if policy.risk_measure == "VARIANCE" else lam * risk
        obj = cp.Maximize(mu @ w - penalty - cost)

    prob = cp.Problem(obj, cons + list(named.values()))
    return prob, w, risk, named


def _solve(prob: cp.Problem) -> str:
    for solver in ("CLARABEL", "HIGHS", "SCS"):
        if solver not in cp.installed_solvers():
            continue
        try:
            prob.solve(solver=solver)
        except (cp.error.SolverError, cp.error.DCPError, ValueError):
            continue
        if prob.status in ("optimal", "optimal_inaccurate", "infeasible", "unbounded"):
            return solver
    return "none"


@traced_tool("portfolio.optimize", lambda r: {"status": r.status, "solver": r.solver or "",
                                              "n_active": sum(r.active.values()), "n_obs": r.n_obs or 0})
def optimize(policy: PolicySpec, as_of, prev_weights: dict[str, float] | None = None,
             window: ReturnWindow | None = None) -> OptimizationResult:
    """Allocation qui minimise le risque (ou maximise l'utilité) sous les limites du mandat."""
    if policy.objective == "max_utility" and not policy.expected_returns:
        raise ValueError("max_utility exige expected_returns (prior sourcé, ex. CMA ou FP Canada)")
    comp = compile_policy(policy, as_of)
    win = window or returns_window(policy, as_of, comp.assets)
    R = win.returns[comp.assets].to_numpy()
    mu, mu_src = _mu(policy, win)
    prev = None
    if prev_weights is not None:
        prev = np.array([float(prev_weights.get(a, 0.0)) for a in comp.assets])

    base = dict(objective=policy.objective, risk_measure=policy.risk_measure, mu_source=mu_src,
                warnings=list(comp.warnings), as_of=str(win.as_of.date()),
                window=(str(win.start.date()), str(win.end.date())), n_obs=win.n_obs,
                data_version=win.data_version)

    prob, w, risk, named = _build(policy, comp, R, mu, prev, skip=set())
    solver = _solve(prob)
    if prob.status not in ("optimal", "optimal_inaccurate") or w.value is None:
        culprits = _diagnose(policy, comp, R, mu, prev)
        return OptimizationResult(status="infeasible" if prob.status == "infeasible" else "error",
                                  weights={}, risk_value=None, expected_return_ann=None,
                                  infeasible_rules=culprits, solver=solver,
                                  message=f"statut solveur : {prob.status}", **base)

    wv = np.clip(w.value, 0, None)
    wv = wv / wv.sum()
    duals, active = {}, {}
    for key, c in named.items():
        d = c.dual_value
        d = float(np.max(np.abs(d))) if d is not None else 0.0
        duals[key] = d
        active[key] = d > ACTIVE_TOL
    risk_value = float(risk.value) if risk.value is not None else None
    if policy.risk_measure == "VARIANCE" and risk_value is not None:
        risk_value = float(np.sqrt(max(risk_value, 0) * P))   # volatilité annualisée (LW)
    exp_ret = float((1 + mu @ wv) ** P - 1) if mu is not None else None
    return OptimizationResult(status="optimal", weights={a: float(x) for a, x in zip(comp.assets, wv, strict=True)},
                              risk_value=risk_value, expected_return_ann=exp_ret, duals=duals,
                              active=active, solver=solver,
                              message=None if prob.status == "optimal" else prob.status, **base)


def _diagnose(policy, comp, R, mu, prev) -> list[str]:
    """Règles dont le retrait (une à une) rend le problème réalisable."""
    rules = sorted({r.parent_rule_id for r in comp.rows}
                   | {r.rule_id for r in comp.risk_rows if r.measure not in CONTROL_ONLY_MEASURES})
    culprits = []
    for rid in rules:
        prob, w, _, _ = _build(policy, comp, R, mu, prev, skip={rid})
        _solve(prob)
        if prob.status in ("optimal", "optimal_inaccurate"):
            culprits.append(rid)
    return culprits


@traced_tool("portfolio.project")
def project(policy: PolicySpec, target: dict[str, float], as_of=None) -> dict[str, float]:
    """Poids admissibles (limites linéaires) les plus proches d'une cible, ex. 1/N ou une demande."""
    comp = compile_policy(policy, as_of)
    n = len(comp.assets)
    w0 = np.array([float(target.get(a, 0.0)) for a in comp.assets])
    w = cp.Variable(n)
    cons = [cp.sum(w) == 1, w >= 0]
    for row in comp.rows:
        if row.hi is not None:
            cons.append(row.vector @ w <= row.hi)
        if row.lo is not None:
            cons.append(row.vector @ w >= row.lo)
    prob = cp.Problem(cp.Minimize(cp.sum_squares(w - w0)), cons)
    _solve(prob)
    if w.value is None:
        raise ValueError(f"projection impossible : {prob.status}")
    wv = np.clip(w.value, 0, None)
    return {a: float(x) for a, x in zip(comp.assets, wv / wv.sum(), strict=True)}
