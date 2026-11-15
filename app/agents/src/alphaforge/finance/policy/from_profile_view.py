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
    """Valeur de chaque champ du profil : les faits de la vue, puis les champs des dimensions qu'ils n'ont pas."""
    out: dict[str, Any] = {}
    for fact in view.get("facts", []) or []:
        out[fact["field"]] = fact.get("value")
    for dimension in (view.get("dimensions") or {}).values():
        for key, value in (dimension.get("fields") or {}).items():
            out.setdefault(key, value)
    return out


def investor_profile_from_view(
    view: dict[str, Any],
    client_id: str,
    *,
    version: int = 1,
    created_utc: datetime | None = None,
    completeness: dict[str, Any] | None = None,
) -> InvestorProfile:
    """Profil F1 de la vue ; ``completeness`` (sinon celle de la vue) ajoute ses champs manquants à ``missing_info``.

    Le profil est COMPLETE seulement si ``missing_info`` est vide.
    """
    facts = _facts(view)
    horizon_years = _horizon_years(facts)
    goals = _goals(facts, horizon_years)
    risk = view.get("risk") or {}
    tolerance, capacity = risk.get("tolerance"), risk.get("capacity")
    declared_gaps = _declared_gaps(facts, horizon_years, tolerance, capacity)
    debts = _debts(facts)
    preferences = _preferences(facts)
    missing = sorted(set(declared_gaps + _completeness_gaps(completeness or view.get("completeness") or {})))
    return InvestorProfile(
        profile_id=client_id,
        version=version,
        created_utc=created_utc or datetime.now(UTC),
        status="COMPLETE" if not missing else "INCOMPLETE",
        mode="saisi",
        knowledge_level=KNOWLEDGE.get(view.get("knowledge_level") or ""),
        goals=goals,
        tolerance_declared=_score(tolerance),
        capacity_assessed=_score(capacity),
        max_acceptable_loss_cad=_amount_or_none(facts.get("risk_capacity.max_loss_cad")),
        investable_wealth=_amount_or_none(facts.get("context.amount_cad")),
        emergency_fund_months=_float_or_none(facts.get("risk_capacity.emergency_fund")),
        income=_income(facts.get("risk_capacity.income_stability")),
        debts=debts,
        preferences=preferences,
        missing_info=missing,
        consistency_flags=[],
    )


def _horizon_years(facts: dict[str, Any]) -> Any:
    """Horizon en années déclaré, sinon borne basse de la bande d'horizon, sinon None (horizon manquant)."""
    years = facts.get("horizon.horizon_years")
    band = facts.get("horizon.horizon_band")
    if years is None and band in HORIZON_BAND_YEARS:
        return HORIZON_BAND_YEARS[band]
    return years


def _goals(facts: dict[str, Any], horizon_years: Any) -> list[Goal]:
    """Objectif principal (horizon d'un an s'il manque), plus un objectif de liquidité si des retraits sont prévus."""
    goal = facts.get("objective.goal") or "growth"
    goals = [
        Goal(
            goal_id="g-main",
            label=f"objectif : {goal}",
            priority=GOAL_PRIORITY.get(goal, "envie"),
            horizon_years=float(1.0 if horizon_years is None else horizon_years),
        )
    ]
    wealth = facts.get("context.amount_cad")
    withdrawal_pct = facts.get("constraints.withdrawal_pct_12m")
    if withdrawal_pct and wealth:
        goals.append(
            Goal(
                goal_id="g-liquidity",
                label="retraits prévus sous 12 mois",
                priority="besoin",
                horizon_years=1.0,
                amount=_withdrawal_amount(withdrawal_pct, wealth),
            )
        )
    return goals


def _withdrawal_amount(withdrawal_pct: Any, wealth: Any) -> float:
    """Retraits prévus sous 12 mois, en dollars : la part est lue en pourcentage au-dessus de 1, en fraction sinon."""
    if withdrawal_pct > 1:
        return float(withdrawal_pct) / 100 * float(wealth)
    return float(withdrawal_pct) * float(wealth)


def _declared_gaps(facts: dict[str, Any], horizon_years: Any, tolerance: Any, capacity: Any) -> list[str]:
    """Données que l'adaptateur lui-même exige : horizon, catégories de risque, montant et fonds d'urgence."""
    gaps = {
        "horizon": horizon_years is None,
        "risk_tolerance": tolerance not in RISK_SCORE,
        "risk_capacity": capacity not in RISK_SCORE,
        "context.amount_cad": facts.get("context.amount_cad") is None,
        "risk_capacity.emergency_fund": facts.get("risk_capacity.emergency_fund") is None,
    }
    return [name for name, missing in gaps.items() if missing]


def _completeness_gaps(completeness: dict[str, Any]) -> list[str]:
    """Champs que la complétude du profil déclare manquants (``field``, sinon ``label``, sinon « ? »)."""
    return [item.get("field") or item.get("label", "?") for item in completeness.get("missing", []) or []]


def _debts(facts: dict[str, Any]) -> list[Debt]:
    """Dette à taux élevé déclarée (``risk_capacity.high_interest_debt``), au taux annuel de 0,20."""
    balance = facts.get("risk_capacity.high_interest_debt")
    if not balance:
        return []
    return [Debt(label="dette à taux élevé (déclarée)", balance=float(balance), annual_rate=0.20)]


def _preferences(facts: dict[str, Any]) -> Preferences:
    """Exclusions (filtre de valeurs et titres exclus), intérêts (inclinaisons) et ESG exigé dès l'importance 3."""
    value_filters = [
        ValueFilter(
            rule=f"exclure : {exclusion}", per_ticker=dict.fromkeys(EXCLUSION_TICKERS.get(exclusion, []), "exclu")
        )
        for exclusion in facts.get("preferences.exclusions") or []
    ]
    tilts = [INTERESTS[interest] for interest in (facts.get("preferences.interests") or []) if interest in INTERESTS]
    esg_required = (facts.get("preferences.esg_importance") or 0) >= 3
    return Preferences(tilts=tilts, value_filters=value_filters, esg_required=esg_required, reference_currency="CAD")


def _score(category: Any) -> Score | None:
    """Score d'une catégorie de risque de l'app (``RISK_SCORE``), ou None si la catégorie est inconnue."""
    if category not in RISK_SCORE:
        return None
    return Score(value=RISK_SCORE[category], label=category, method="app/profile rules")


def _amount_or_none(value: Any) -> float | None:
    """Montant en dollars ; une valeur vide ou nulle (0) donne None."""
    return float(value) if value else None


def _float_or_none(value: Any) -> float | None:
    """Nombre déclaré, 0 compris ; None s'il est absent."""
    return float(value) if value is not None else None


def _income(stability: Any) -> Income | None:
    """Variabilité du revenu dans le vocabulaire du contrat (``INCOME``), ou None si la stabilité n'est pas déclarée."""
    if not stability:
        return None
    return Income(variability=INCOME.get(stability))


# --------------------------------------------------------------------------- étape 0 (style et sélection)


def _tuple(value) -> tuple[str, ...]:
    """Codes d'une réponse (liste ou valeur seule) en chaînes, sans None ni « none »."""
    if not value:
        return ()
    values = value if isinstance(value, list | tuple) else [value]
    return tuple(str(item) for item in values if item not in (None, "none"))


def _concentrated_sectors(flags: tuple[str, ...], exposures: dict[str, Any]) -> tuple[str, ...]:
    """Secteur déjà concentré du portefeuille existant, quand le constat ``concentration_sector`` est levé.

    ``by_sector`` est une part du portefeuille entier, alors que le constat porte sur les titres individuels :
    on retient le secteur le plus lourd (celui qui a déclenché le constat), sans recalculer de seuil.
    """
    if "concentration_sector" not in flags or not exposures.get("by_sector"):
        return ()
    weights = {
        sector: (weight or 0) for sector, weight in exposures["by_sector"].items() if sector not in (None, "Unknown")
    }
    if not weights:
        return ()
    return (max(sorted(weights), key=lambda sector: weights[sector]),)


def style_inputs_from_view(view: dict[str, Any], portfolio: dict[str, Any] | None = None):
    """Variables du profil court (Brain 3993936) → ``StyleInputs`` de l'étape 0, sans changer ``InvestorProfile``.

    Ne fait que lire : aucune valeur n'est inventée (une variable absente reste vide et ne déclenche rien).
    Chaque champ lu est déclaré dans ``questionnaire.yaml`` (version 2026-11-15.1 pour behavior.hype_*,
    exclusion_strictness, employment_sector, sell_threshold_pct et quiz_*, de poids nul) ; un test le vérifie.
    """
    from alphaforge.finance.strategy.style import StyleInputs

    # g(champ) : valeur du champ, ou None. Nom court gardé : le test des champs déclarés relève ses appels ici.
    g = _facts(view).get
    quiz = {k: str(g(f"knowledge.{k}")) for k in ("quiz_diversification", "quiz_bond_rates") if g(f"knowledge.{k}")}
    existing = portfolio or view.get("portfolio") or {}
    exposures = (existing.get("exposures") or {}) if isinstance(existing, dict) else {}
    flags = _tuple(g("context.portfolio_flags")) or _tuple(exposures.get("flags"))
    concentrated = _concentrated_sectors(flags, exposures)
    amount = g("context.amount_cad")
    esg = g("preferences.esg_importance")
    return StyleInputs(
        goal=g("objective.goal"),
        approach=g("preferences.approach"),
        interests=_tuple(g("preferences.interests")),
        exclusions=_tuple(g("preferences.exclusions")),
        exclusion_strictness=g("preferences.exclusion_strictness"),
        esg_importance=int(esg) if isinstance(esg, int | float) else None,
        employment_sector=g("risk_capacity.employment_sector"),
        currency_preference=g("constraints.currency_preference"),
        account_types=_tuple(g("constraints.account_types")),
        amount_cad=float(amount) if isinstance(amount, int | float) and amount > 0 else None,
        portfolio_flags=flags,
        concentrated_sectors=concentrated,
        knowledge_level=view.get("knowledge_level") or g("knowledge.level"),
        self_assessment=g("knowledge.self_assessment"),
        quiz=quiz,
        products_known=_tuple(g("knowledge.products_known")),
        news_frequency=g("knowledge.news_frequency"),
        hype_reaction=g("behavior.hype_reaction"),
        hype_position_share=g("behavior.hype_position_share"),
        drop_reaction=g("risk_tolerance.drop_reaction"),
        past_drop_behavior=g("risk_tolerance.past_drop_behavior"),
        sell_threshold_pct=g("risk_tolerance.sell_threshold_pct"),
    )
