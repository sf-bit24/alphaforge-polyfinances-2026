"""Tests sautés tant que l'engine de backtest (research/backtest) est absent, comme tests/finance."""

from __future__ import annotations

from alphaforge.finance._engine_path import engine_available

NEEDS_ENGINE = {
    "test_pipeline_rules.py",
    "test_integration_optimizer.py",
    "test_personas.py",
    "test_from_profile_view.py",
    "test_monotonicity.py",
    "test_status_emphasis.py",
    "test_adapter.py",
}


def pytest_ignore_collect(collection_path, config):
    if collection_path.name in NEEDS_ENGINE and not engine_available():
        return True
    return None
