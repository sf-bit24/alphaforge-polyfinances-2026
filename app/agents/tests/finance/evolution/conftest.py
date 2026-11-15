"""Tests de l'évolution du portefeuille.

- ``test_contracts_*.py`` : pydantic seulement, tournent toujours en CI.
- les autres demandent numpy/pandas/cvxpy (groupe ``finance``, absent de ``uv sync --frozen``) : sautés sans eux ;
- ``test_data_*.py`` lisent en plus les données longues (parquets non versionnés) : sautés sans elles.
"""
from __future__ import annotations

import importlib.util

from alphaforge.finance.backtest.paths import long_data_available

_HAS_FINANCE = all(importlib.util.find_spec(m) is not None for m in ("numpy", "pandas", "cvxpy"))


def pytest_ignore_collect(collection_path, config):
    name = collection_path.name
    if not name.startswith("test_") or name.startswith("test_contracts_"):
        return None
    if not _HAS_FINANCE:
        return True
    if name.startswith("test_data_") and not long_data_available():
        return True
    return None
