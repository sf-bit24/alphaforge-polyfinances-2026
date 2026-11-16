"""Tests sautés si les données longues du moteur de backtest (``alphaforge/data/long``, parquets non versionnés)
ou numpy/pandas manquent, comme tests/finance."""

from __future__ import annotations

from alphaforge.finance.backtest.paths import long_data_available

NEEDS_ENGINE = {
    "test_pipeline_rules.py",
    "test_every_profile_portfolio.py",
    "test_pipeline_holdings.py",
    "test_integration_optimizer.py",
    "test_personas.py",
    "test_from_profile_view.py",
    "test_monotonicity.py",
    "test_status_emphasis.py",
    "test_adapter.py",
    "test_allocation_pipeline.py",
}


def pytest_ignore_collect(collection_path, config):
    if collection_path.name in NEEDS_ENGINE and not long_data_available():
        return True
    return None
