"""Tests du volet finance. Ceux qui lisent les données longues du moteur de backtest (``alphaforge/data/long``,
parquets non versionnés) sont sautés si ces parquets ou numpy/pandas manquent, pour ne pas casser la CI
(``uv sync --frozen`` n'installe pas le groupe ``finance``)."""
from __future__ import annotations

import importlib.util

from alphaforge.finance.backtest.paths import long_data_available

NEEDS_DATA = {"test_portfolio.py"}


def pytest_ignore_collect(collection_path, config):
    if collection_path.name in NEEDS_DATA and not long_data_available():
        return True
    if collection_path.name == "test_llm_replay.py" and importlib.util.find_spec("strands") is None:
        return True
    return None
