import numpy as np
import pandas as pd
import pytest

from engine.bonds import bond_returns_from_yields, par_bond_price


def test_hand_computed_price_2y_semiannual():
    # coupon 6 %, yield 7 %, exactly 2 years left -> 4 half-years at 3.5 %
    # 0.03/1.035 + 0.03/1.035^2 + 0.03/1.035^3 + 1.03/1.035^4 = 0.981635 (hand computed)
    assert par_bond_price(0.06, 0.07, 2.0) == pytest.approx(0.981635, abs=2e-6)


def test_price_matches_explicit_cashflows_integer_periods():
    c, y, n = 0.05, 0.04, 20  # 10 years
    cf = sum((c / 2) / (1 + y / 2) ** k for k in range(1, n + 1)) + 1 / (1 + y / 2) ** n
    assert par_bond_price(c, y, 10.0) == pytest.approx(cf, rel=1e-12)


def test_par_bond_prices_at_par_and_zero_yield():
    assert par_bond_price(0.05, 0.05, 9 + 11 / 12) == pytest.approx(1.0, abs=1e-12)
    assert par_bond_price(0.03, 0.0, 5.0) == pytest.approx(1.15, abs=1e-12)


def test_monthly_return_unchanged_yield_is_carry():
    y = pd.Series([4.0, 4.0, 4.0])
    r = bond_returns_from_yields(y, 10)
    assert np.isnan(r.iloc[0])
    assert r.iloc[1] == pytest.approx(0.04 / 12, abs=1e-12)


def test_monthly_return_hand_case():
    # maturity N = 2 + 1/12 so that after one month exactly 2 years remain (case above)
    r = bond_returns_from_yields(pd.Series([6.0, 7.0]), 2 + 1 / 12)
    assert r.iloc[1] == pytest.approx(0.981635 - 1 + 0.06 / 12, abs=2e-6)


def test_rising_yield_loses_more_for_longer_maturity():
    y = pd.Series([3.0, 4.0])
    assert bond_returns_from_yields(y, 20).iloc[1] < bond_returns_from_yields(y, 2).iloc[1] < 0
