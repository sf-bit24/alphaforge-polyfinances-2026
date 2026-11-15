"""Adaptateur : ``ProfileView`` du runtime ``profile`` (app/CONTRACTS.md §3.3) → ``InvestorProfile``.

Le profil de Mikael (A1/A2, questionnaire.yaml) est la source ; F1 n'en recalcule pas les catégories,
il les respecte comme bornes :
- ``risk.tolerance`` → ``tolerance_declared`` ; ``risk.capacity`` → ``capacity_assessed`` (F1 ne peut
  jamais dépasser une capacité évaluée, et prend min(tolérance, capacité)) ;
- les montants (patrimoine, perte maximale, fonds d'urgence, dette, retraits) alimentent la règle en
  dollars et les seaux ;
- une donnée absente reste ``None`` et va dans ``missing_info`` : F1 applique alors une borne prudente.
Les bandes d'horizon sont converties vers leur borne BASSE (prudence).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from alphaforge.finance.contracts.profile import Debt, Goal, Income, InvestorProfile, Preferences, Score, ValueFilter

# Milieu des tranches de R du risk_levels.yaml v0.2 (coupures 15/30/45/60/75) : la catégorie de
# l'app tombe dans le niveau correspondant, jamais au-dessus.
RISK_SCORE = {"low": 22.0, "low_medium": 37.0, "medium": 52.0, "medium_high": 67.0, "high": 85.0}
KNOWLEDGE = {"beginner": "debutant", "intermediate": "intermediaire", "advanced": "avance"}
HORIZON_BAND_YEARS = {"lt3": 1.0, "3to10": 3.0, "gt10": 10.0}
INCOME = {
    "very_stable": "stable",
    "stable": "stable",
    "variable": "variable",
    "irregular": "erratique",
    "none": "erratique",
}
GOAL_PRIORITY = {"retirement": "besoin", "project": "besoin", "income": "besoin", "growth": "envie"}
# Exclusions de l'app → tickers de l'univers (secteur Energy du jeu de départ ; aucune autre
# exclusion n'a de titre dans l'univers actuel, la règle est conservée pour la trace).
EXCLUSION_TICKERS = {"fossil_fuels": ["XOM", "CNQ.TO", "ENB.TO"]}
INTERESTS = {"technology": "IA", "crypto": "crypto"}


def _facts(view: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in view.get("facts", []) or []:
        out[f["field"]] = f.get("value")
    for dim in (view.get("dimensions") or {}).values():
        for k, v in (dim.get("fields") or {}).items():
            out.setdefault(k if "." in k else k, v)
    return out


def investor_profile_from_view(
    view: dict[str, Any],
    client_id: str,
    *,
    version: int = 1,
    created_utc: datetime | None = None,
    completeness: dict[str, Any] | None = None,
) -> InvestorProfile:
    f = _facts(view)
    g = lambda key: f.get(key)  # noqa: E731
    missing: list[str] = []

    years = g("horizon.horizon_years")
    if years is None and g("horizon.horizon_band") in HORIZON_BAND_YEARS:
        years = HORIZON_BAND_YEARS[g("horizon.horizon_band")]
    if years is None:
        years, _ = 1.0, missing.append("horizon")
    goal = g("objective.goal") or "growth"
    goals = [
        Goal(
            goal_id="g-main",
            label=f"objectif : {goal}",
            priority=GOAL_PRIORITY.get(goal, "envie"),
            horizon_years=float(years),
        )
    ]
    wealth = g("context.amount_cad")
    pct12 = g("constraints.withdrawal_pct_12m")
    if pct12 and wealth:
        goals.append(
            Goal(
                goal_id="g-liquidity",
                label="retraits prévus sous 12 mois",
                priority="besoin",
                horizon_years=1.0,
                amount=float(pct12) / 100 * float(wealth) if pct12 > 1 else float(pct12) * float(wealth),
            )
        )

    risk = view.get("risk") or {}
    tol, cap = risk.get("tolerance"), risk.get("capacity")
    if tol not in RISK_SCORE:
        missing.append("risk_tolerance")
    if cap not in RISK_SCORE:
        missing.append("risk_capacity")

    debts = []
    if g("risk_capacity.high_interest_debt"):
        debts.append(
            Debt(
                label="dette à taux élevé (déclarée)",
                balance=float(g("risk_capacity.high_interest_debt")),
                annual_rate=0.20,
            )
        )
    if wealth is None:
        missing.append("context.amount_cad")
    if g("risk_capacity.emergency_fund") is None:
        missing.append("risk_capacity.emergency_fund")

    filters = []
    for ex in g("preferences.exclusions") or []:
        filters.append(
            ValueFilter(rule=f"exclure : {ex}", per_ticker={t: "exclu" for t in EXCLUSION_TICKERS.get(ex, [])})
        )
    tilts = [INTERESTS[i] for i in (g("preferences.interests") or []) if i in INTERESTS]
    esg = (g("preferences.esg_importance") or 0) >= 3

    comp = completeness or view.get("completeness") or {}
    missing += [m.get("field") or m.get("label", "?") for m in comp.get("missing", []) or []]
    missing = sorted(set(missing))
    status = "COMPLETE" if not missing else "INCOMPLETE"

    income_stab = g("risk_capacity.income_stability")
    return InvestorProfile(
        profile_id=client_id,
        version=version,
        created_utc=created_utc or datetime.now(UTC),
        status=status,
        mode="saisi",
        knowledge_level=KNOWLEDGE.get(view.get("knowledge_level") or ""),
        goals=goals,
        tolerance_declared=Score(value=RISK_SCORE[tol], label=tol, method="app/profile rules")
        if tol in RISK_SCORE
        else None,
        capacity_assessed=Score(value=RISK_SCORE[cap], label=cap, method="app/profile rules")
        if cap in RISK_SCORE
        else None,
        max_acceptable_loss_cad=float(g("risk_capacity.max_loss_cad")) if g("risk_capacity.max_loss_cad") else None,
        investable_wealth=float(wealth) if wealth else None,
        emergency_fund_months=float(g("risk_capacity.emergency_fund"))
        if g("risk_capacity.emergency_fund") is not None
        else None,
        income=Income(variability=INCOME.get(income_stab)) if income_stab else None,
        debts=debts,
        preferences=Preferences(tilts=tilts, value_filters=filters, esg_required=esg, reference_currency="CAD"),
        missing_info=missing,
        consistency_flags=[],
    )
