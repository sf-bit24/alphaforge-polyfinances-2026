"""F1 — compilateur deterministe InvestorProfile -> PolicySpec (risk_levels.yaml v0.2).

Porte en code de bibliotheque la logique de app/agents/scripts/calibration/review/expand.py (emit) et
persona_v02.py (capacite, tolerance, regle des dollars). Chaque nombre derive est inscrit dans
``trace`` avec son chemin YAML ; chaque Limit porte ``source = risk_levels.yaml@<ver>#<chemin>``.
SIMULATION SEULEMENT — jamais un conseil financier.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, NamedTuple

import yaml

from alphaforge.finance.contracts import ExposureOverride, HistoryProxy, Limit, PolicySpec, Selector
from alphaforge.finance.contracts.profile import Debt, Goal, InvestorProfile, ProfileStatus, Score

from . import envelope
from .adapter import QuestionnaireScores, apply_questionnaire
from .emphasis import compute_emphasis
from .models import CompileResult, DecisionKind, RequestView, SpecificRequest

LV = ["N0", "N1", "N2", "N3", "N4", "N5"]  # niveaux du mandat, du plus prudent au plus risque
DEFAULT_YAML = Path(__file__).with_name("risk_levels.yaml")
EPSILON = 1e-12  # marge des comparaisons entre flottants
DAYS_PER_YEAR = 365.25

# Constantes absentes du YAML sous forme de cle (presentes dans le texte du YAML) : tracees comme telles.
MU_RECOVERY = 0.04  # risk_levels.yaml#dollar_rule.l_cap : « mu_recovery 0.04 (HYPOTHESE) »
CAPACITY_COMPONENT_FLOOR = 0.05  # risk_levels.yaml#capacity : « C = 100 * prod_k max(c_k, 0.05)^a_k »
RETIRED_INCOME_FLOOR = 0.3  # risk_levels.yaml#capacity.income_stability.retired : « 0.3 + 0.7*pi »
RETIRED_PENSION_WEIGHT = 0.7
NEUTRAL_DEBT_CAPACITY = 0.5  # cL sans revenu connu mais avec des dettes (persona.py)
SENIOR_AGE = 55  # risk_levels.yaml#capacity.emergency_req_months.retraite_ou_55plus
UNDERFUNDED_NEED_HORIZON_YEARS = 5  # un besoin sous-finance est a 5 ans ou moins (README, ecart 7)
UNKNOWN_HORIZON_YEARS = 99  # horizon_years absent ou nul : l'objectif ne compte pas comme « a 5 ans ou moins »
WITHDRAWAL_RESERVE_HORIZON_YEARS = 5  # risk_levels.yaml#buckets : retraits « debutant dans <= 5 ans -> seau N1 »
WITHDRAWAL_RESERVE_LEVEL = "N1"
# Formules de risk_levels.yaml#composition, que le YAML donne en texte.
ETF_EQUITY_EACH_FLOOR = 0.10  # etf_equity_each_max : « max(0.10, 0.6 * e_cap) »
ETF_EQUITY_EACH_SHARE = 0.6
ETF_BOND_EACH_SHARE = 0.65  # etf_bond_each_max : « ceil_5%(0.65 * (1 - e_min)) »
ETF_BOND_EACH_STEP = 0.05
CASH_LIKE_SHARE = 0.5  # cash_like_max : « N0: 1.0 ; sinon 0.5 * (1 - e_min) »

# Classes d'actifs du starter (copie de assets.csv du moteur alphaforge.finance.backtest, colonne asset_class),
# utilisees seulement pour classer une SpecificRequest ; surchargeables via ``asset_classes``.
STARTER_ASSET_CLASSES = {
    **dict.fromkeys(("XIU.TO", "SPY", "QQQ", "ESGV"), "etf_equity"),
    **dict.fromkeys(("XBB.TO", "ZST.TO", "AGG", "TLT"), "etf_bond"),
    "GLD": "commodity",
    "BTC-USD": "crypto",
    "ETH-USD": "crypto",
    **dict.fromkeys(
        (
            "RY.TO",
            "TD.TO",
            "MFC.TO",
            "ENB.TO",
            "CNQ.TO",
            "CNR.TO",
            "FTS.TO",
            "ATD.TO",
            "SHOP.TO",
            "CSU.TO",
            "AAPL",
            "MSFT",
            "NVDA",
            "GOOGL",
            "AMZN",
            "TSLA",
            "JPM",
            "JNJ",
            "PG",
            "XOM",
        ),
        "equity_single",
    ),
}
CRYPTO_ETF_CLASSES = {"etf_crypto"}  # aucun dans le starter -> crypto « etf_only » = 0 pour un debutant
CRYPTO_TILT_WORDS = ("crypto", "bitcoin", "btc", "ether", "eth")
MORTGAGE_WORDS = ("hypoth", "mortgage")  # une hypotheque est reconnue a son libelle (README, ecart 7)
# Budget de risque d'un niveau -> colonne de l'enveloppe ENV(e) qui le mesure.
BUDGET_ENVELOPE_COLUMNS = {"vol": "vol", "cvar_m": "cvar95_m", "cvar_12m": "cvar95_12m", "mdd": "mdd", "s2022": "y2022"}


# --------------------------------------------------------------------------- utilitaires


def _clip(x: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, x))


def floor_step(x: float, s: float = 0.0025) -> float:
    """Arrondi inferieur de x au multiple du pas s."""
    return round(math.floor(round(x / s, 9)) * s, 6)


def ceil_step(x: float, s: float) -> float:
    """Arrondi superieur de x au multiple du pas s."""
    return round(math.ceil(round(x / s, 9)) * s, 6)


def _normalize_label(label: str) -> str:
    """Minuscules sans accents ; tirets et espaces deviennent des tirets bas."""
    ascii_label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    return ascii_label.replace("-", "_").replace(" ", "_")


def _bias_key(label: str) -> str | None:
    normalized = _normalize_label(label)
    if "fomo" in normalized:
        return "FOMO"
    if "surconf" in normalized or "overconf" in normalized:
        return "surconfiance"
    if "aversion" in normalized or "loss_aver" in normalized:
        return "aversion_perte"
    if "familiar" in normalized or "home_bias" in normalized:
        return "familiarite"
    return None


@lru_cache(maxsize=8)
def _load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _level_index(level: str) -> int:
    return LV.index(level)


class _CompileContext:
    """Regles de risk_levels.yaml et journal d'une compilation : regles appliquees, valeurs prudentes retenues."""

    def __init__(self, risk_levels: dict):
        self.risk_levels = risk_levels
        self.version = str(risk_levels["version"])
        self.trace: list[dict[str, Any]] = []
        self.missing_defaults: list[str] = []

    def source(self, path: str) -> str:
        return f"risk_levels.yaml@{self.version}#{path}"

    def record(self, rule: str, inputs: dict, output: Any, path: str) -> None:
        """Inscrit une regle appliquee dans la trace ; un ``path`` sans nom de fichier vise risk_levels.yaml."""
        self.trace.append(
            {
                "rule": rule,
                "inputs": inputs,
                "output": output,
                "yaml_path": path
                if path.startswith(("risk_levels", "envelope", "emphasis", "profile", "questionnaire"))
                else self.source(path),
            }
        )

    def use_default(self, field: str, value: Any, reason: str) -> Any:
        """Note la valeur prudente retenue pour un champ absent du profil, et la rend."""
        self.missing_defaults.append(f"{field} absent -> {value!r} ({reason})")
        return value


# --------------------------------------------------------------------------- faits du profil


def _goal_horizon(goal: Goal, as_of: date) -> float:
    horizons = []
    if goal.horizon_years is not None:
        horizons.append(float(goal.horizon_years))
    if goal.target_date is not None:
        horizons.append(max(0.0, (goal.target_date - as_of).days / DAYS_PER_YEAR))
    return min(horizons)


def _is_retired(profile: InvestorProfile) -> bool:
    has_no_income = profile.income is None or not profile.income.annual_amount
    return has_no_income and bool(profile.pensions)


def _covered_goal_ids(options: dict) -> set[str]:
    """Objectifs finances par la poche liquide du questionnaire : hors du seau risque (un seul chemin)."""
    return options.get("covered_goal_ids") or set()


class _GoalPlacement(NamedTuple):
    """Place d'un objectif : son seau prudent eventuel, et son horizon s'il reste dans le seau risque."""

    bucket: dict[str, Any] | None
    risk_horizon_years: float | None


def _liquid_pocket_bucket(options: dict) -> dict[str, Any]:
    return {
        "goal_id": "poche_liquide",
        "level_cap": options["bucket_level"],
        "amount": options["liquid_pocket_cad"],
        "covers": sorted(_covered_goal_ids(options)),
        "kind": "poche_liquide",
        "source": "questionnaire_adapter.yaml#liquid_pocket",
    }


def _prudent_bucket(goal: Goal, horizon_years: float, context: _CompileContext) -> dict[str, Any] | None:
    """Seau de l'objectif selon buckets.rules (la regle au plafond le plus strict), ou None si aucune ne le vise."""
    matches = [
        (index, rule)
        for index, rule in enumerate(context.risk_levels["buckets"]["rules"])
        if rule["priority"] == goal.priority.value and horizon_years <= rule["T_max"]
    ]
    if not matches:
        return None
    index, rule = min(matches, key=lambda match: _level_index(match[1]["level_cap"]))
    bucket = {
        "goal_id": goal.goal_id,
        "horizon_years": round(horizon_years, 4),
        "level_cap": rule["level_cap"],
        "amount": goal.amount,
        "source": context.source(f"buckets.rules[{index}]"),
    }
    context.record(
        "buckets.goal",
        {"goal_id": goal.goal_id, "priority": goal.priority.value, "horizon_years": horizon_years},
        rule["level_cap"],
        f"buckets.rules[{index}]",
    )
    return bucket


def _withdrawal_reserve(goal: Goal, horizon_years: float, context: _CompileContext) -> _GoalPlacement:
    """Reserve N1 de quelques annees de retraits ; l'horizon de l'objectif dans le seau risque recule d'autant."""
    reserve_years = context.risk_levels["buckets"]["withdrawal_reserve_years"]
    bucket = {
        "goal_id": goal.goal_id,
        "horizon_years": round(horizon_years, 4),
        "level_cap": WITHDRAWAL_RESERVE_LEVEL,
        "amount": reserve_years * goal.recurring_withdrawal,
        "kind": "reserve_retraits",
        "source": context.source("buckets.withdrawal_reserve_years"),
    }
    risk_horizon_years = horizon_years + reserve_years
    context.record(
        "buckets.withdrawal_reserve",
        {"goal_id": goal.goal_id, "recurring_withdrawal": goal.recurring_withdrawal},
        {"reserve_cad": reserve_years * goal.recurring_withdrawal, "risk_horizon_years": risk_horizon_years},
        "buckets.withdrawal_reserve_years",
    )
    return _GoalPlacement(bucket, risk_horizon_years)


def _place_goal(goal: Goal, as_of: date, context: _CompileContext, options: dict) -> _GoalPlacement:
    """Range l'objectif dans un seau prudent ou dans le seau risque (une reserve de retraits en repousse l'horizon)."""
    horizon_years = _goal_horizon(goal, as_of)
    bucket = _prudent_bucket(goal, horizon_years, context)
    if bucket is not None:
        return _GoalPlacement(bucket, None)
    pocket_reserve_years = options.get("sequence_reserve_years")
    if goal.recurring_withdrawal and pocket_reserve_years:  # reserve deja dans la poche liquide du questionnaire
        risk_horizon_years = horizon_years + pocket_reserve_years
        context.record(
            "buckets.withdrawal_reserve",
            {"goal_id": goal.goal_id, "sequence_reserve_years": pocket_reserve_years},
            {"risk_horizon_years": risk_horizon_years},
            "questionnaire_adapter.yaml#liquid_pocket",
        )
        return _GoalPlacement(None, risk_horizon_years)
    if goal.recurring_withdrawal and horizon_years <= WITHDRAWAL_RESERVE_HORIZON_YEARS:
        return _withdrawal_reserve(goal, horizon_years, context)
    return _GoalPlacement(None, horizon_years)


def _horizon_and_buckets(
    profile: InvestorProfile, as_of: date, context: _CompileContext, options: dict
) -> tuple[float, str | None, list[dict[str, Any]]]:
    """T du seau risque, plafond de niveau impose par les seaux (si tous les objectifs sont « seau »)."""
    covered = _covered_goal_ids(options)
    placements = [_place_goal(goal, as_of, context, options) for goal in profile.goals if goal.goal_id not in covered]
    buckets = [_liquid_pocket_bucket(options)] if options.get("liquid_pocket_cad") else []
    buckets += [placement.bucket for placement in placements if placement.bucket is not None]
    risk_horizons = [
        placement.risk_horizon_years for placement in placements if placement.risk_horizon_years is not None
    ]
    if risk_horizons:
        risk_horizon_years = min(risk_horizons)
        level_cap = None
    else:  # tous les objectifs sont des seaux prudents : le mandat entier suit le plus strict
        risk_horizon_years = min(_goal_horizon(goal, as_of) for goal in profile.goals if goal.goal_id not in covered)
        level_cap = min((placement.bucket["level_cap"] for placement in placements), key=_level_index)
    context.record(
        "horizon.T_risk",
        {"goal_horizons": {goal.goal_id: round(_goal_horizon(goal, as_of), 4) for goal in profile.goals}},
        round(risk_horizon_years, 4),
        "horizon_cap",
    )
    return risk_horizon_years, level_cap, buckets


# --------------------------------------------------------------------------- capacite


def _horizon_capacity(horizon_years: float, context: _CompileContext) -> float:
    """Composante H : nulle a T_zero, pleine a T_full, logarithmique entre les deux."""
    bounds = context.risk_levels["capacity"]["horizon"]
    capacity = (
        _clip(math.log(horizon_years / bounds["T_zero"]) / math.log(bounds["T_full"] / bounds["T_zero"]))
        if horizon_years > 0
        else 0.0
    )
    context.record("capacity.H", {"T": horizon_years}, capacity, "capacity.horizon")
    return capacity


def _income_variability(profile: InvestorProfile) -> str | None:
    return profile.income.variability if profile.income else None


def _required_emergency_months(profile: InvestorProfile, context: _CompileContext, *, is_retired: bool) -> float:
    """Ereq : mois de reserve exiges selon la variabilite du revenu, la retraite et l'age (55 ans et plus)."""
    required = context.risk_levels["capacity"]["emergency_req_months"]
    variability = _income_variability(profile)
    if is_retired:
        months = required["retraite_ou_55plus"]
    elif variability is None:
        months = context.use_default(
            "income.variability", max(required.values()), "capacity.emergency_req_months : plus exigeant"
        )
    else:
        months = required[variability]
    if profile.age is not None and profile.age >= SENIOR_AGE:
        months = max(months, required["retraite_ou_55plus"])
    return months


def _emergency_capacity(
    profile: InvestorProfile, required_months: float, context: _CompileContext, *, is_retired: bool
) -> tuple[float, float]:
    """Mois de reserve d'urgence retenus (E, nul si le profil n'en dit rien) et composante E."""
    months = profile.emergency_fund_months
    if months is None:
        months = context.use_default("emergency_fund_months", 0.0, "prudent : aucune reserve supposee")
    capacity = _clip(months / required_months)
    context.record(
        "capacity.E",
        {"emergency_fund_months": months, "required_months": required_months, "retired": is_retired},
        capacity,
        "capacity.emergency_req_months",
    )
    return months, capacity


def _withdrawal_capacity(
    profile: InvestorProfile, wealth: float | None, context: _CompileContext, options: dict
) -> tuple[float, float]:
    """Taux de retrait q des objectifs du seau risque et composante D."""
    rules = context.risk_levels["capacity"]["withdrawal"]
    covered = _covered_goal_ids(options)
    annual_withdrawals = sum(goal.recurring_withdrawal or 0.0 for goal in profile.goals if goal.goal_id not in covered)
    if annual_withdrawals and not wealth:
        rate = context.use_default("investable_wealth (taux de retrait)", rules["q_max"], "q = q_max, prudent")
    else:
        rate = annual_withdrawals / wealth if wealth else 0.0
    capacity = _clip(1 - rules["phi_dep"] * rate / rules["q_max"])
    context.record(
        "capacity.D",
        {"annual_withdrawals": annual_withdrawals, "W": wealth, "q": rate},
        capacity,
        "capacity.withdrawal",
    )
    return rate, capacity


def _loss_capacity(withdrawal_rate: float, horizon_years: float, context: _CompileContext) -> float:
    """l_cap : perte absorbable, bornee par le taux de retrait et par le temps de recuperation."""
    q_max = context.risk_levels["capacity"]["withdrawal"]["q_max"]
    loss_capacity = max(0.0, min(1 - withdrawal_rate / q_max, 1 - (1 + MU_RECOVERY) ** (-horizon_years)))
    context.record(
        "dollar_rule.l_cap",
        {"q": withdrawal_rate, "q_max": q_max, "T": horizon_years, "mu_recovery": MU_RECOVERY},
        loss_capacity,
        "dollar_rule.l_cap",
    )
    return loss_capacity


def _absorption_capacity(loss_capacity: float, context: _CompileContext) -> float:
    capacity = _clip(loss_capacity / context.risk_levels["capacity"]["absorption_full"])
    context.record("capacity.A", {"l_cap": loss_capacity}, capacity, "capacity.absorption_full")
    return capacity


def _retired_income_capacity(profile: InvestorProfile, context: _CompileContext) -> float:
    """Stabilite du revenu d'un retraite : 0.3 + 0.7 * pi, ou pi est la part des depenses que couvrent les rentes."""
    monthly_pensions = sum(pension.monthly_amount or 0.0 for pension in profile.pensions)
    monthly_expenses = profile.monthly_expenses
    if monthly_expenses:
        pension_coverage = _clip(monthly_pensions / monthly_expenses)
    else:
        pension_coverage = context.use_default("monthly_expenses (couverture des rentes)", 0.0, "pi = 0")
    capacity = RETIRED_INCOME_FLOOR + RETIRED_PENSION_WEIGHT * pension_coverage
    context.record(
        "capacity.I.retired",
        {"pension_monthly": monthly_pensions, "monthly_expenses": monthly_expenses, "pi": pension_coverage},
        capacity,
        "capacity.income_stability.retired",
    )
    return capacity


def _income_capacity(profile: InvestorProfile, context: _CompileContext, *, is_retired: bool) -> float:
    """Composante I : stabilite du revenu, reduite quand l'investisseur detient des titres de son employeur."""
    rules = context.risk_levels["capacity"]
    variability = _income_variability(profile)
    if is_retired:
        capacity = _retired_income_capacity(profile, context)
    elif variability is None:
        capacity = rules["income_stability"]["missing"]
        context.record("capacity.I", {"variability": None}, capacity, "capacity.income_stability.missing")
    else:
        capacity = rules["income_stability"][variability]
        context.record("capacity.I", {"variability": variability}, capacity, f"capacity.income_stability.{variability}")
    if profile.employer_equity:
        capacity *= rules["employer_equity_haircut"]
        context.record(
            "capacity.I.employer_haircut",
            {"employer_equity": len(profile.employer_equity)},
            capacity,
            "capacity.employer_equity_haircut",
        )
    return capacity


def _is_mortgage(debt: Debt) -> bool:
    return any(word in _normalize_label(debt.label) for word in MORTGAGE_WORDS)


def _debt_capacity(profile: InvestorProfile, context: _CompileContext) -> float:
    """Composante L : dette hors hypotheque rapportee au revenu annuel (les rentes, a defaut de revenu)."""
    non_mortgage_debt = sum(debt.balance for debt in profile.debts if not _is_mortgage(debt))
    annual_income = (
        profile.income.annual_amount if profile.income and profile.income.annual_amount else 0.0
    ) or 12 * sum(pension.monthly_amount or 0.0 for pension in profile.pensions)
    if annual_income:
        capacity = _clip(1 - non_mortgage_debt / annual_income)
    elif non_mortgage_debt:
        capacity = context.use_default(
            "income.annual_amount", NEUTRAL_DEBT_CAPACITY, "capacity : cL neutre 0.5 (persona.py)"
        )
    else:
        capacity = 1.0
    context.record(
        "capacity.L",
        {"non_mortgage_debt": non_mortgage_debt, "annual_income": annual_income},
        capacity,
        "capacity.weights.L",
    )
    return capacity


class _HardCap(NamedTuple):
    """Plafond dur que le profil declenche : son nom, sa valeur, les faits traces et son chemin YAML."""

    name: str
    cap: float
    inputs: dict[str, Any]
    yaml_path: str


def _is_underfunded_need(goal: Goal, wealth: float | None) -> bool:
    """Besoin a 5 ans ou moins (selon horizon_years) dont le montant depasse W."""
    return bool(
        goal.priority.value == "besoin"
        and goal.amount
        and wealth is not None
        and goal.amount > wealth
        and (goal.horizon_years or UNKNOWN_HORIZON_YEARS) <= UNDERFUNDED_NEED_HORIZON_YEARS
    )


def _triggered_hard_caps(
    profile: InvestorProfile, wealth: float | None, emergency_months: float, context: _CompileContext
) -> list[_HardCap]:
    """Plafonds durs de la capacite que le profil declenche, dans l'ordre ou ils s'appliquent."""
    rules = context.risk_levels["capacity"]
    hard_caps = rules["hard_caps"]
    triggered = []
    if emergency_months < 1:
        triggered.append(
            _HardCap(
                "emergency_lt_1_month",
                hard_caps["emergency_lt_1_month"],
                {"emergency_fund_months": emergency_months},
                "capacity.hard_caps.emergency_lt_1_month",
            )
        )
    high_cost_debts = [
        debt.label for debt in profile.debts if debt.annual_rate >= rules["debt"]["high_cost_rate"] and debt.balance > 0
    ]
    if high_cost_debts:
        triggered.append(
            _HardCap(
                "high_cost_debt",
                rules["debt"]["high_cost_cap"],
                {"high_cost_debts": high_cost_debts},
                "capacity.debt.high_cost_cap",
            )
        )
    underfunded = [goal.goal_id for goal in profile.goals if _is_underfunded_need(goal, wealth)]
    if underfunded:
        triggered.append(
            _HardCap(
                "besoin_underfunded",
                hard_caps["besoin_underfunded"],
                {"underfunded_besoin_goals": underfunded, "W": wealth},
                "capacity.hard_caps.besoin_underfunded",
            )
        )
    return triggered


def _capped_capacity(
    raw_capacity: float, hard_caps: list[_HardCap], profile: InvestorProfile, context: _CompileContext
) -> tuple[float, list[str]]:
    """C apres les plafonds durs, puis apres la capacite evaluee, qui ne peut que la baisser."""
    capacity = raw_capacity
    applied = []
    for hard_cap in hard_caps:
        capacity = min(capacity, hard_cap.cap)
        applied.append(hard_cap.name)
        context.record("capacity.hard_cap", hard_cap.inputs, capacity, hard_cap.yaml_path)
    assessed = profile.capacity_assessed
    if assessed is not None and context.risk_levels["capacity"].get("never_exceed_capacity_assessed", True):
        if assessed.value < capacity:
            applied.append("capacity_assessed")
        capacity = min(capacity, assessed.value)
        context.record(
            "capacity.assessed",
            {"capacity_assessed": assessed.value},
            capacity,
            "capacity.never_exceed_capacity_assessed",
        )
    return capacity, applied


def _capacity(
    profile: InvestorProfile, horizon_years: float, wealth: float | None, context: _CompileContext, options: dict
) -> dict[str, Any]:
    """Capacite C (0-100) : produit pondere des composantes H, A, E, D, I et L, puis plafonds durs."""
    weights = context.risk_levels["capacity"]["weights"]
    horizon_capacity = _horizon_capacity(horizon_years, context)  # cH
    is_retired = _is_retired(profile)
    required_months = _required_emergency_months(profile, context, is_retired=is_retired)  # Ereq
    emergency_months, emergency_capacity = _emergency_capacity(  # E, cE
        profile, required_months, context, is_retired=is_retired
    )
    withdrawal_rate, withdrawal_capacity = _withdrawal_capacity(profile, wealth, context, options)  # q, cD
    loss_capacity = _loss_capacity(withdrawal_rate, horizon_years, context)  # l_cap
    absorption_capacity = _absorption_capacity(loss_capacity, context)  # cA
    income_capacity = _income_capacity(profile, context, is_retired=is_retired)  # cI
    debt_capacity = _debt_capacity(profile, context)  # cL
    components = {
        "H": horizon_capacity,
        "A": absorption_capacity,
        "E": emergency_capacity,
        "D": withdrawal_capacity,
        "I": income_capacity,
        "L": debt_capacity,
    }
    raw_capacity = 100 * math.prod(  # C_raw
        max(components[component], CAPACITY_COMPONENT_FLOOR) ** weights[component] for component in weights
    )
    context.record("capacity.C", {"components": components, "weights": weights}, raw_capacity, "capacity.weights")
    hard_caps = _triggered_hard_caps(profile, wealth, emergency_months, context)
    capacity, applied_caps = _capped_capacity(raw_capacity, hard_caps, profile, context)
    return {
        "C": capacity,
        "C_raw": raw_capacity,
        "components": components,
        "hard_caps_applied": applied_caps,
        "emergency_required_months": required_months,
        "q": withdrawal_rate,
        "l_cap": loss_capacity,
        "retired": is_retired,
    }


# --------------------------------------------------------------------------- tolerance


@dataclass(frozen=True)
class _ToleranceScores:
    """Scores de tolerance d'un decideur : l'investisseur ou un membre du menage."""

    declared: Score | None
    tested: Score | None = None
    composure: Score | None = None


class _WeightedScore(NamedTuple):
    value: float
    weight: float
    confidence: float


def _own_scores(profile: InvestorProfile) -> _ToleranceScores:
    return _ToleranceScores(profile.tolerance_declared, profile.tolerance_tested, profile.composure)


def _weighted_scores(
    scores: _ToleranceScores, context: _CompileContext, *, overconfident: bool
) -> list[_WeightedScore]:
    """Scores declare puis teste, s'ils existent, avec leur poids et leur confiance (celles du YAML par defaut).

    Le biais de surconfiance donne plus de poids au test et moins de confiance a la declaration.
    """
    rules = context.risk_levels["tolerance"]
    default_confidence = rules["default_confidence"]
    declared_weight, tested_weight = rules["w_declared"], rules["w_tested"]
    declared_confidence_mult = 1.0
    if overconfident:
        bias = context.risk_levels["biases"]["surconfiance"]
        tested_weight, declared_confidence_mult = bias["w_tested"], bias["declared_confidence_mult"]
    weighted = []
    declared, tested = scores.declared, scores.tested
    if declared is not None:
        confidence = declared.confidence if declared.confidence is not None else default_confidence["declared"]
        weighted.append(_WeightedScore(declared.value, declared_weight, confidence * declared_confidence_mult))
    if tested is not None:
        confidence = tested.confidence if tested.confidence is not None else default_confidence["tested"]
        weighted.append(_WeightedScore(tested.value, tested_weight, confidence))
    return weighted


def _apply_composure(tolerance: float, composure: Score | None, context: _CompileContext) -> float:
    """Rabat la part de la tolerance qui depasse la composure et sa marge ; penalite fixe si la composure manque."""
    rules = context.risk_levels["tolerance"]["composure"]
    if composure is None:
        return tolerance - rules["missing_penalty"]
    return tolerance - rules["slope"] * max(0.0, tolerance - (composure.value + rules["slack"]))


def _individual_tolerance(
    scores: _ToleranceScores, context: _CompileContext, *, who: str, overconfident: bool = False
) -> dict[str, Any]:
    """Tolerance d'un decideur (formule PhD1) avec ses etapes : moyenne ponderee par la confiance, desaccord,
    retrecissement vers l'a priori prudent, composure."""
    rules = context.risk_levels["tolerance"]
    prior = rules["conservative_prior"]  # T0
    weighted = _weighted_scores(scores, context, overconfident=overconfident)
    if not weighted:
        return {"T": float(prior), "steps": {"prior": prior}, "who": who, "missing": True}
    weighted_mean = sum(score.weight * score.confidence * score.value for score in weighted) / sum(  # Tb
        score.weight * score.confidence for score in weighted
    )
    if len(weighted) == 2:
        declared_value, tested_value = weighted[0].value, weighted[1].value
        disagreement = rules["disagreement"]
        disagreement_weight = _clip(  # beta
            (abs(declared_value - tested_value) - disagreement["free"]) / (disagreement["full"] - disagreement["free"])
        )
        blended = (1 - disagreement_weight) * weighted_mean + disagreement_weight * min(  # T1
            declared_value, tested_value
        )
    else:
        disagreement_weight, blended = 0.0, weighted_mean
    confidence = 1 - math.prod(1 - score.confidence for score in weighted)  # k
    shrunk = blended - (1 - confidence) * max(0.0, blended - prior)  # T2
    tolerance = _apply_composure(shrunk, scores.composure, context)  # T3
    return {
        "T": tolerance,
        "who": who,
        "missing": False,
        "overconfident": overconfident,
        "steps": {
            "Tb": weighted_mean,
            "beta": disagreement_weight,
            "T1": blended,
            "k": confidence,
            "T2": shrunk,
            "T3": tolerance,
        },
    }


def _person_tolerance(profile: InvestorProfile, context: _CompileContext) -> dict[str, Any]:
    """Tolerance de l'investisseur lui-meme ; note les valeurs prudentes prises pour ses scores absents."""
    person = _individual_tolerance(_own_scores(profile), context, who="personne")
    context.record(
        "tolerance.person",
        {
            "declared": profile.tolerance_declared and profile.tolerance_declared.value,
            "tested": profile.tolerance_tested and profile.tolerance_tested.value,
            "composure": profile.composure and profile.composure.value,
        },
        person["steps"],
        "tolerance",
    )
    if person["missing"]:
        context.use_default("tolerance_declared/tolerance_tested", person["T"], "tolerance.conservative_prior")
    if profile.composure is None:
        context.use_default(
            "composure",
            -context.risk_levels["tolerance"]["composure"]["missing_penalty"],
            "tolerance.composure.missing_penalty",
        )
    return person


def _overconfident_tolerance(
    profile: InvestorProfile, person_tolerance: float, context: _CompileContext
) -> dict[str, Any]:
    overconfident = _individual_tolerance(
        _own_scores(profile), context, who="personne+surconfiance", overconfident=True
    )
    context.record(
        "biases.surconfiance",
        {"T_without": person_tolerance, "T_with": overconfident["T"]},
        min(person_tolerance, overconfident["T"]),
        "biases.surconfiance",
    )
    return overconfident


def _household_tolerances(profile: InvestorProfile, context: _CompileContext) -> list[dict[str, Any]]:
    """Tolerance de chaque membre du menage qui en declare une."""
    rule = profile.household_rule or "min_tolerance"
    tolerances = []
    for member in profile.household:
        if member.tolerance is None:
            continue
        member_tolerance = _individual_tolerance(_ToleranceScores(member.tolerance), context, who=member.role)
        context.record(
            "household.member",
            {"role": member.role, "tolerance": member.tolerance.value, "rule": rule},
            member_tolerance["T"],
            "household.min_tolerance",
        )
        tolerances.append(member_tolerance)
    return tolerances


def _tolerance(profile: InvestorProfile, biases: set[str], context: _CompileContext) -> dict[str, Any]:
    """Tolerance T retenue : la plus basse de celles de la personne, de sa variante surconfiante et du menage."""
    person = _person_tolerance(profile, context)
    candidates = [person]
    if "surconfiance" in biases:  # les biais ne font que resserrer : min(sans, avec)
        candidates.append(_overconfident_tolerance(profile, person["T"], context))
    candidates.extend(_household_tolerances(profile, context))
    tolerance = min(candidate["T"] for candidate in candidates)
    context.record(
        "tolerance.T",
        {"candidates": [candidate["T"] for candidate in candidates]},
        tolerance,
        "household.min_tolerance",
    )
    return {"T": tolerance, "person": person, "candidates": candidates}


# --------------------------------------------------------------------------- niveau


def _risk_level_index(risk_score: float, cutoffs: list[float]) -> int:
    return sum(risk_score >= cutoff for cutoff in cutoffs)


def _horizon_level_cap(horizon_years: float, context: _CompileContext) -> str:
    for index, row in enumerate(context.risk_levels["horizon_cap"]):
        if row["T_lt"] is None or horizon_years < row["T_lt"]:
            context.record("horizon_cap", {"T": horizon_years}, row["level_max"], f"horizon_cap[{index}]")
            return row["level_max"]
    raise ValueError("horizon_cap sans ligne terminale")


def _equity_band_pct(level: str, context: _CompileContext) -> tuple[int, int]:
    """Bande d'actions (e_min, e_max) du niveau, en points de pourcentage."""
    low, high = context.risk_levels["levels"][level]["equity"]
    return int(round(low * 100)), int(round(high * 100))


class _SourcedValue(NamedTuple):
    """Un plafond et la source YAML qui le justifie."""

    value: float
    source: str


def _budgets(level: str, equity_cap_pct: int, context: _CompileContext) -> dict[str, _SourcedValue]:
    """Budgets de risque du niveau ; si e_cap < e_max : arrondi_sup(ENV(e_cap)) (budgets_when_capped)."""
    level_budgets = context.risk_levels["levels"][level]
    if equity_cap_pct >= _equity_band_pct(level, context)[1]:
        return {
            name: _SourcedValue(float(level_budgets[name]), context.source(f"levels.{level}.{name}"))
            for name in BUDGET_ENVELOPE_COLUMNS
        }
    rounding = context.risk_levels["measurement"]["rounding"]
    budgets = {}
    for name, column in BUDGET_ENVELOPE_COLUMNS.items():
        envelope_value = envelope.env(equity_cap_pct, column)
        # Garde de monotonie (ecart au YAML) : ENV n'est pas monotone sous e = 10 % (obligations seules
        # plus dures que le melange demi-cash) ; un budget plafonne ne depasse jamais celui du niveau.
        budget = min(ceil_step(envelope_value, rounding[name]), float(level_budgets[name]))
        budgets[name] = _SourcedValue(
            budget,
            f"{context.source('levels.budgets_when_capped')} ; envelope_v02.yaml#equity_pct.{equity_cap_pct}.{column}",
        )
        context.record(
            f"budget.{name}",
            {
                "e_cap_pct": equity_cap_pct,
                "env": envelope_value,
                "step": rounding[name],
                "level_budget": level_budgets[name],
            },
            budget,
            context.source("levels.budgets_when_capped"),
        )
    return budgets


# --------------------------------------------------------------------------- compilateur


def _default_universe(risk_levels: dict) -> list[str]:
    proxies = risk_levels["history_proxies"]
    return list(proxies) + [asset for asset in risk_levels.get("no_proxy") or [] if asset not in proxies]


@dataclass(frozen=True)
class _CompileInputs:
    """Entrees d'une compilation, une fois le questionnaire applique au profil."""

    profile: InvestorProfile
    as_of: date
    options: dict[str, Any]  # options de l'adaptateur du questionnaire ; vide sans questionnaire
    universe: list[str]
    asset_classes: dict[str, str]
    biases: set[str]  # cles de risk_levels.yaml#biases reconnues dans les biais du profil
    knowledge: str  # niveau de connaissances ; la valeur prudente du YAML si le profil n'en donne pas

    @property
    def wealth(self) -> float | None:
        """W : patrimoine investissable du seau risque."""
        return self.profile.investable_wealth


def _signature(
    inputs: _CompileInputs,
    request: SpecificRequest | None,
    questionnaire: QuestionnaireScores | None,
    context: _CompileContext,
) -> str:
    serialized = json.dumps(
        {
            "profile": inputs.profile.model_dump(mode="json"),
            "as_of": inputs.as_of.isoformat(),
            "questionnaire": questionnaire.model_dump(mode="json") if questionnaire else None,
            "request": request.model_dump(mode="json") if request else None,
            "yaml_version": context.risk_levels["version"],
            "universe": inputs.universe,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def _questionnaire_adapted(
    profile: InvestorProfile, questionnaire: QuestionnaireScores | None, context: _CompileContext
) -> tuple[InvestorProfile, dict[str, Any]]:
    """Profil apres l'adaptateur du questionnaire et options de celui-ci (vides sans questionnaire)."""
    if questionnaire is None:
        return profile, {}
    adapted, options, questionnaire_trace = apply_questionnaire(profile, questionnaire)
    context.trace.extend(questionnaire_trace)
    context.missing_defaults.extend(options["notes"])
    return adapted, options


def _knowledge_level(profile: InvestorProfile, context: _CompileContext) -> str:
    if profile.knowledge_level:
        return profile.knowledge_level.value
    return context.use_default("knowledge_level", context.risk_levels["knowledge"]["missing"], "knowledge.missing")


def _knowledge_caps(knowledge: str, context: _CompileContext) -> dict[str, Any]:
    """Plafonds propres au niveau de connaissances (risk_levels.yaml#knowledge) ; vide s'il n'en impose pas."""
    return context.risk_levels["knowledge"].get(knowledge) or {}


def _missing_must_have(profile: InvestorProfile, context: _CompileContext) -> list[str]:
    """Champs de status.must_have absents du profil ; seul investable_wealth est verifie ici."""
    must_have = context.risk_levels["status"]["must_have"]
    return [name for name in must_have if name == "investable_wealth" and profile.investable_wealth is None]


def _profile_status(profile: InvestorProfile, missing_must_have: list[str], context: _CompileContext) -> str:
    """Statut retenu : un profil COMPLETE devient INCOMPLETE s'il manque un champ obligatoire ou de la confiance."""
    status = profile.status.value
    if status == "COMPLETE" and (
        missing_must_have
        or (profile.confidence is not None and profile.confidence < context.risk_levels["status"]["completeness_min"])
    ):
        status = "INCOMPLETE"
    context.record(
        "status",
        {
            "profile_status": profile.status.value,
            "must_have_missing": missing_must_have,
            "confidence": profile.confidence,
            "completeness_min": context.risk_levels["status"]["completeness_min"],
        },
        status,
        "status",
    )
    if profile.investable_wealth is None:
        context.use_default("investable_wealth", None, "status.must_have : aucun calcul en dollars")
    return status


def _risk_score(tolerance: float, capacity: float, flags: list[str], context: _CompileContext) -> float:
    """R = min(T, C) moins la penalite des drapeaux d'incoherence, plafonnee."""
    penalty_rules = context.risk_levels["tolerance"]["flag_penalty"]
    penalty = min(penalty_rules["max"], penalty_rules["per_flag"] * len(flags))
    risk_score = min(tolerance, capacity) - penalty
    context.record("R", {"T": tolerance, "C": capacity, "flag_penalty": penalty, "flags": list(flags)}, risk_score, "R")
    return risk_score


@dataclass(frozen=True)
class _RiskAssessment:
    """Lecture du profil avant le choix du niveau : statut, horizon, capacite, tolerance et score R."""

    status: str  # COMPLETE | INCOMPLETE | PROTECTION, avant la regle des dollars
    missing_must_have: list[str]
    horizon_years: float  # T du seau risque
    bucket_level_cap: str | None  # plafond de niveau quand tous les objectifs sont des seaux prudents
    buckets: list[dict[str, Any]]
    capacity: dict[str, Any]
    tolerance: dict[str, Any]
    risk_score: float  # R
    risk_level_index: int  # niveau(R)
    near_cutoff: bool


def _assess_risk(inputs: _CompileInputs, context: _CompileContext) -> _RiskAssessment:
    profile = inputs.profile
    missing_must_have = _missing_must_have(profile, context)
    status = _profile_status(profile, missing_must_have, context)
    horizon_years, bucket_level_cap, buckets = _horizon_and_buckets(profile, inputs.as_of, context, inputs.options)
    capacity = _capacity(profile, horizon_years, inputs.wealth, context, inputs.options)
    tolerance = _tolerance(profile, inputs.biases, context)
    risk_score = _risk_score(tolerance["T"], capacity["C"], profile.consistency_flags, context)
    cutoffs = context.risk_levels["levels"]["R_cutoffs"]
    risk_level_index = _risk_level_index(risk_score, cutoffs)
    context.record("level.R", {"R": risk_score, "cutoffs": cutoffs}, LV[risk_level_index], "levels.R_cutoffs")
    hysteresis = context.risk_levels["levels"]["hysteresis"]
    return _RiskAssessment(
        status=status,
        missing_must_have=missing_must_have,
        horizon_years=horizon_years,
        bucket_level_cap=bucket_level_cap,
        buckets=buckets,
        capacity=capacity,
        tolerance=tolerance,
        risk_score=risk_score,
        risk_level_index=risk_level_index,
        near_cutoff=min(abs(risk_score - cutoff) for cutoff in cutoffs) < hysteresis,
    )


def _capped_level_index(assessment: _RiskAssessment, context: _CompileContext) -> int:
    """Niveau L0 avant la regle des dollars : le min de niveau(R) et des plafonds d'horizon, de seaux et de statut."""
    caps = {
        "R": assessment.risk_level_index,
        "horizon": _level_index(_horizon_level_cap(assessment.horizon_years, context)),
    }
    if assessment.bucket_level_cap:
        caps["buckets"] = _level_index(assessment.bucket_level_cap)
    if assessment.status == "INCOMPLETE":
        incomplete_cap = context.risk_levels["status"]["INCOMPLETE"]["level_cap"]
        caps["status"] = _level_index(incomplete_cap)
        context.record("status.INCOMPLETE.level_cap", {}, incomplete_cap, "status.INCOMPLETE.level_cap")
    capped_index = min(caps.values())
    context.record("level.L0", caps, LV[capped_index], "R")
    return capped_index


def _planning_loss(equity_pct: int, context: _CompileContext) -> float:
    """L_plan(e) : perte sommet-creux de planification, soit ENV(e, mdd) plus la marge quotidienne."""
    return envelope.env(equity_pct, "mdd") + context.risk_levels["dollar_rule"]["daily_buffer"]


def _declared_loss(profile: InvestorProfile, context: _CompileContext) -> float | None:
    """l_declared : la plus basse des pertes maximales declarees (en % et en $ rapportes a W), ou None."""
    wealth = profile.investable_wealth
    declared = []
    if profile.max_acceptable_loss_pct is not None:
        declared.append(profile.max_acceptable_loss_pct)
    if profile.max_acceptable_loss_cad is not None and wealth:
        declared.append(profile.max_acceptable_loss_cad / wealth)
    declared_loss = min(declared) if declared else None
    context.record(
        "dollar_rule.l_declared",
        {"pct": profile.max_acceptable_loss_pct, "cad": profile.max_acceptable_loss_cad, "W": wealth},
        declared_loss,
        "dollar_rule.l_declared",
    )
    return declared_loss


def _loss_budget(
    max_equity_pct: int, declared_loss: float | None, loss_capacity: float, context: _CompileContext
) -> float:
    """l* : la plus basse de L_plan(e_max), de la perte declaree et de la perte absorbable."""
    planning_loss = _planning_loss(max_equity_pct, context)
    loss_budget = min(loss for loss in (planning_loss, declared_loss, loss_capacity) if loss is not None)
    context.record(
        "dollar_rule.l_star",
        {
            "L_plan_emax": planning_loss,
            "l_declared": declared_loss,
            "l_cap": loss_capacity,
            "e_max_pct": max_equity_pct,
            "daily_buffer": context.risk_levels["dollar_rule"]["daily_buffer"],
            "envelope": f"envelope_v02.yaml#equity_pct.{max_equity_pct}.mdd",
        },
        loss_budget,
        "dollar_rule.l_star",
    )
    return loss_budget


def _admissible_equity_cap(max_equity_pct: int, loss_budget: float, context: _CompileContext) -> int | None:
    """e_cap : plus grande part d'actions de la grille dont L_plan tient dans l* ; None si aucune ne tient."""
    admissible = [
        equity_pct
        for equity_pct in envelope.grid()
        if equity_pct <= max_equity_pct and _planning_loss(equity_pct, context) <= loss_budget + EPSILON
    ]
    if not admissible:
        context.record(
            "dollar_rule.protection",
            {
                "l_star": loss_budget,
                "min_L_plan": min(_planning_loss(equity_pct, context) for equity_pct in envelope.grid()),
            },
            "PROTECTION",
            "dollar_rule.protection",
        )
        return None
    equity_cap_pct = max(admissible)
    context.record(
        "dollar_rule.e_cap",
        {
            "l_star": loss_budget,
            "e_max_pct": max_equity_pct,
            "L_plan_e_cap": _planning_loss(equity_cap_pct, context),
        },
        equity_cap_pct,
        "dollar_rule.e_cap",
    )
    return equity_cap_pct


def _level_index_holding(equity_cap_pct: int, context: _CompileContext) -> int:
    """Niveau dont la bande contient e_cap (e_min < e_cap <= e_max ; e_cap = 0 -> N0)."""
    if equity_cap_pct == 0:
        return 0
    return next(
        index
        for index, level in enumerate(LV)
        if _equity_band_pct(level, context)[0] < equity_cap_pct <= _equity_band_pct(level, context)[1]
    )


@dataclass(frozen=True)
class _LevelDecision:
    """Niveau final du mandat, une fois appliques les plafonds de niveau et la regle des dollars."""

    level: str
    status: str  # PROTECTION si le profil l'impose ou si aucune part d'actions ne tient dans l*
    declared_loss: float | None  # l_declared
    loss_budget: float  # l*
    equity_cap_pct: int  # e_cap, sur la grille de 5 %
    equity_min_pct: int  # e_min de la bande du niveau
    is_protection: bool

    @property
    def level_index(self) -> int:
        return _level_index(self.level)

    @property
    def equity_cap(self) -> float:
        """e_cap en fraction du portefeuille."""
        return self.equity_cap_pct / 100


def _decide_level(profile: InvestorProfile, assessment: _RiskAssessment, context: _CompileContext) -> _LevelDecision:
    """Plafonds de niveau, puis regle des dollars : l*, e_cap, niveau dont la bande contient e_cap, protection."""
    capped_index = _capped_level_index(assessment, context)
    max_equity_pct = _equity_band_pct(LV[capped_index], context)[1]  # e_max
    declared_loss = _declared_loss(profile, context)
    loss_budget = _loss_budget(max_equity_pct, declared_loss, assessment.capacity["l_cap"], context)
    admissible_cap = _admissible_equity_cap(max_equity_pct, loss_budget, context)
    is_protection = profile.status is ProfileStatus.PROTECTION or admissible_cap is None
    equity_cap_pct = admissible_cap or 0
    level_index = min(_level_index_holding(equity_cap_pct, context), capped_index)
    if is_protection:
        level_index = _level_index(context.risk_levels["status"]["PROTECTION"]["level"])
        equity_cap_pct = min(equity_cap_pct, _equity_band_pct(LV[level_index], context)[1])
    level = LV[level_index]
    context.record(
        "level.final",
        {"e_cap_pct": equity_cap_pct, "L0": LV[capped_index], "protection": is_protection},
        level,
        "dollar_rule.level_after",
    )
    return _LevelDecision(
        level=level,
        status="PROTECTION" if is_protection else assessment.status,
        declared_loss=declared_loss,
        loss_budget=loss_budget,
        equity_cap_pct=equity_cap_pct,
        equity_min_pct=_equity_band_pct(level, context)[0],
        is_protection=is_protection,
    )


def _status_overrides(status: str, context: _CompileContext) -> dict[str, Any]:
    """Regles du statut INCOMPLETE ou PROTECTION (satellites mis a zero) ; vide pour un profil COMPLETE."""
    if status in ("INCOMPLETE", "PROTECTION"):
        return context.risk_levels["status"].get(status, {})
    return {}


class _SingleNameCaps(NamedTuple):
    each: float
    total: float
    source: str


def _single_name_caps(inputs: _CompileInputs, decision: _LevelDecision, context: _CompileContext) -> _SingleNameCaps:
    """Plafonds des titres individuels (chacun, et leur somme) ; nuls sous min_level ou si le statut les interdit."""
    rules = context.risk_levels["satellites"]["single_name"]
    status_overrides = _status_overrides(decision.status, context)
    if decision.level_index < _level_index(rules["min_level"]) or status_overrides.get("single_name") == 0:
        each = total = 0.0
        source = (
            context.source(f"status.{decision.status}.single_name")
            if status_overrides
            else context.source("satellites.single_name.min_level")
        )
    else:
        each = min(rules["cap_abs"], floor_step(rules["phi"] * decision.loss_budget / rules["delta"]))
        total = floor_step(rules["total_phi"] * decision.loss_budget / rules["delta"])
        source = context.source("satellites.single_name")
        knowledge_caps = _knowledge_caps(inputs.knowledge, context)
        if "single_name_cap" in knowledge_caps:
            each = min(each, knowledge_caps["single_name_cap"])
            source += f" ; {context.source(f'knowledge.{inputs.knowledge}.single_name_cap')}"
    context.record(
        "satellites.single_name",
        {
            "level": decision.level,
            "l_star": decision.loss_budget,
            "knowledge": inputs.knowledge,
            "status": decision.status,
        },
        {"each": each, "total": total},
        source.split(" ; ")[0],
    )
    return _SingleNameCaps(each, total, source)


def _has_crypto_tilt(profile: InvestorProfile) -> bool:
    return any(any(word in _normalize_label(tilt) for word in CRYPTO_TILT_WORDS) for tilt in profile.preferences.tilts)


def _has_crypto_etf(inputs: _CompileInputs) -> bool:
    return any(inputs.asset_classes.get(asset) in CRYPTO_ETF_CLASSES for asset in inputs.universe)


def _knowledge_limited_crypto(cap: _SourcedValue, inputs: _CompileInputs, context: _CompileContext) -> _SourcedValue:
    """Plafond crypto resserre par les connaissances : crypto_mult, puis FNB seulement (crypto_vehicle)."""
    knowledge_caps = _knowledge_caps(inputs.knowledge, context)
    weight, source = cap
    if "crypto_mult" in knowledge_caps:
        weight = floor_step(weight * knowledge_caps["crypto_mult"])
        source += f" ; {context.source(f'knowledge.{inputs.knowledge}.crypto_mult')}"
    if knowledge_caps.get("crypto_vehicle") == "etf_only" and not _has_crypto_etf(inputs):
        weight = 0.0
        source += (
            f" ; {context.source(f'knowledge.{inputs.knowledge}.crypto_vehicle')} (aucun FNB crypto dans l'univers)"
        )
    return _SourcedValue(weight, source)


def _crypto_cap(inputs: _CompileInputs, decision: _LevelDecision, context: _CompileContext) -> _SourcedValue:
    """Plafond crypto ; nul sous min_level, sans preference pour la crypto ou si le statut l'interdit."""
    rules = context.risk_levels["satellites"]["crypto"]
    has_tilt = _has_crypto_tilt(inputs.profile)
    cap = _SourcedValue(0.0, context.source("satellites.crypto"))
    is_allowed = not (
        decision.level_index < _level_index(rules["min_level"])
        or (rules["requires_tilt"] and not has_tilt)
        or _status_overrides(decision.status, context).get("crypto") == 0
    )
    if is_allowed:
        weight = min(rules["cap_abs"][decision.level], floor_step(rules["phi"] * decision.loss_budget / rules["delta"]))
        cap = _knowledge_limited_crypto(_SourcedValue(weight, cap.source), inputs, context)
    context.record(
        "satellites.crypto",
        {"level": decision.level, "tilt": has_tilt, "l_star": decision.loss_budget, "knowledge": inputs.knowledge},
        cap.value,
        cap.source.split(" ; ")[0],
    )
    return cap


def _sandbox_cap(inputs: _CompileInputs, decision: _LevelDecision, context: _CompileContext) -> float:
    """Plafond du bac a sable ; nul sous min_level, si le statut l'interdit ou sans patrimoine connu."""
    rules = context.risk_levels["satellites"]["sandbox"]
    wealth = inputs.wealth
    monthly_expenses = inputs.profile.monthly_expenses
    if (
        decision.level_index < _level_index(rules["min_level"])
        or _status_overrides(decision.status, context).get("sandbox") == 0
        or not wealth
    ):
        cap = 0.0
    else:
        if monthly_expenses is None:
            monthly_expenses = context.use_default(
                "monthly_expenses", 0.0, "satellites.sandbox.months_cap : bac a sable nul"
            )
        cap = min(
            rules["cap_abs"],
            floor_step(rules["months_cap"] * monthly_expenses / wealth),
            floor_step(rules["phi"] * decision.loss_budget / rules["delta"]),
        )
        knowledge_caps = _knowledge_caps(inputs.knowledge, context)
        if "sandbox_mult" in knowledge_caps:
            cap = floor_step(cap * knowledge_caps["sandbox_mult"])
    context.record(
        "satellites.sandbox",
        {
            "level": decision.level,
            "W": wealth,
            "M": monthly_expenses,
            "l_star": decision.loss_budget,
            "knowledge": inputs.knowledge,
        },
        cap,
        "satellites.sandbox",
    )
    return cap


def _tech_cap(biases: set[str], decision: _LevelDecision, context: _CompileContext) -> float:
    """Plafond d'exposition au theme tech ; le biais de familiarite reduit la part de l* qui lui revient."""
    rules = context.risk_levels["satellites"]["theme_tech"]
    loss_share = (  # phi
        context.risk_levels["biases"]["familiarite"]["theme_phi"] if "familiarite" in biases else rules["phi"]
    )
    cap = floor_step(
        decision.equity_cap_pct / 100 * rules["s_ref"] + loss_share * decision.loss_budget / rules["delta"]
    )
    context.record(
        "satellites.theme_tech",
        {
            "e_cap_pct": decision.equity_cap_pct,
            "s_ref": rules["s_ref"],
            "phi": loss_share,
            "l_star": decision.loss_budget,
        },
        cap,
        "satellites.theme_tech",
    )
    return cap


@dataclass(frozen=True)
class _SatelliteCaps:
    """Plafonds des satellites : titres individuels, crypto, bac a sable et theme tech."""

    single_name: _SingleNameCaps
    crypto: _SourcedValue
    sandbox: float
    tech: float


def _satellite_caps(inputs: _CompileInputs, decision: _LevelDecision, context: _CompileContext) -> _SatelliteCaps:
    single_name = _single_name_caps(inputs, decision, context)
    crypto = _crypto_cap(inputs, decision, context)
    sandbox = _sandbox_cap(inputs, decision, context)
    tech = _tech_cap(inputs.biases, decision, context)
    return _SatelliteCaps(single_name, crypto, sandbox, tech)


class _Composition(NamedTuple):
    """Plafonds de composition du niveau (anti-concentration), selon risk_levels.yaml#composition."""

    etf_equity_each_max: float
    etf_bond_each_max: float
    cash_like_max: float
    cash_like_min: float | None


def _composition(decision: _LevelDecision, context: _CompileContext) -> _Composition:
    rules = context.risk_levels["composition"]
    level = decision.level
    defensive_share = 1 - decision.equity_min_pct / 100
    composition = _Composition(
        etf_equity_each_max=round(max(ETF_EQUITY_EACH_FLOOR, ETF_EQUITY_EACH_SHARE * decision.equity_cap), 4),
        etf_bond_each_max=round(ceil_step(ETF_BOND_EACH_SHARE * defensive_share, ETF_BOND_EACH_STEP), 4),
        cash_like_max=1.0 if level == "N0" else round(CASH_LIKE_SHARE * defensive_share, 4),
        cash_like_min=context.risk_levels["levels"][level].get("cash_like_min"),
    )
    context.record(
        "composition",
        {"level": level, "e_cap_pct": decision.equity_cap_pct, "e_min_pct": decision.equity_min_pct},
        {
            "etf_equity_each_max": composition.etf_equity_each_max,
            "etf_bond_each_max": composition.etf_bond_each_max,
            "cash_like_max": composition.cash_like_max,
            "cash_like_min": composition.cash_like_min,
            "long_duration_max": rules["long_duration_max"][level],
            "gold_max": rules["gold_max"][level],
        },
        "composition",
    )
    return composition


class _Bounds(NamedTuple):
    """Bornes et source d'une Limit du gabarit limits_template."""

    minimum: float | None
    maximum: float | None
    source: str


def _allocation_bounds(
    decision: _LevelDecision, composition: _Composition, crypto: _SourcedValue, context: _CompileContext
) -> dict[str, _Bounds]:
    level = decision.level
    rules = context.risk_levels["composition"]
    return {
        "alloc.growth": _Bounds(
            decision.equity_min_pct / 100,
            decision.equity_cap,
            f"{context.source(f'levels.{level}.equity')} ; {context.source('dollar_rule.e_cap')}",
        ),
        "alloc.cash_like": _Bounds(
            composition.cash_like_min,
            composition.cash_like_max,
            context.source("composition.cash_like_max")
            + (f" ; {context.source('levels.N0.cash_like_min')}" if composition.cash_like_min else ""),
        ),
        "alloc.long_duration": _Bounds(
            None, rules["long_duration_max"][level], context.source(f"composition.long_duration_max.{level}")
        ),
        "alloc.gold": _Bounds(None, rules["gold_max"][level], context.source(f"composition.gold_max.{level}")),
        "alloc.crypto": _Bounds(None, crypto.value, crypto.source),
    }


def _concentration_bounds(
    composition: _Composition, satellites: _SatelliteCaps, biases: set[str], context: _CompileContext
) -> dict[str, _Bounds]:
    single_name = satellites.single_name
    return {
        "conc.etf_equity_each": _Bounds(
            None, composition.etf_equity_each_max, context.source("composition.etf_equity_each_max")
        ),
        "conc.etf_bond_each": _Bounds(
            None, composition.etf_bond_each_max, context.source("composition.etf_bond_each_max")
        ),
        "conc.single_each": _Bounds(None, single_name.each, single_name.source),
        "conc.single_total": _Bounds(
            None,
            single_name.total,
            context.source("satellites.single_name.total_phi")
            if single_name.total
            else single_name.source.split(" ; ")[0],
        ),
        "exp.tech": _Bounds(
            None,
            satellites.tech,
            context.source("satellites.theme_tech")
            + (f" ; {context.source('biases.familiarite.theme_phi')}" if "familiarite" in biases else ""),
        ),
    }


def _risk_bounds(
    budgets: dict[str, _SourcedValue], crypto: _SourcedValue, context: _CompileContext
) -> dict[str, _Bounds]:
    """Budgets de risque ; la CVaR mensuelle est reduite de la part que la crypto, sans proxy, peut perdre."""
    cvar_m = budgets["cvar_m"]
    crypto_cvar_m_proxy = context.risk_levels["satellites"]["crypto"]["cvar_m_proxy"]
    return {
        "risk.cvar_m": _Bounds(
            None,
            round(cvar_m.value - crypto.value * crypto_cvar_m_proxy, 6),
            cvar_m.source + (f" ; {context.source('satellites.crypto.cvar_m_proxy')}" if crypto.value else ""),
        ),
        "risk.cvar_12m": _Bounds(None, budgets["cvar_12m"].value, budgets["cvar_12m"].source),
        "risk.mdd": _Bounds(None, budgets["mdd"].value, budgets["mdd"].source),
        "risk.vol": _Bounds(None, budgets["vol"].value, budgets["vol"].source),
        "risk.cdar_m": _Bounds(None, cvar_m.value, f"{context.source('biases.aversion_perte')} ; {cvar_m.source}"),
        "risk.stress_2022": _Bounds(None, budgets["s2022"].value, budgets["s2022"].source),
    }


def _needs_cdar_limit(inputs: _CompileInputs, context: _CompileContext) -> bool:
    """risk.cdar_m n'est emise que pour une aversion aux pertes ou une composure sous le seuil du YAML."""
    composure = inputs.profile.composure
    return "aversion_perte" in inputs.biases or (
        composure is not None and composure.value < context.risk_levels["tolerance"]["low_composure_cdar"]["threshold"]
    )


def _derived_from(template: dict[str, Any], biases: set[str]) -> str:
    derived_from = template["derived_from"]
    if template["rule_id"] == "risk.cdar_m":
        derived_from = "profile.biases[aversion_perte]" if "aversion_perte" in biases else "profile.composure<40"
    return derived_from


def _template_limits(
    bounds: dict[str, _Bounds], inputs: _CompileInputs, level: str, context: _CompileContext
) -> list[Limit]:
    """Une Limit par entree de limits_template, sauf sat.sandbox et la CDaR quand rien ne la declenche."""
    needs_cdar = _needs_cdar_limit(inputs, context)
    limits: list[Limit] = []
    for template in context.risk_levels["limits_template"]:
        rule_id = template["rule_id"]
        if rule_id == "sat.sandbox":
            continue  # emise seulement avec une demande (RequestView.limits)
        if rule_id == "risk.cdar_m" and not needs_cdar:
            continue
        minimum, maximum, source = bounds[rule_id]
        limits.append(
            Limit(
                rule_id=rule_id,
                kind=template["kind"],
                selector=Selector(**template["selector"]),
                min=minimum,
                max=maximum,
                blocking=template.get("blocking", True),
                derived_from=_derived_from(template, inputs.biases),
                source=source,
                description_fr=f"{rule_id} niveau {level}",
            )
        )
        context.record(f"limit.{rule_id}", {"level": level}, {"min": minimum, "max": maximum}, source.split(" ; ")[0])
    return limits


def _employer_tickers(profile: InvestorProfile, universe: list[str]) -> list[str]:
    """Titres de l'employeur (titres detenus, employeur du revenu) presents dans l'univers, tries."""
    tickers = {equity.ticker for equity in profile.employer_equity if equity.ticker}
    if profile.income and profile.income.employer_ticker:
        tickers.add(profile.income.employer_ticker)
    return [ticker for ticker in sorted(tickers) if ticker in universe]


def _employer_limit(inputs: _CompileInputs, single_name: _SingleNameCaps, context: _CompileContext) -> Limit | None:
    """Biais de familiarite : le titre de l'employeur n'a droit qu'a une fraction du plafond d'un titre individuel."""
    if "familiarite" not in inputs.biases:
        return None
    tickers = _employer_tickers(inputs.profile, inputs.universe)
    if not tickers:
        return None
    multiplier = context.risk_levels["biases"]["familiarite"]["employer_ticker_cap_mult"]
    cap = floor_step(single_name.each * multiplier)
    limit = Limit(
        rule_id="bias.familiarite.employer",
        kind="asset_weight",
        selector=Selector(assets=tickers),
        max=cap,
        derived_from="profile.biases[familiarite] ; profile.employer_equity",
        source=f"{context.source('biases.familiarite.employer_ticker_cap_mult')} ; {single_name.source}",
        description_fr="titre de l'employeur plafonne",
    )
    context.record(
        "biases.familiarite.employer",
        {"tickers": tickers, "w_single": single_name.each, "mult": multiplier},
        cap,
        "biases.familiarite.employer_ticker_cap_mult",
    )
    return limit


def _mandate_limits(
    inputs: _CompileInputs, decision: _LevelDecision, satellites: _SatelliteCaps, context: _CompileContext
) -> list[Limit]:
    """Limites du mandat (1:1 avec limits_template), puis celle du titre de l'employeur."""
    composition = _composition(decision, context)
    budgets = _budgets(decision.level, decision.equity_cap_pct, context)
    bounds = {
        **_allocation_bounds(decision, composition, satellites.crypto, context),
        **_concentration_bounds(composition, satellites, inputs.biases, context),
        **_risk_bounds(budgets, satellites.crypto, context),
    }
    limits = _template_limits(bounds, inputs, decision.level, context)
    employer_limit = _employer_limit(inputs, satellites.single_name, context)
    if employer_limit is not None:
        limits.append(employer_limit)
    return limits


def _excluded_assets(profile: InvestorProfile, universe: list[str], context: _CompileContext) -> dict[str, str]:
    """Actifs de l'univers exclus par une contrainte legale bloquante ou par un filtre de valeurs, avec la raison."""
    excluded: dict[str, str] = {}
    for constraint in profile.legal_constraints:
        if not constraint.blocking:
            continue
        for asset in constraint.tickers:
            if asset in universe:
                excluded[asset] = f"profile.legal_constraints[{constraint.kind}]"
    for value_filter in profile.preferences.value_filters:
        for asset, verdict in sorted(value_filter.per_ticker.items()):
            is_excluding = verdict == "exclu" or (verdict == "zone_grise" and value_filter.decided_utc is None)
            if asset in universe and is_excluding:
                excluded.setdefault(asset, f"profile.preferences.value_filters[{value_filter.rule}]={verdict}")
    if excluded:
        context.record("universe.excluded", {}, dict(sorted(excluded.items())), "profile")
    return excluded


def _outside_policy_reasons(
    excluded_reason: str | None, requested_weight: float | None, applicable_max: float, *, in_universe: bool
) -> list[str]:
    reasons = []
    if not in_universe:
        reasons.append("ticker hors univers du mandat")
    if excluded_reason is not None:
        reasons.append(f"ticker exclu : {excluded_reason}")
    if requested_weight is None:
        reasons.append("poids de la demande inconnu (investable_wealth absent)")
    elif requested_weight > applicable_max + EPSILON:
        reasons.append(f"poids demande {requested_weight:.4f} > plafond applicable {applicable_max:.4f}")
    return reasons


def _sandbox_limit(ticker: str, sandbox_cap: float, context: _CompileContext, *, has_fomo: bool) -> Limit:
    return Limit(
        rule_id="sat.sandbox",
        kind="group_weight",
        selector=Selector(assets=[ticker]),
        max=sandbox_cap,
        derived_from="profile.requests" + (" ; profile.biases[FOMO]" if has_fomo else ""),
        source=context.source("satellites.sandbox"),
        description_fr=f"bac a sable {ticker}",
    )


def _cooldown_days(context: _CompileContext, *, has_fomo: bool) -> int:
    """Delai de reflexion du bac a sable ; celui du biais FOMO s'il est plus long."""
    sandbox_cooldown_days = context.risk_levels["satellites"]["sandbox"]["cooldown_days"]
    fomo_cooldown_days = context.risk_levels["biases"]["FOMO"]["cooldown_days"] if has_fomo else 0
    return max(sandbox_cooldown_days, fomo_cooldown_days)


def _request_view(
    request: SpecificRequest,
    inputs: _CompileInputs,
    satellites: _SatelliteCaps,
    excluded: dict[str, str],
    context: _CompileContext,
) -> RequestView:
    """Plafonds qui visent la demande (bac a sable, titre individuel, crypto) ; F1 ne l'approuve jamais."""
    ticker, wealth = request.ticker, inputs.wealth
    asset_class = inputs.asset_classes.get(ticker)
    in_universe = ticker in inputs.universe
    is_investable = in_universe and ticker not in excluded
    requested_weight = (
        request.weight if request.weight is not None else (request.amount_cad / wealth if wealth else None)
    )
    single_name_max = satellites.single_name.each if asset_class == "equity_single" else None
    crypto_max = satellites.crypto.value if asset_class == "crypto" else None
    caps = [cap for cap in (satellites.sandbox, single_name_max, crypto_max) if cap is not None]
    applicable_max = min(caps) if is_investable else 0.0
    reasons = _outside_policy_reasons(excluded.get(ticker), requested_weight, applicable_max, in_universe=in_universe)
    has_fomo = "FOMO" in inputs.biases
    limits = [_sandbox_limit(ticker, satellites.sandbox, context, has_fomo=has_fomo)] if is_investable else []
    context.record(
        "request",
        {"ticker": ticker, "class": asset_class, "requested_weight": requested_weight},
        {"applicable_max": applicable_max, "outside_policy": bool(reasons)},
        "satellites.sandbox",
    )
    return RequestView(
        ticker=ticker,
        asset_class=asset_class,
        in_universe=in_universe,
        excluded_reason=excluded.get(ticker),
        requested_weight=requested_weight,
        requested_cad=request.amount_cad
        if request.amount_cad is not None
        else (request.weight * wealth if wealth else None),
        sandbox_max=satellites.sandbox,
        sandbox_max_cad=round(satellites.sandbox * wealth, 2) if wealth else None,
        single_name_max=single_name_max,
        crypto_max=crypto_max,
        applicable_max=applicable_max,
        applicable_max_cad=round(applicable_max * wealth, 2) if wealth else None,
        outside_policy=bool(reasons),
        reasons=reasons,
        sandbox_only=has_fomo,
        cooldown_days=_cooldown_days(context, has_fomo=has_fomo),
        limits=limits,
    )


def _emphasis_signals(
    inputs: _CompileInputs, assessment: _RiskAssessment, decision: _LevelDecision, request_view: RequestView | None
) -> dict[str, Any]:
    """Signaux que lisent les regles d'emphasis.yaml."""
    profile, wealth = inputs.profile, inputs.wealth
    goal_horizons = [_goal_horizon(goal, inputs.as_of) for goal in profile.goals]
    need_horizons = [_goal_horizon(goal, inputs.as_of) for goal in profile.goals if goal.priority.value == "besoin"]
    positions = [holding.market_value for holding in profile.holdings] + [
        equity.value or 0.0 for equity in profile.employer_equity
    ]
    return {
        "min_goal_horizon_years": min(goal_horizons),
        "has_recurring_withdrawal": any(goal.recurring_withdrawal for goal in profile.goals),
        "min_besoin_horizon_years": min(need_horizons) if need_horizons else None,
        "tolerance_gt_capacity": assessment.tolerance["T"] > assessment.capacity["C"]
        or any("tolerance>capacit" in _normalize_label(flag) for flag in profile.consistency_flags),
        "max_loss_declared": decision.declared_loss is not None,
        "has_debt": bool(profile.debts),
        "emergency_short": (profile.emergency_fund_months or 0.0) < assessment.capacity["emergency_required_months"],
        "emotional_bias": bool(inputs.biases & {"FOMO", "aversion_perte"})
        or any(bias.kind.value == "emotionnel" for bias in profile.biases),
        "esg_required": profile.preferences.esg_required,
        "has_value_filters": bool(profile.preferences.value_filters),
        "has_tilts": bool(profile.preferences.tilts),
        "max_position_share": (max(positions) / wealth) if positions and wealth else None,
        "has_legal_constraints": bool(profile.legal_constraints),
        "has_employer_equity": bool(profile.employer_equity),
        "has_user_rules": bool(profile.user_rules),
        "request_outside_policy": request_view.outside_policy if request_view else False,
    }


def _decision_kind(
    decision: _LevelDecision, missing_must_have: list[str], context: _CompileContext
) -> DecisionKind | None:
    if decision.is_protection:
        kind = "protection"
    elif missing_must_have:
        kind = "incomplet"
    elif decision.status == "INCOMPLETE":
        kind = "position_attente"
    else:
        kind = None
    context.record(
        "decision_kind",
        {"status": decision.status, "protection": decision.is_protection, "must_have_missing": missing_must_have},
        kind,
        "status",
    )
    return kind


def _exposure_overrides(risk_levels: dict, universe: list[str]) -> dict[str, dict[str, ExposureOverride]]:
    return {
        asset: {
            tag: ExposureOverride(
                value=override["value"], source=override["source"], status=override.get("status", "HYPOTHESE")
            )
            for tag, override in tags.items()
        }
        for asset, tags in (risk_levels.get("exposure_overrides") or {}).items()
        if asset in universe
    }


def _history_proxies(risk_levels: dict, universe: list[str]) -> dict[str, HistoryProxy]:
    return {
        asset: HistoryProxy(proxy=proxy["proxy"], source=proxy["source"])
        for asset, proxy in (risk_levels.get("history_proxies") or {}).items()
        if asset in universe
    }


def _policy_spec(
    inputs: _CompileInputs, signature: str, limits: list[Limit], excluded: dict[str, str], context: _CompileContext
) -> PolicySpec:
    """Mandat PolicySpec : limites, exclusions et champs copies du YAML, restreints a l'univers."""
    risk_levels, profile, universe = context.risk_levels, inputs.profile, inputs.universe
    defaults = risk_levels.get("policy_defaults") or {}
    exposure_overrides = _exposure_overrides(risk_levels, universe)
    history_proxies = _history_proxies(risk_levels, universe)
    loss_bounds = {
        asset: float(bound) for asset, bound in (risk_levels.get("loss_bounds") or {}).items() if asset in universe
    }
    # Crochet PROB_LOSS (non emis) : quand l'equipe aura tranche alpha, L et H par profil, ajouter ici
    # ``portfolio.scenario_risk.prob_loss_limit(...)`` a ``limits`` (et, au besoin, ``scenario_blocks`` /
    # ``scenario_run_id`` au PolicySpec). Aucun seuil n'est fixe tant que ce n'est pas decide.
    return PolicySpec(
        policy_id=f"f1-{profile.profile_id}-v{profile.version}-{inputs.as_of.isoformat()}-{signature}",
        profile_id=profile.profile_id,
        profile_version=profile.version,
        created_utc=datetime.combine(inputs.as_of, time(0), tzinfo=UTC),
        currency="CAD",
        universe=universe,
        excluded=dict(sorted(excluded.items())),
        objective=defaults.get("objective", "min_risk"),
        risk_measure=defaults.get("risk_measure", "CVAR"),
        cvar_beta=defaults.get("cvar_beta", 0.95),
        lookback_months=defaults.get("lookback_months", 120),
        limits=limits,
        exposure_overrides=exposure_overrides,
        history_proxies=history_proxies,
        loss_bounds=loss_bounds,
        loss_bounds_source=(
            f"{context.source('loss_bounds')} : {risk_levels.get('loss_bounds_source')}" if loss_bounds else None
        ),
        missing_defaults=list(context.missing_defaults),
    )


def _tolerance_summary(tolerance: dict[str, Any]) -> dict[str, Any]:
    """Tolerance telle que la publie CompileResult : T, etapes de la personne, candidats au min."""
    return {
        "T": tolerance["T"],
        "person": tolerance["person"]["steps"],
        "candidates": [{"who": candidate["who"], "T": candidate["T"]} for candidate in tolerance["candidates"]],
    }


def _compile_mandate(
    inputs: _CompileInputs,
    context: _CompileContext,
    *,
    request: SpecificRequest | None,
    questionnaire: QuestionnaireScores | None,
    emphasis_path: str | Path | None,
) -> CompileResult:
    """Enchaine les etapes de risk_levels.yaml : lecture du profil, niveau, satellites, limites, demande, mandat."""
    assessment = _assess_risk(inputs, context)
    decision = _decide_level(inputs.profile, assessment, context)
    satellites = _satellite_caps(inputs, decision, context)
    limits = _mandate_limits(inputs, decision, satellites, context)
    excluded = _excluded_assets(inputs.profile, inputs.universe, context)
    request_view = _request_view(request, inputs, satellites, excluded, context) if request else None
    signals = _emphasis_signals(inputs, assessment, decision, request_view)
    emphasis, fired_rules, emphasis_trace = compute_emphasis(signals, emphasis_path)
    context.trace.extend(emphasis_trace)
    kind = _decision_kind(decision, assessment.missing_must_have, context)
    signature = _signature(inputs, request, questionnaire, context)
    policy = None
    if kind not in ("protection", "incomplet"):
        policy = _policy_spec(inputs, signature, limits, excluded, context)
    return CompileResult(
        policy=policy,
        level=decision.level,
        R=assessment.risk_score,
        capacity=assessment.capacity,
        tolerance=_tolerance_summary(assessment.tolerance),
        decision_kind=kind,
        emphasis=emphasis,
        trace=context.trace,
        missing_defaults=list(context.missing_defaults),
        status=decision.status,
        level_from_R=LV[assessment.risk_level_index],
        horizon_years=assessment.horizon_years,
        l_star=decision.loss_budget,
        e_cap=decision.equity_cap,
        limits=limits,
        buckets=assessment.buckets,
        emphasis_rules=fired_rules,
        request=request_view,
        near_cutoff=assessment.near_cutoff,
    )


def compile_profile(  # noqa: PLR0913 (signature publique figee : les appelants passent ces options par mot-cle)
    profile: InvestorProfile,
    as_of: date,
    *,
    request: SpecificRequest | None = None,
    yaml_path: str | Path | None = None,
    universe: list[str] | None = None,
    asset_classes: dict[str, str] | None = None,
    emphasis_path: str | Path | None = None,
    questionnaire: QuestionnaireScores | None = None,
) -> CompileResult:
    """Compile un profil en mandat PolicySpec. Deterministe : memes entrees -> meme JSON."""
    context = _CompileContext(_load_yaml(str(yaml_path or DEFAULT_YAML)))
    adapted, options = _questionnaire_adapted(profile, questionnaire, context)
    inputs = _CompileInputs(
        profile=adapted,
        as_of=as_of,
        options=options,
        universe=list(universe) if universe is not None else _default_universe(context.risk_levels),
        asset_classes={**STARTER_ASSET_CLASSES, **(asset_classes or {})},
        biases={key for key in (_bias_key(bias.kind_label) for bias in adapted.biases) if key},
        knowledge=_knowledge_level(adapted, context),
    )
    return _compile_mandate(inputs, context, request=request, questionnaire=questionnaire, emphasis_path=emphasis_path)


# --------------------------------------------------------------------------- cause d'une decision sans mandat


@dataclass(frozen=True)
class DollarRuleProtection:
    """Regle des dollars en PROTECTION : aucune part d'actions de la grille dont L_plan tient dans l*.

    Valeurs lues dans la trace de la compilation (``dollar_rule.protection``, ``dollar_rule.l_star``,
    ``dollar_rule.l_declared`` et ``dollar_rule.l_cap``). Les termes de l_cap et les seuils des leviers en derivent
    par les formules de risk_levels.yaml#dollar_rule.
    """

    l_star: float  # l* = min(L_plan(e_max), l_declared, l_cap)
    min_planning_loss: float  # min_L_plan : plus petite L_plan(e) de la grille
    yaml_path: str
    declared_loss: float | None = None  # l_declared = min(pct, cad / W)
    declared_loss_pct: float | None = None
    declared_loss_cad: float | None = None
    wealth: float | None = None  # W
    loss_capacity: float | None = None  # l_cap = min(1 - q / q_max, 1 - (1 + mu_recovery)^-T)
    withdrawal_rate: float | None = None  # q
    withdrawal_rate_max: float | None = None  # q_max
    horizon_years: float | None = None  # T du seau risque
    mu_recovery: float | None = None
    goal_horizons: dict[str, float] = field(default_factory=dict)  # horizon de chaque objectif (horizon.T_risk)

    def is_below(self, loss: float | None) -> bool:
        """Vrai si cette entree de l* est sous min_L_plan : il faut la relever pour qu'une allocation existe."""
        return loss is not None and loss < self.min_planning_loss - EPSILON

    @property
    def declared_in_dollars(self) -> bool:
        """Vrai si l_declared vient de la perte declaree en dollars (cad / W) plutot que du pourcentage."""
        if self.declared_loss is None or self.declared_loss_cad is None or not self.wealth:
            return False
        return abs(self.declared_loss_cad / self.wealth - self.declared_loss) <= EPSILON

    @property
    def horizon_loss(self) -> float | None:
        """Terme d'horizon de l_cap : 1 - (1 + mu_recovery)^-T."""
        if self.horizon_years is None or self.mu_recovery is None:
            return None
        return 1 - (1 + self.mu_recovery) ** (-self.horizon_years)

    @property
    def withdrawal_loss(self) -> float | None:
        """Terme de retrait de l_cap : max(0, 1 - q / q_max), borne a 0 comme l_cap (au-dela de q_max, rien)."""
        if self.withdrawal_rate is None or not self.withdrawal_rate_max:
            return None
        return max(0.0, 1 - self.withdrawal_rate / self.withdrawal_rate_max)

    def required_horizon_years(self) -> float | None:
        """T minimal pour que le terme d'horizon de l_cap atteigne min_L_plan."""
        if self.mu_recovery is None or not 0 < self.min_planning_loss < 1:
            return None
        return math.log(1 / (1 - self.min_planning_loss)) / math.log(1 + self.mu_recovery)

    def allowed_withdrawal_rate(self) -> float | None:
        """q maximal pour que le terme de retrait de l_cap atteigne min_L_plan."""
        if not self.withdrawal_rate_max:
            return None
        return self.withdrawal_rate_max * (1 - self.min_planning_loss)


@dataclass(frozen=True)
class NoMandateCause:
    """Causes inscrites par la compilation pour une decision sans allocation (``incomplet``, ``protection``,
    ``position_attente``) : statut transmis par le profil, regle des dollars, champs obligatoires, confiance."""

    decision_kind: DecisionKind | None
    profile_status: str | None  # statut du profil, avant la regle des dollars
    status_yaml_path: str | None
    must_have_missing: list[str]
    confidence: float | None
    completeness_min: float | None
    dollar_rule: DollarRuleProtection | None
    levers: ProtectionLevers | None = None  # leviers de la regle des dollars, verifies par compilation

    @property
    def profile_protection(self) -> bool:
        """Vrai si le profil lui-meme impose la protection (signaux de vulnerabilite)."""
        return self.profile_status == ProfileStatus.PROTECTION.value

    @property
    def low_confidence(self) -> bool:
        """Vrai si la confiance du profil est sous status.completeness_min."""
        return (
            self.confidence is not None
            and self.completeness_min is not None
            and self.confidence < self.completeness_min
        )


def _last_record(trace: list[dict[str, Any]], rule: str) -> dict[str, Any] | None:
    return next((entry for entry in reversed(trace) if entry.get("rule") == rule), None)


def _dollar_rule_protection(trace: list[dict[str, Any]]) -> DollarRuleProtection | None:
    protection = _last_record(trace, "dollar_rule.protection")
    if protection is None:
        return None
    loss_budget = (_last_record(trace, "dollar_rule.l_star") or {}).get("inputs", {})
    declared = (_last_record(trace, "dollar_rule.l_declared") or {}).get("inputs", {})
    loss_capacity = (_last_record(trace, "dollar_rule.l_cap") or {}).get("inputs", {})
    risk_horizon = (_last_record(trace, "horizon.T_risk") or {}).get("inputs", {})
    return DollarRuleProtection(
        l_star=protection["inputs"]["l_star"],
        min_planning_loss=protection["inputs"]["min_L_plan"],
        yaml_path=protection["yaml_path"],
        declared_loss=loss_budget.get("l_declared"),
        declared_loss_pct=declared.get("pct"),
        declared_loss_cad=declared.get("cad"),
        wealth=declared.get("W"),
        loss_capacity=loss_budget.get("l_cap"),
        withdrawal_rate=loss_capacity.get("q"),
        withdrawal_rate_max=loss_capacity.get("q_max"),
        horizon_years=loss_capacity.get("T"),
        mu_recovery=loss_capacity.get("mu_recovery"),
        goal_horizons=dict(risk_horizon.get("goal_horizons") or {}),
    )


def no_mandate_cause(
    result: CompileResult,
    profile: InvestorProfile | None = None,
    as_of: date | None = None,
    compile_fn: Callable[[InvestorProfile, date], CompileResult] | None = None,
) -> NoMandateCause:
    """Cause enregistree d'une decision sans allocation, lue dans ``result.trace`` (regles ``status``,
    ``dollar_rule.*`` et ``decision_kind``) : l'explication la cite au lieu d'un texte generique.

    Avec le profil compile et sa date, la cause porte aussi les leviers de la regle des dollars, chacun verifie par
    une nouvelle compilation (``compile_fn``, ``compile_profile`` par defaut) du profil modifie."""
    status = _last_record(result.trace, "status") or {}
    status_inputs = status.get("inputs", {})
    kind = _last_record(result.trace, "decision_kind") or {}
    dollar_rule = _dollar_rule_protection(result.trace)
    levers = None
    if dollar_rule is not None and profile is not None and as_of is not None:
        levers = protection_levers(profile, as_of, dollar_rule, compile_fn or compile_profile)
    return NoMandateCause(
        decision_kind=result.decision_kind,
        profile_status=status_inputs.get("profile_status"),
        status_yaml_path=status.get("yaml_path"),
        must_have_missing=list(kind.get("inputs", {}).get("must_have_missing") or []),
        confidence=status_inputs.get("confidence"),
        completeness_min=status_inputs.get("completeness_min"),
        dollar_rule=dollar_rule,
        levers=levers,
    )


# --------------------------------------------------------------------------- leviers de la regle des dollars

SHORT_NEED_YEARS = 1.0  # un besoin a un an ou moins (« retraits prevus sous 12 mois ») a un horizon fixe
HORIZON_STEP_YEARS = 0.1  # pas des horizons testes ; un seau vise horizon <= T_max, on teste T_max + 0.1
SAME_HORIZON_YEARS = 1e-4  # horizon.T_risk arrondit les horizons a 4 decimales


@dataclass(frozen=True)
class GoalRef:
    """Objectif du profil vise par un levier, avec son horizon a la date de calcul (trace horizon.T_risk)."""

    goal_id: str
    label: str
    horizon_years: float


@dataclass(frozen=True)
class ProfileChange:
    """Changement du profil propose comme levier de la regle des dollars."""

    kind: Literal["max_loss_cad", "max_loss_pct", "withdrawal_rate", "goal_horizon", "without_goal"]
    value: float | None = None  # perte en $ ou en part de W, taux de retrait annuel, horizon en annees
    goal: GoalRef | None = None
    horizon_after: float | None = None  # T du seau risque une fois le changement applique

    def apply(self, profile: InvestorProfile) -> InvestorProfile:
        data = profile.model_dump()
        if self.kind == "max_loss_cad":
            data["max_acceptable_loss_cad"] = self.value
        elif self.kind == "max_loss_pct":
            data["max_acceptable_loss_pct"] = self.value
        elif self.kind == "without_goal":
            data["goals"] = [goal for goal in data["goals"] if goal["goal_id"] != self.goal.goal_id]
        elif self.kind == "goal_horizon":
            for goal in data["goals"]:
                if goal["goal_id"] == self.goal.goal_id:
                    goal.update(horizon_years=self.value, target_date=None)
        else:  # withdrawal_rate : retraits recurrents ramenes a value * W par an, au prorata
            total = sum(goal["recurring_withdrawal"] or 0.0 for goal in data["goals"])
            for goal in data["goals"]:
                if goal["recurring_withdrawal"]:
                    goal["recurring_withdrawal"] *= self.value * profile.investable_wealth / total
        return InvestorProfile.model_validate(data)


@dataclass(frozen=True)
class ProtectionLevers:
    """Leviers de la regle des dollars, verifies par une nouvelle compilation du profil modifie.

    ``required`` releve chaque entree de l* sous min_L_plan autre que l'horizon (perte declaree, retraits). Quand
    l'horizon est trop court, chaque option de ``horizon``, appliquee avec ``required``, leve dollar_rule.protection ;
    seules les options verifiees sont gardees.
    """

    required: tuple[ProfileChange, ...]
    horizon: tuple[ProfileChange, ...]
    horizon_short: bool  # le terme d'horizon de l_cap est sous min_L_plan
    horizon_goal: GoalRef | None  # objectif dont l'horizon fixe T, s'il est seul
    lifted: bool  # required avec chaque option d'horizon : plus de dollar_rule.protection
    allocation: bool  # ... et chacune de ces compilations donne un mandat (decision_kind None)


def _compile_changed(
    profile: InvestorProfile, as_of: date, compile_fn: Callable, changes: list[ProfileChange]
) -> CompileResult:
    for change in changes:
        profile = change.apply(profile)
    return compile_fn(profile, as_of)


def _dollar_rule_blocks(result: CompileResult) -> bool:
    return _last_record(result.trace, "dollar_rule.protection") is not None


def _risk_horizon(result: CompileResult) -> float | None:
    return (_last_record(result.trace, "horizon.T_risk") or {}).get("output")


def _goal_refs(profile: InvestorProfile, as_of: date, rule: DollarRuleProtection) -> list[GoalRef]:
    return [
        GoalRef(goal.goal_id, goal.label, rule.goal_horizons.get(goal.goal_id, _goal_horizon(goal, as_of)))
        for goal in profile.goals
    ]


def _total_withdrawals(profile: InvestorProfile) -> float:
    return sum(goal.recurring_withdrawal or 0.0 for goal in profile.goals)


def _required_changes(profile: InvestorProfile, rule: DollarRuleProtection) -> tuple[ProfileChange, ...]:
    """Pertes declarees (en $ et en %) relevees a min_L_plan, retraits recurrents ramenes au taux admis."""
    floor_loss = rule.min_planning_loss
    changes = []
    if rule.declared_loss_cad is not None and rule.wealth and rule.is_below(rule.declared_loss_cad / rule.wealth):
        changes.append(ProfileChange("max_loss_cad", ceil_step(floor_loss * rule.wealth, 1)))
    if rule.is_below(rule.declared_loss_pct):
        changes.append(ProfileChange("max_loss_pct", ceil_step(floor_loss, 0.001)))
    if rule.is_below(rule.withdrawal_loss) and profile.investable_wealth and _total_withdrawals(profile):
        changes.append(ProfileChange("withdrawal_rate", floor_step(rule.allowed_withdrawal_rate(), 0.001)))
    return tuple(changes)


def _longer_horizons(goal: GoalRef, rule: DollarRuleProtection) -> list[float]:
    """Horizons a tester pour un objectif, croissants : le T qui suffit a l_cap (avec ou sans reserve de retraits),
    et la sortie de chaque seau prudent (T_max + 0.1)."""
    buckets = _load_yaml(str(DEFAULT_YAML))["buckets"]
    needed = rule.required_horizon_years()
    values = {round(bucket["T_max"] + HORIZON_STEP_YEARS, 6) for bucket in buckets["rules"]}
    if needed is not None:
        values |= {ceil_step(needed, HORIZON_STEP_YEARS)}
        values |= {ceil_step(needed - buckets["withdrawal_reserve_years"], HORIZON_STEP_YEARS)}
    return sorted(value for value in values if value > goal.horizon_years + EPSILON)


def _horizon_candidates(goal: GoalRef, goals: list[GoalRef], rule: DollarRuleProtection) -> list[ProfileChange]:
    """Un besoin a un an ou moins garde son horizon : on l'ote, si d'autres objectifs restent. Sinon, son horizon
    s'allonge."""
    if goal.horizon_years <= SHORT_NEED_YEARS + EPSILON and len(goals) > 1:
        return [ProfileChange("without_goal", goal=goal)]
    return [ProfileChange("goal_horizon", value, goal) for value in _longer_horizons(goal, rule)]


def _horizon_options(
    profile: InvestorProfile,
    as_of: date,
    rule: DollarRuleProtection,
    required: tuple[ProfileChange, ...],
    compile_fn: Callable,
) -> tuple[ProfileChange, ...]:
    """Pour chaque objectif, le premier changement qui, avec ``required``, leve dollar_rule.protection."""
    goals = _goal_refs(profile, as_of, rule)
    options = []
    for goal in sorted(goals, key=lambda ref: ref.horizon_years):
        for candidate in _horizon_candidates(goal, goals, rule):
            result = _compile_changed(profile, as_of, compile_fn, [*required, candidate])
            if not _dollar_rule_blocks(result):
                options.append(replace(candidate, horizon_after=_risk_horizon(result)))
                break
    return tuple(options)


def _horizon_goal(goals: list[GoalRef], rule: DollarRuleProtection) -> GoalRef | None:
    """L'objectif dont l'horizon est T, s'il est seul (une reserve de retraits decale T : aucun ne l'est alors)."""
    if rule.horizon_years is None:
        return None
    fixing = [goal for goal in goals if abs(goal.horizon_years - rule.horizon_years) < SAME_HORIZON_YEARS]
    return fixing[0] if len(fixing) == 1 else None


def protection_levers(
    profile: InvestorProfile, as_of: date, rule: DollarRuleProtection, compile_fn: Callable
) -> ProtectionLevers:
    """Leviers qui levent la regle des dollars, chacun verifie par ``compile_fn`` sur le profil modifie."""
    required = _required_changes(profile, rule)
    horizon_short = rule.is_below(rule.horizon_loss)
    options = _horizon_options(profile, as_of, rule, required, compile_fn) if horizon_short else ()
    combos = [[*required, option] for option in options] or [list(required)]
    results = [_compile_changed(profile, as_of, compile_fn, combo) for combo in combos]
    lifted = (bool(options) or not horizon_short) and not any(_dollar_rule_blocks(result) for result in results)
    return ProtectionLevers(
        required=required,
        horizon=options,
        horizon_short=horizon_short,
        horizon_goal=_horizon_goal(_goal_refs(profile, as_of, rule), rule),
        lifted=lifted,
        allocation=lifted and all(result.decision_kind is None for result in results),
    )

