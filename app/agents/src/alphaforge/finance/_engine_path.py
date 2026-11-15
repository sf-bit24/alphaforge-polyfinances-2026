"""Où trouver l'engine de backtest (research/backtest), sans l'importer."""
from __future__ import annotations

import os
from pathlib import Path

BT_ROOT = Path(os.environ.get("ALPHAFORGE_BT_ROOT", Path(__file__).resolve().parents[5] / "research" / "backtest"))


def engine_available() -> bool:
    return (BT_ROOT / "engine" / "__init__.py").exists() and (BT_ROOT / "data" / "processed").exists()
