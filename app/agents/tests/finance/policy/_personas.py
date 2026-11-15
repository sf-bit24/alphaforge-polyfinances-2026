"""Profils de test (entrees HYPOTHESE de app/agents/scripts/calibration/review/persona_v02.py). Fiction, simulation."""

from __future__ import annotations

from datetime import UTC, date, datetime

from alphaforge.finance.contracts.profile import (
    Bias,
    Debt,
    Goal,
    HouseholdMember,
    Income,
    InvestorProfile,
    Pension,
    Preferences,
    Score,
)

AS_OF = date(2026, 9, 30)
CREATED = datetime(2026, 11, 14, tzinfo=UTC)


def amira(**kw) -> InvestorProfile:
    # persona_v02 : T=20, E=4 / Ereq=3, q=0, cI=1, dette 12 000 / revenu 95 000 ; tol (80,.7,72,.8,60) ; crypto tilt
    base = dict(
        profile_id="amira",
        created_utc=CREATED,
        status="COMPLETE",
        mode="persona",
        age=29,
        knowledge_level="intermediaire",
        goals=[Goal(goal_id="long_terme", label="croissance long terme", priority="souhait", horizon_years=20)],
        tolerance_declared=Score(value=80, confidence=0.7),
        tolerance_tested=Score(value=72, confidence=0.8),
        composure=Score(value=60),
        investable_wealth=150_000,
        monthly_expenses=4_000,
        emergency_fund_months=4,
        income=Income(annual_amount=95_000, variability="stable"),
        debts=[Debt(label="pret etudiant", balance=12_000, annual_rate=0.05)],
        preferences=Preferences(tilts=["crypto"]),
    )
    base.update(kw)
    return InvestorProfile(**base)


def mateo(**kw) -> InvestorProfile:
    # persona_v02 : T=9, E=5 / Ereq=3, dette 18 000 / revenu 160 000 ; tol (55,.7,50,.8,55) ; l_decl 0.25 ;
    # menage : conjoint plus prudent (regle min_tolerance)
    base = dict(
        profile_id="mateo",
        created_utc=CREATED,
        status="COMPLETE",
        mode="persona",
        age=41,
        knowledge_level="intermediaire",
        goals=[Goal(goal_id="etudes", label="etudes des enfants", priority="envie", horizon_years=9)],
        household=[HouseholdMember(role="conjoint", age=40, tolerance=Score(value=45, confidence=0.6))],
        household_rule="min_tolerance",
        tolerance_declared=Score(value=55, confidence=0.7),
        tolerance_tested=Score(value=50, confidence=0.8),
        composure=Score(value=55),
        max_acceptable_loss_pct=0.25,
        investable_wealth=400_000,
        monthly_expenses=9_000,
        emergency_fund_months=5,
        income=Income(annual_amount=160_000, variability="stable"),
        debts=[Debt(label="pret auto", balance=18_000, annual_rate=0.06)],
    )
    base.update(kw)
    return InvestorProfile(**base)


def robert(**kw) -> InvestorProfile:
    # persona_v02 : T=7, E=8 / Ereq=6 (retraite), q = 30 000 / 900 000, cI = 0.3 + 0.7*3400/6500 ;
    # tol (35,.7,52,.6,30) ; l_decl = 120 000 / 900 000 = 0.133 ; demande 50 000 $
    base = dict(
        profile_id="robert",
        created_utc=CREATED,
        status="COMPLETE",
        mode="persona",
        age=62,
        knowledge_level="intermediaire",
        goals=[
            Goal(
                goal_id="decaissement",
                label="revenu de retraite",
                priority="besoin",
                horizon_years=7,
                recurring_withdrawal=30_000,
            )
        ],
        tolerance_declared=Score(value=35, confidence=0.7),
        tolerance_tested=Score(value=52, confidence=0.6),
        composure=Score(value=30),
        max_acceptable_loss_cad=120_000,
        investable_wealth=900_000,
        monthly_expenses=6_500,
        emergency_fund_months=8,
        pensions=[Pension(kind="PD", monthly_amount=3_400)],
    )
    base.update(kw)
    return InvestorProfile(**base)


def bias(label: str, kind: str = "emotionnel") -> Bias:
    return Bias(kind_label=label, kind=kind, evidence="test")
