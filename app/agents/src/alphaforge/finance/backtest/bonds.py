"""Synthetic constant-maturity bond returns from yield series.

Method (documented in data/SOURCES.md and tested in tests/test_bonds.py):

At the end of month t-1 we buy a newly issued *par* bond with maturity N years
whose coupon equals the yield y_{t-1} (semi-annual coupons). One month later the
bond has N - 1/12 years left and is re-priced at the new yield y_t. The bond is
then sold and a new par bond is bought (constant maturity). Monthly total return:

    r_t = P(c=y_{t-1}, y=y_t, M=N-1/12) - 1 + y_{t-1}/12

where P is the price (per 1 of face) of a bond with annual coupon rate c paid
semi-annually, yield-to-maturity y (semi-annual compounding) and M years left:

    P = (c/y) * (1 - (1+y/2)^(-2M)) + (1+y/2)^(-2M)        (y != 0)
    P = 1 + c*M                                            (y == 0)

The fractional number of periods (2M is not an integer) is handled by the
continuous annuity formula above — a standard simplification for index
reconstruction (no accrued-interest/day-count detail). Yields are in DECIMAL.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def par_bond_price(coupon: float | np.ndarray, ytm: float | np.ndarray, years: float) -> np.ndarray:
    """Price per 1 face of a semi-annual coupon bond (decimal rates)."""
    coupon_rate = np.asarray(coupon, dtype=float)
    yield_rate = np.asarray(ytm, dtype=float)
    n = 2.0 * years  # semi-annual periods
    with np.errstate(divide="ignore", invalid="ignore"):
        discount = (1.0 + yield_rate / 2.0) ** (-n)
        return np.where(
            np.abs(yield_rate) < 1e-12,
            1.0 + coupon_rate * years,
            (coupon_rate / yield_rate) * (1.0 - discount) + discount,
        )


def bond_returns_from_yields(yields_pct: pd.Series, maturity_years: float) -> pd.Series:
    """Monthly total returns of a constant-maturity par bond.

    yields_pct: monthly yields in PERCENT (e.g. 4.25), indexed by month.
    Returns a series aligned on yields_pct.index; the first value is NaN.
    Missing yields propagate as NaN (no interpolation here).
    """
    yields = yields_pct.astype(float) / 100.0
    previous = yields.shift(1)
    price = par_bond_price(previous.values, yields.values, maturity_years - 1.0 / 12.0)
    returns = price - 1.0 + previous.values / 12.0
    return pd.Series(returns, index=yields_pct.index, name=yields_pct.name)
