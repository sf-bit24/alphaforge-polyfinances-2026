"""Contrats de l'évolution du portefeuille dans le temps (tick mensuel, rejeu).

PROPOSITION v0.1 (2026-11-15), à valider par l'équipe. SIMULATION SEULEMENT : chaque mouvement est un
« événement de rééquilibrage illustratif », jamais un ordre ni un conseil.

Principe : le code calcule (dérive, bandes, overlays, Judge), le modèle n'explique qu'à partir des
``Fact`` produits ici. Les poids sont des fractions du portefeuille (somme = 1).
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .decision import Explanation, Fact

SCHEMA_VERSION = "0.1.0"
EVENT_LABEL = "événement de rééquilibrage illustratif"

Action = Literal["HOLD", "REBALANCE_TO_BANDS", "OVERLAY_SHIFT", "REOPTIMIZE", "REPROFILE_REQUIRED"]
TradeReason = Literal["flow", "band", "overlay", "glidepath", "reoptimize", "liquidation"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Trade(_Strict):
    """Mouvement illustratif d'une ligne (aucun ordre réel)."""
    asset_id: str
    w_from: float
    w_to: float
    dw: float
    amount_cad: float
    reason: TradeReason

    @model_validator(mode="after")
    def _consistent(self) -> Trade:
        if abs((self.w_to - self.w_from) - self.dw) > 1e-9:
            raise ValueError(f"{self.asset_id}: dw incohérent")
        return self


class TriggerFired(_Strict):
    code: str                              # HORIZON_LEVEL_CHANGE, DRAWDOWN_LIMIT, ...
    blocking: bool                         # bloquant -> REPROFILE_REQUIRED, aucune opération
    value: float | str | None = None
    threshold: float | str | None = None
    threshold_source: str                  # chemin YAML ou champ du profil d'où vient le seuil
    message_fr: str


class OverlayState(_Strict):
    name: str
    active: bool                           # False = « testé, non retenu » ou désactivé
    gate: Literal["passe", "echoue", "desactive", "non_evalue"]
    gate_reason_fr: str
    signal: float | None = None            # signal brut (ex. +1 / -1, rang)
    delta: dict[str, float] = Field(default_factory=dict)   # déplacement de cible appliqué (après bornes)
    clipped: bool = False                  # vrai si les bornes ont rogné le déplacement
    fact_ids: list[str] = Field(default_factory=list)


class RebalanceEvent(_Strict):
    event_id: str
    month: date
    action: Action
    label: Literal["événement de rééquilibrage illustratif"] = EVENT_LABEL
    drift: float                           # Σ|w - w*| / 2 avant opération
    breaches: list[str] = Field(default_factory=list)
    triggers: list[TriggerFired] = Field(default_factory=list)
    overlays: list[OverlayState] = Field(default_factory=list)
    trades: list[Trade] = Field(default_factory=list)
    flow_cad: float = 0.0
    turnover_oneway: float = 0.0           # 0,5 · Σ|dw|
    turnover_twoway: float = 0.0           # Σ|dw| (convention de l'optimiseur)
    cost_cad: float = 0.0
    judge_before: Literal["approuve", "refuse", "non_evalue"] = "non_evalue"
    judge_after: Literal["approuve", "refuse", "non_evalue"] = "non_evalue"
    judge_violations_after: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)


class PortfolioVersion(_Strict):
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    version_id: str
    parent_version_id: str | None
    seq: int = Field(ge=0)
    client_id: str
    profile_version: int = Field(ge=1)
    decision_id: str | None = None
    as_of: date
    weights: dict[str, float]              # après l'événement du mois
    value_cad: float = Field(ge=0)
    target: dict[str, float]               # cible stratégique (après overlays)
    level: str                             # N0..N5
    policy_hash: str
    data_version: str
    config_hash: str
    event: RebalanceEvent
    status: Literal["FICTION"] = "FICTION"  # trajectoire simulée

    @model_validator(mode="after")
    def _weights(self) -> PortfolioVersion:
        s = sum(self.weights.values())
        if self.weights and abs(s - 1.0) > 1e-6:
            raise ValueError(f"poids de la version {self.version_id} : somme {s}")
        if any(w < -1e-9 for w in self.weights.values()):
            raise ValueError("poids négatif")
        return self


class PerfSnapshot(_Strict):
    """Mesures calculées par le code depuis le début de la trajectoire."""
    months: int
    value_cad: float
    invested_cad: float                    # apports nets cumulés (y compris le capital initial)
    twr_cum: float
    twr_ann: float | None                  # None si moins de 12 mois (on n'annualise pas)
    mwr_ann: float | None
    cagr: float | None
    max_drawdown: float
    current_drawdown: float
    high_water_mark_cad: float
    months_underwater: int
    cash_drag: float | None = None
    turnover_oneway_cum: float = 0.0
    costs_cad_cum: float = 0.0


class TickResult(_Strict):
    version: PortfolioVersion
    perf: PerfSnapshot
    facts: list[Fact] = Field(default_factory=list)
    explanation: Explanation | None = None
    reprofile_triggers_fired: list[str] = Field(default_factory=list)


class ComparatorRow(_Strict):
    """Stratégie testée (overlay ou référence). Toujours avec le nombre d'essais et le DSR."""
    name: str
    applied: bool
    n_trials: int = Field(ge=1)
    sharpe: float | None
    dsr: float | None
    pbo: float | None = None
    cagr: float | None
    max_drawdown: float | None
    turnover_ann: float | None
    verdict_fr: str


class ReplayResult(_Strict):
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    run_id: str
    client_id: str
    persona_label: str
    window: tuple[date, date]
    versions: list[PortfolioVersion]
    perf: PerfSnapshot
    comparators: list[ComparatorRow] = Field(default_factory=list)
    overlays_gate: list[OverlayState] = Field(default_factory=list)
    n_events_by_action: dict[str, int] = Field(default_factory=dict)
    facts: list[Fact] = Field(default_factory=list)
    explanations: dict[str, Explanation] = Field(default_factory=dict)   # event_id -> explication
    config_hash: str
    data_version: str
    digest: str                            # sha256 canonique du rejeu (contrôle de déterminisme)
