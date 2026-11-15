"""Volet finance AlphaForge AI — F2 (optimiseur), F3 (analyses), F4 (contrôle du Judge).

Entrée : un ``contracts.PolicySpec`` produit par F1 (hors de ce paquet).
Données : moteur de backtest ``alphaforge.finance.backtest`` (données longues ``alphaforge/data/long``).
SIMULATION SEULEMENT — aucun conseil financier, aucun ordre.
"""

from .analysis import (
    diversification_report,
    horizon_report,
    lookthrough_report,
    portfolio_returns,
    risk_report,
    stress_report,
)
from .judge import JudgeReport, check, framed_alternative
from .market import InsufficientHistoryError, ReturnWindow, returns_window
from .optimizer import OptimizationResult, optimize, project

__all__ = [
    "InsufficientHistoryError",
    "JudgeReport",
    "OptimizationResult",
    "ReturnWindow",
    "check",
    "diversification_report",
    "framed_alternative",
    "horizon_report",
    "lookthrough_report",
    "optimize",
    "portfolio_returns",
    "project",
    "returns_window",
    "risk_report",
    "stress_report",
]
