"""Accès en lecture seule à l'engine de research/backtest (propriété d'une autre session).

On n'en modifie rien : on l'importe. Chemin surchargeable par ALPHAFORGE_BT_ROOT.
"""
from __future__ import annotations

import sys

from .._engine_path import BT_ROOT

if str(BT_ROOT) not in sys.path:
    sys.path.insert(0, str(BT_ROOT))

from engine import data as bt_data  # noqa: E402
from engine import metrics as bt_metrics  # noqa: E402
from engine.strategies import ledoit_wolf  # noqa: E402

__all__ = ["BT_ROOT", "bt_data", "bt_metrics", "ledoit_wolf"]
