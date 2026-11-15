"""Tests de l'étape 0. Les modules purs (style, rules, features, config) tournent en CI ; ceux qui lisent les
données longues du moteur ou l'optimiseur sont sautés si les parquets ou numpy/pandas manquent."""

from __future__ import annotations

from alphaforge.finance.backtest.paths import long_data_available

NEEDS_DATA = {
    "test_scoring.py",
    "test_select.py",
    "test_pipeline_strategy.py",
    "test_okf_fundamentals_engine.py",
    "test_review_fixes.py",
}


def pytest_ignore_collect(collection_path, config):
    if collection_path.name in NEEDS_DATA and not long_data_available():
        return True
    return None
