import pytest

# The engine needs the `finance` dependency group (numpy, pandas, scipy), not installed by a plain `uv sync`.
pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("scipy")

import pandas as pd

from alphaforge.finance.backtest.windows import windows


def test_non_overlapping_3y_1926_2026():
    w = windows(3, "1926-07", "2026-09", "non_overlapping")
    n_months = len(pd.date_range("1926-07-31", "2026-09-30", freq="ME"))
    assert len(w) == n_months // 36 == 33
    assert all(x.n_months == 36 for x in w)
    assert w[1].start == w[0].end + pd.offsets.MonthEnd(1)


def test_rolling_step():
    w = windows(10, "2000-01", "2019-12", "rolling", step_months=12)
    assert len(w) == 11
    assert w[1].start == pd.Timestamp("2001-01-31")
    assert w[-1].end == pd.Timestamp("2019-12-31")
