"""Fixtures of the backtest engine tests.

The processed dataset (``alphaforge/data/long/*.parquet``) is not versioned (licences: yfinance, Moody's, OECD).
Without it, the tests that read data are skipped with an explicit reason; the pure ones (bonds, metrics,
windows, ...) still run. Without the ``finance`` dependency group, every test module skips itself
(``pytest.importorskip``). This file only uses the standard library so that it loads in both cases.
"""
import copy
from pathlib import Path

import pytest

from alphaforge.finance.backtest.paths import data_dir, long_data_available

DATA_DIR = data_dir()
HAS_DATA = long_data_available(("numpy", "pandas", "pyarrow"))
HERE = Path(__file__).resolve().parent
DATA_TEST_FILES = {"test_constraints.py", "test_data.py", "test_engine.py", "test_lookahead.py"}
REBUILD = "uv run --group finance --group backtest-data python -I -m alphaforge.finance.backtest.build_data"


def pytest_collection_modifyitems(config, items):
    if HAS_DATA:
        return
    skip = pytest.mark.skip(reason=f"{DATA_DIR}/*.parquet (or pyarrow) missing: run `{REBUILD}` first")
    for item in items:  # the hook sees every collected item: only mark the data tests of this folder
        if item.path.resolve().parent == HERE and item.path.name in DATA_TEST_FILES:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def example_profile():
    from alphaforge.finance.backtest.profile import load_profile

    return load_profile("example")


@pytest.fixture
def prof(example_profile):
    return copy.deepcopy(example_profile)
