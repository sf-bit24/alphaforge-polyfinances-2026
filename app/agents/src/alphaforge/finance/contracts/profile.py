"""InvestorProfile — contrat entre le volet profil (Mikael) et le volet finance.

PROPOSITION v0.1 (2026-11-14), à valider par l'équipe. Simulation seulement, jamais un conseil.

Règles :
- Le profil décrit la personne : identité, objectifs, contraintes, préférences, biais.
  Il ne contient **aucun** poids de portefeuille ni aucune cible de performance ;
  le moteur finance dérive les seuils à partir de ces champs.
- Toute information non fournie reste ``None`` et figure dans ``missing_info`` :
  le moteur ne la devine jamais.
- La capacité de risque est évaluée à partir de faits (horizon, dettes, revenus, réserve) ;
  l'utilisateur ne peut pas la dépasser (risque effectif = min(tolérance, capacité)).
"""
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.1.0"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, str_strip_whitespace=True)


# --- Énumérations ---------------------------------------------------------------------------

class ProfileStatus(StrEnum):
    COMPLETE = "COMPLETE"          # assez d'information pour une proposition
    INCOMPLETE = "INCOMPLETE"      # info critique manquante -> position d'attente
    PROTECTION = "PROTECTION"      # signaux de vulnérabilité -> mode protection


class KnowledgeLevel(StrEnum):
    DEBUTANT = "debutant"
    INTERMEDIAIRE = "intermediaire"
    AVANCE = "avance"


class Priority(StrEnum):
    BESOIN = "besoin"      # essentiel : pas de prise de risque qui le compromette
    ENVIE = "envie"
    SOUHAIT = "souhait"


class AccountType(StrEnum):
    CELI = "CELI"
    REER = "REER"
    FERR = "FERR"
    REEE = "REEE"
    REEI = "REEI"
    CELIAPP = "CELIAPP"
    CRI_FRV = "CRI_FRV"
    NON_ENREGISTRE = "non_enregistre"
    AUTRE = "autre"


class BiasKind(StrEnum):
    COGNITIF = "cognitif"      # à modérer par les données
    EMOTIONNEL = "emotionnel"  # à accommoder par la structure du portefeuille


class ClaimKind(StrEnum):
    FAIT = "fait"
    RUMEUR = "rumeur"
    DECLARE_NON_VERIFIE = "declare_non_verifie"


Currency = Literal["CAD", "USD", "EUR", "PHP", "autre"]


# --- Blocs ----------------------------------------------------------------------------------

class Score(_Strict):
    """Score 0-100 avec son origine (questionnaire, test psychométrique, déclaration)."""
    value: float = Field(ge=0, le=100)
    label: str | None = None                  # ex. « modérée »
    method: str | None = None                 # ex. « questionnaire v1 », « Holt-Laury »
    confidence: float | None = Field(default=None, ge=0, le=1)


class Goal(_Strict):
    goal_id: str
    label: str
    priority: Priority
    amount: float | None = Field(default=None, ge=0)
    currency: Currency = "CAD"
    target_date: date | None = None
    horizon_years: float | None = Field(default=None, ge=0)
    min_success_prob: float | None = Field(default=None, ge=0, le=1)
    beneficiary: str | None = None             # rôle, jamais un vrai nom (ex. « fille »)
    legal_owner: str | None = None             # à qui appartient l'argent
    recurring_withdrawal: float | None = Field(default=None, ge=0)  # décaissement annuel visé
    indexed_to_inflation: bool | None = None

    @model_validator(mode="after")
    def _horizon_known(self) -> Goal:
        if self.target_date is None and self.horizon_years is None:
            raise ValueError(f"objectif {self.goal_id}: target_date ou horizon_years requis")
        return self


class HouseholdMember(_Strict):
    role: str                                  # « personne », « conjoint »
    age: int | None = Field(default=None, ge=0, le=120)
    tolerance: Score | None = None


class Income(_Strict):
    annual_amount: float | None = Field(default=None, ge=0)
    currency: Currency = "CAD"
    variability: Literal["stable", "variable", "saisonnier", "erratique"] | None = None
    monthly_calendar: list[float] | None = Field(default=None, min_length=12, max_length=12)
    sector: str | None = None                  # pour le capital humain (ex. « energie »)
    employer_ticker: str | None = None


class Debt(_Strict):
    label: str
    balance: float = Field(ge=0)
    annual_rate: float = Field(ge=0)           # 0.20 = 20 %
    rate_type: Literal["fixe", "variable"] | None = None
    tax_deductible: bool | None = None


class RecurringLiability(_Strict):
    label: str
    amount: float = Field(ge=0)
    currency: Currency = "CAD"
    frequency: Literal["mensuel", "trimestriel", "annuel", "saisonnier"]


class Pension(_Strict):
    kind: Literal["RPC", "RRQ", "PSV", "SRG", "PD", "CD", "rente", "autre"]  # PD = prestations déterminées
    monthly_amount: float | None = Field(default=None, ge=0)
    start_age: int | None = Field(default=None, ge=0, le=120)
    indexed: bool | None = None


class IlliquidAsset(_Strict):
    label: str                                 # « terres agricoles », « œuvre d'art »
    value_low: float | None = Field(default=None, ge=0)
    value_high: float | None = Field(default=None, ge=0)
    valuation_source: str | None = None        # ESTIMATION_TIERCE, déclaratif...


class EmployerEquity(_Strict):
    ticker: str | None = None                  # None si société privée
    value: float | None = Field(default=None, ge=0)
    kind: Literal["actions", "options", "UAR", "UAP", "regime_achat"] | None = None
    vesting_note: str | None = None
    blackout: bool = False                     # période d'interdiction en cours


class FutureInflow(_Strict):
    label: str
    amount: float = Field(ge=0)
    currency: Currency = "CAD"
    status: Literal["encaisse", "conditionnel"]
    expected_date: date | None = None


class Holding(_Strict):
    """Position existante (mode hybride)."""
    ticker: str
    market_value: float = Field(ge=0)
    currency: Currency = "CAD"
    account: AccountType = AccountType.NON_ENREGISTRE
    reason: str | None = None                  # pourquoi l'investisseur la détient


class ValueFilter(_Strict):
    rule: str                                  # ex. « exclure combustibles fossiles », « charia »
    per_ticker: dict[str, Literal["exclu", "zone_grise", "admis"]] = Field(default_factory=dict)
    decided_utc: datetime | None = None        # quand l'utilisateur a tranché les zones grises


class Preferences(_Strict):
    tilts: list[str] = Field(default_factory=list)           # thèmes souhaités (« IA »)
    value_filters: list[ValueFilter] = Field(default_factory=list)
    esg_required: bool = False
    accept_indirect_exposure: bool | None = None              # via FNB larges (look-through)
    reference_currency: Currency = "CAD"


class LegalConstraint(_Strict):
    kind: str                                  # « periode_interdiction », « gel_actifs », « employeur »
    detail: str
    blocking: bool = True
    tickers: list[str] = Field(default_factory=list)


class UserRule(_Strict):
    """Règle pré-engagée par l'utilisateur lui-même (friction voulue, protocole automatique)."""
    rule: str
    version: int = 1
    cooldown_days: int = Field(default=0, ge=0)


class Bias(_Strict):
    kind_label: str                            # « familiarite », « FOMO », « ancrage »...
    kind: BiasKind
    evidence: str                              # citation ou réponse qui le montre


class Claim(_Strict):
    text: str
    classification: ClaimKind


# --- Profil ---------------------------------------------------------------------------------

class InvestorProfile(_Strict):
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    profile_id: str
    version: int = Field(default=1, ge=1)
    created_utc: datetime
    status: ProfileStatus
    mode: Literal["persona", "saisi", "hybride"] = "saisi"

    age: int | None = Field(default=None, ge=0, le=120)
    province: str | None = None
    language: Literal["fr", "en"] = "fr"
    plain_language: bool = False
    knowledge_level: KnowledgeLevel | None = None
    experience_note: str | None = None

    goals: list[Goal] = Field(min_length=1)
    household: list[HouseholdMember] = Field(default_factory=list)
    household_rule: Literal["min_tolerance", "par_objectif", "a_trancher"] | None = None

    tolerance_declared: Score | None = None
    tolerance_tested: Score | None = None
    capacity_assessed: Score | None = None
    capacity_rationale: str | None = None
    composure: Score | None = None
    max_acceptable_loss_pct: float | None = Field(default=None, ge=0, le=1)
    max_acceptable_loss_cad: float | None = Field(default=None, ge=0)

    investable_wealth: float | None = Field(default=None, ge=0)
    monthly_expenses: float | None = Field(default=None, ge=0)
    emergency_fund_months: float | None = Field(default=None, ge=0)
    income: Income | None = None
    debts: list[Debt] = Field(default_factory=list)
    recurring_liabilities: list[RecurringLiability] = Field(default_factory=list)
    pensions: list[Pension] = Field(default_factory=list)
    illiquid_assets: list[IlliquidAsset] = Field(default_factory=list)
    employer_equity: list[EmployerEquity] = Field(default_factory=list)
    future_inflows: list[FutureInflow] = Field(default_factory=list)
    holdings: list[Holding] = Field(default_factory=list)
    accounts: list[AccountType] = Field(default_factory=list)

    preferences: Preferences = Field(default_factory=Preferences)
    legal_constraints: list[LegalConstraint] = Field(default_factory=list)
    user_rules: list[UserRule] = Field(default_factory=list)
    biases: list[Bias] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)

    trusted_person_role: str | None = None     # rôle seulement (« fille »), consentement requis
    trusted_person_consent: bool = False
    unavailable_until: date | None = None
    unauthorized_third_parties: list[str] = Field(default_factory=list)

    consistency_flags: list[str] = Field(default_factory=list)   # ex. « tolerance>capacite »
    missing_info: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    reprofile_triggers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _coherence(self) -> InvestorProfile:
        if self.status is ProfileStatus.COMPLETE and self.missing_info:
            raise ValueError("un profil COMPLETE ne peut pas avoir de missing_info")
        ids = [g.goal_id for g in self.goals]
        if len(ids) != len(set(ids)):
            raise ValueError("goal_id en double")
        if self.trusted_person_role and not self.trusted_person_consent:
            raise ValueError("personne de confiance déclarée sans consentement")
        return self
