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
from typing import NamedTuple

import cvxpy as cp
import numpy as np

from ..backtest.strategies import ledoit_wolf
from ..contracts import PolicySpec
from ..contracts.policy import CONTROL_ONLY_MEASURES
from ..observability.telemetry import traced_tool
from .compile import CompiledPolicy, LinearRow, compile_policy
from .market import ReturnWindow, returns_window

MONTHS_PER_YEAR = 12
ACTIVE_TOL = 1e-6
SOLVED = ("optimal", "optimal_inaccurate")


@dataclass
class OptimizationResult:
    status: str  # optimal | infeasible | error
    weights: dict[str, float]
    objective: str
    risk_measure: str
    risk_value: float | None  # mesure de l'objectif (mensuelle sauf VOL annualisée)
    expected_return_ann: float | None  # μ utilisé (HYPOTHESE), pas une prévision
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


def _cvar_expr(portfolio_returns, beta: float, months: int):
    threshold = cp.Variable()  # z : seuil de perte (VaR au niveau β à l'optimum)
    excess = cp.Variable(months, nonneg=True)  # u_t : perte au-delà du seuil
    return threshold + cp.sum(excess) / ((1 - beta) * months), [excess >= -portfolio_returns - threshold]


def _drawdown_vars(portfolio_returns, months: int):
    """Drawdown arithmétique : dd_t = max_{s≤t} C_s − C_t, avec C_0 = 0."""
    cumulative = cp.cumsum(portfolio_returns)
    peak = cp.Variable(months)
    constraints = [peak >= cumulative, peak >= 0, peak[1:] >= peak[:-1]]
    return peak - cumulative, constraints


def _cdar_expr(drawdown, beta: float, months: int):
    threshold = cp.Variable()
    excess = cp.Variable(months, nonneg=True)
    return threshold + cp.sum(excess) / ((1 - beta) * months), [excess >= drawdown - threshold]


def _cdar_of_returns(portfolio_returns, beta: float, months: int):
    drawdown, constraints = _drawdown_vars(portfolio_returns, months)
    cdar, cdar_constraints = _cdar_expr(drawdown, beta, months)
    return cdar, constraints + cdar_constraints


def _expected_returns(policy: PolicySpec, window: ReturnWindow) -> tuple[np.ndarray | None, str]:
    """μ mensuel tiré d'un prior sourcé (CMA, FP Canada…). Jamais de moyenne historique brute :
    sur 5 à 10 ans elle est dominée par quelques gagnants (biais du survivant, erreur d'estimation)."""
    if not policy.expected_returns:
        return None, "aucun : objectif min_risk, aucun rendement attendu n'est calculé"
    missing = [asset for asset in window.returns.columns if asset not in policy.expected_returns]
    if missing:
        raise ValueError(f"expected_returns incomplet : {missing}")
    annual = np.array([policy.expected_returns[asset] for asset in window.returns.columns])
    return (1 + annual) ** (1 / MONTHS_PER_YEAR) - 1, f"prior : {policy.expected_returns_source}"


# --------------------------------------------------------------------------- problème


@dataclass(frozen=True)
class _Holdings:
    """Portefeuille détenu avant l'optimisation."""

    weights: np.ndarray  # sur les actifs investissables
    # Poids détenus hors de l'univers investissable (exclus ou retirés), forcément vendus :
    # ils comptent dans la rotation et dans les frais.
    outside: float

    def turnover(self, weights: cp.Variable) -> cp.Expression:
        return cp.norm1(weights - self.weights) + self.outside


def _holdings(prev_weights: dict[str, float] | None, assets: list[str]) -> _Holdings | None:
    if prev_weights is None:
        return None
    return _Holdings(
        np.array([float(prev_weights.get(asset, 0.0)) for asset in assets]),
        float(sum(abs(float(x)) for asset, x in prev_weights.items() if asset not in assets)),
    )


@dataclass
class _RiskExpressions:
    """Mesures de risque convexes des rendements du portefeuille sur la fenêtre."""

    returns: np.ndarray  # R : mois × actifs investissables
    weights: cp.Variable
    beta: float
    months: int = field(init=False)
    portfolio: cp.Expression = field(init=False)
    sample_cov: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.months = self.returns.shape[0]
        self.portfolio = self.returns @ self.weights
        self.sample_cov = np.atleast_2d(np.cov(self.returns, rowvar=False, ddof=1))

    def limit(self, measure: str) -> tuple[cp.Expression, list[cp.Constraint]]:
        """Mesure d'une limite de risque : CVAR, CDAR, MDD, sinon VOL."""
        if measure == "CVAR":
            return _cvar_expr(self.portfolio, self.beta, self.months)
        if measure == "CDAR":
            return _cdar_of_returns(self.portfolio, self.beta, self.months)
        if measure == "MDD":
            drawdown, constraints = _drawdown_vars(self.portfolio, self.months)
            return cp.max(drawdown), constraints
        # VOL annualisée, covariance empirique (comme le Judge)
        cholesky = np.linalg.cholesky(self.sample_cov + 1e-12 * np.eye(self.returns.shape[1]))
        return np.sqrt(MONTHS_PER_YEAR) * cp.norm(cholesky.T @ self.weights), []

    def objective(self, risk_measure: str) -> tuple[cp.Expression, list[cp.Constraint]]:
        """Mesure de l'objectif : CVAR, CDAR, sinon variance Ledoit-Wolf."""
        if risk_measure == "CVAR":
            return _cvar_expr(self.portfolio, self.beta, self.months)
        if risk_measure == "CDAR":
            return _cdar_of_returns(self.portfolio, self.beta, self.months)
        return cp.quad_form(self.weights, cp.psd_wrap(ledoit_wolf(self.returns))), []


def _linear_constraints(rows: list[LinearRow], weights: cp.Variable, skip: frozenset[str]) -> dict[str, cp.Constraint]:
    named: dict[str, cp.Constraint] = {}
    for row in rows:
        if row.parent_rule_id in skip:
            continue
        share = row.vector @ weights
        if row.hi is not None:
            named[f"{row.rule_id}:max"] = share <= row.hi
        if row.lo is not None:
            named[f"{row.rule_id}:min"] = share >= row.lo
    return named


class _Problem(NamedTuple):
    problem: cp.Problem
    weights: cp.Variable
    risk: cp.Expression
    named: dict[str, cp.Constraint]  # contraintes des limites, par « rule_id:côté » (prix duaux)


@dataclass(frozen=True)
class _Formulation:
    """Données fixes du problème ; chaque ``build`` en tire un problème cvxpy neuf."""

    policy: PolicySpec
    compiled: CompiledPolicy
    returns: np.ndarray  # R : mois × actifs investissables
    expected_returns: np.ndarray | None  # μ mensuel (prior) ; None pour min_risk
    holdings: _Holdings | None

    def build(self, skip: frozenset[str] = frozenset()) -> _Problem:
        """Problème sans les règles de ``skip``."""
        weights = cp.Variable(self.returns.shape[1], name="w")
        constraints = [cp.sum(weights) == 1, weights >= 0]
        risks = _RiskExpressions(self.returns, weights, self.policy.cvar_beta)
        named = _linear_constraints(self.compiled.rows, weights, skip)
        for row in self.compiled.risk_rows:
            if row.rule_id in skip or row.measure in CONTROL_ONLY_MEASURES:
                continue  # CVAR12M : contrôlée par le Judge, resserrer la CVaR mensuelle si besoin
            expr, aux = risks.limit(row.measure)
            constraints += aux
            named[f"{row.rule_id}:max"] = expr <= row.hi
        turnover = self.holdings.turnover(weights) if self.holdings is not None else None
        if turnover is not None and self.policy.max_turnover is not None:
            named["max_turnover:max"] = turnover <= self.policy.max_turnover
        cost = (self.policy.transaction_cost_bps / 1e4) * turnover if turnover is not None else 0
        risk, aux = risks.objective(self.policy.risk_measure)
        constraints += aux
        problem = cp.Problem(self._objective(weights, risk, cost), constraints + list(named.values()))
        return _Problem(problem, weights, risk, named)

    def _objective(self, weights: cp.Variable, risk: cp.Expression, cost) -> cp.Minimize | cp.Maximize:
        if self.policy.objective == "min_risk":
            return cp.Minimize(risk + cost)
        aversion = self.policy.risk_aversion
        penalty = 0.5 * aversion * risk if self.policy.risk_measure == "VARIANCE" else aversion * risk
        return cp.Maximize(self.expected_returns @ weights - penalty - cost)

    def diagnose(self) -> list[str]:
        """Règles dont le retrait (une à une) rend le problème réalisable."""
        rules = sorted(
            {row.parent_rule_id for row in self.compiled.rows}
            | {row.rule_id for row in self.compiled.risk_rows if row.measure not in CONTROL_ONLY_MEASURES}
        )
        culprits = []
        for rule_id in rules:
            problem = self.build(skip=frozenset({rule_id})).problem
            _solve(problem)
            if problem.status in SOLVED:
                culprits.append(rule_id)
        return culprits


def _solve(problem: cp.Problem) -> str:
    for solver in ("CLARABEL", "HIGHS", "SCS"):
        if solver not in cp.installed_solvers():
            continue
        try:
            problem.solve(solver=solver)
        except (cp.error.SolverError, cp.error.DCPError, ValueError):
            continue
        if problem.status in ("optimal", "optimal_inaccurate", "infeasible", "unbounded"):
            return solver
    return "none"


def _normalized(weights: np.ndarray) -> np.ndarray:
    """Poids du solveur sans le bruit numérique négatif, ramenés à une somme de 1."""
    clipped = np.clip(weights, 0, None)
    return clipped / clipped.sum()


def _prices(named: dict[str, cp.Constraint]) -> tuple[dict[str, float], dict[str, bool]]:
    """Prix dual de chaque contrainte nommée (plus grand multiplicateur en valeur absolue) et contraintes actives."""
    duals, active = {}, {}
    for key, constraint in named.items():
        dual = constraint.dual_value
        price = float(np.max(np.abs(dual))) if dual is not None else 0.0
        duals[key] = price
        active[key] = price > ACTIVE_TOL
    return duals, active


def _reported_risk(policy: PolicySpec, risk: cp.Expression) -> float | None:
    if risk.value is None:
        return None
    value = float(risk.value)
    if policy.risk_measure == "VARIANCE":
        return float(np.sqrt(max(value, 0) * MONTHS_PER_YEAR))  # volatilité annualisée (LW)
    return value


def _run_details(policy: PolicySpec, compiled: CompiledPolicy, window: ReturnWindow, mu_source: str) -> dict:
    """Champs du résultat communs à l'optimum et à l'échec."""
    return {
        "objective": policy.objective,
        "risk_measure": policy.risk_measure,
        "mu_source": mu_source,
        "warnings": list(compiled.warnings),
        "as_of": str(window.as_of.date()),
        "window": (str(window.start.date()), str(window.end.date())),
        "n_obs": window.n_obs,
        "data_version": window.data_version,
    }


@traced_tool(
    "portfolio.optimize",
    lambda result: {
        "status": result.status,
        "solver": result.solver or "",
        "n_active": sum(result.active.values()),
        "n_obs": result.n_obs or 0,
    },
)
def optimize(
    policy: PolicySpec,
    as_of,
    prev_weights: dict[str, float] | None = None,
    window: ReturnWindow | None = None,
) -> OptimizationResult:
    """Allocation qui minimise le risque (ou maximise l'utilité) sous les limites du mandat."""
    if policy.objective == "max_utility" and not policy.expected_returns:
        raise ValueError("max_utility exige expected_returns (prior sourcé, ex. CMA ou FP Canada)")
    compiled = compile_policy(policy, as_of)
    window = window or returns_window(policy, as_of, compiled.assets)
    returns = window.returns[compiled.assets].to_numpy()
    expected, mu_source = _expected_returns(policy, window)
    formulation = _Formulation(policy, compiled, returns, expected, _holdings(prev_weights, compiled.assets))
    common = _run_details(policy, compiled, window, mu_source)
    built = formulation.build()
    solver = _solve(built.problem)
    status = built.problem.status
    if status not in SOLVED or built.weights.value is None:
        culprits = formulation.diagnose()
        return OptimizationResult(
            status="infeasible" if status == "infeasible" else "error",
            weights={},
            risk_value=None,
            expected_return_ann=None,
            infeasible_rules=culprits,
            solver=solver,
            message=f"statut solveur : {status}",
            **common,
        )
    weights = _normalized(built.weights.value)
    duals, active = _prices(built.named)
    return OptimizationResult(
        status="optimal",
        weights={asset: float(x) for asset, x in zip(compiled.assets, weights, strict=True)},
        risk_value=_reported_risk(policy, built.risk),
        expected_return_ann=float((1 + expected @ weights) ** MONTHS_PER_YEAR - 1) if expected is not None else None,
        duals=duals,
        active=active,
        solver=solver,
        message=None if status == "optimal" else status,
        **common,
    )


@traced_tool("portfolio.project")
def project(policy: PolicySpec, target: dict[str, float], as_of=None) -> dict[str, float]:
    """Poids admissibles (limites linéaires) les plus proches d'une cible, ex. 1/N ou une demande."""
    compiled = compile_policy(policy, as_of)
    target_weights = np.array([float(target.get(asset, 0.0)) for asset in compiled.assets])
    weights = cp.Variable(len(compiled.assets))
    constraints = [cp.sum(weights) == 1, weights >= 0]
    for row in compiled.rows:
        if row.hi is not None:
            constraints.append(row.vector @ weights <= row.hi)
        if row.lo is not None:
            constraints.append(row.vector @ weights >= row.lo)
    problem = cp.Problem(cp.Minimize(cp.sum_squares(weights - target_weights)), constraints)
    _solve(problem)
    if weights.value is None:
        raise ValueError(f"projection impossible : {problem.status}")
    return {asset: float(x) for asset, x in zip(compiled.assets, _normalized(weights.value), strict=True)}
