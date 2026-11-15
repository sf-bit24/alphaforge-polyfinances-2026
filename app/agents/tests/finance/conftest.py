"""Tests du volet finance. Ceux qui lisent l'engine de backtest (research/backtest, branche
feat/backtest-engine) sont sautés tant qu'il n'est pas présent, pour ne pas casser la CI."""
from __future__ import annotations

import importlib.util

from alphaforge.finance._engine_path import engine_available

NEEDS_ENGINE = {"test_portfolio.py"}


def pytest_ignore_collect(collection_path, config):
    if collection_path.name in NEEDS_ENGINE and not engine_available():
        return True
    if collection_path.name == "test_llm_replay.py" and importlib.util.find_spec("strands") is None:
        return True
    return None
