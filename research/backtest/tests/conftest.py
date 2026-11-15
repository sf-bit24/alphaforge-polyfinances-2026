import copy

import pytest

from engine.data import DATA_DIR
from engine.profile import load_profile

# The processed dataset is not versioned (licences: yfinance, Moody's, OECD). Without it, the tests that read
# data are skipped with an explicit reason; the pure ones (bonds, metrics, windows, ...) still run.
HAS_DATA = (DATA_DIR / "monthly_returns.parquet").exists()
DATA_TEST_FILES = {"test_constraints.py", "test_data.py", "test_engine.py", "test_lookahead.py"}


def pytest_collection_modifyitems(config, items):
    if HAS_DATA:
        return
    skip = pytest.mark.skip(reason="data/processed/*.parquet missing: run `python -I data/build_data.py` first")
    for item in items:
        if item.path.name in DATA_TEST_FILES:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def example_profile():
    return load_profile("example")


@pytest.fixture
def prof(example_profile):
    return copy.deepcopy(example_profile)
