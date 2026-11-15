"""Alias de compatibilité : l'ancien accès par chemin à l'engine de research/backtest.

Le moteur est désormais le sous-paquet ``alphaforge.finance.backtest`` ; les modules de ``portfolio`` l'importent
directement. Ce module ne reste que pour les scripts qui importent encore
``alphaforge.finance.portfolio._engine`` (``scripts/finance/feasibility_levels.py``) ; à retirer quand ils
importeront le sous-paquet.
"""
from __future__ import annotations

from ..backtest import data as bt_data
from ..backtest import metrics as bt_metrics
from ..backtest.strategies import ledoit_wolf

__all__ = ["bt_data", "bt_metrics", "ledoit_wolf"]
