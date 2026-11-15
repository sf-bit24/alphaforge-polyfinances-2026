"""Seuls les tests qui appellent l'optimiseur sont sautés si les données longues du moteur de backtest
(``alphaforge/data/long``, parquets non versionnés) ou numpy/pandas manquent; F1 tourne sans eux."""

from __future__ import annotations

from alphaforge.finance.backtest.paths import long_data_available

NEEDS_ENGINE = {"test_integration_optimizer.py"}  # les autres tournent sans numpy (F1 pur)


def pytest_ignore_collect(collection_path, config):
    if collection_path.name in NEEDS_ENGINE and not long_data_available():
        return True
    return None
