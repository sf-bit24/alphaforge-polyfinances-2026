import pytest

# The engine needs the `finance` dependency group (numpy, pandas, scipy), not installed by a plain `uv sync`.
pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("scipy")

import numpy as np

from alphaforge.finance.backtest import metrics as M


def test_growth_drawdown_recovery():
    r = [0.10, -0.50, 1.00]
    assert M.cumulative_growth(r) == pytest.approx(1.1)
    assert M.max_drawdown(r) == pytest.approx(0.5)
    assert M.recovery_months(r) == 1.0
    assert M.max_underwater_months(r) == 1


def test_never_recovers_is_nan():
    assert np.isnan(M.recovery_months([0.1, -0.2, 0.05]))


def test_annualized_and_real():
    r = np.full(24, 0.01)
    assert M.annualized_return(r) == pytest.approx(1.01 ** 12 - 1)
    assert M.annualized_real_return(r, np.full(24, 0.01)) == pytest.approx(0.0, abs=1e-12)
    assert M.volatility(r) == pytest.approx(0.0, abs=1e-12)


def test_sharpe_sortino_known():
    r = np.array([0.02, 0.0] * 6)
    # mean 0.01, sample std = sqrt(12/11)*0.01
    assert M.sharpe(r) == pytest.approx(0.01 / (0.01 * np.sqrt(12 / 11)) * np.sqrt(12))
    assert np.isnan(M.sortino(r))  # no downside -> undefined
    r2 = np.array([0.03, -0.01])
    # downside dev = sqrt(mean([0, 1e-4])) = 0.0070711 ; sortino = 0.01*12 / (0.0070711*sqrt(12))
    assert M.sortino(r2) == pytest.approx(0.12 / (np.sqrt(0.5e-4) * np.sqrt(12)))


def test_var_cvar_historical():
    r = np.arange(-10, 10) / 100.0  # -0.10 .. 0.09, 20 values
    v, cv = M.var_cvar(r, 0.05)
    assert v == pytest.approx(0.10)
    assert cv == pytest.approx(0.10)
    v, cv = M.var_cvar(r, 0.10)
    assert v == pytest.approx(0.09) and cv == pytest.approx(0.095)


def test_calmar_worst_window():
    r = [0.1, -0.2, 0.1, 0.1]
    assert M.worst_window_return(r, 2) == pytest.approx(0.8 * 1.1 - 1)
    assert M.calmar(r) == pytest.approx(M.annualized_return(r) / 0.2)


def test_wealth_with_flows_and_depletion():
    assert M.final_wealth([0.0, 0.0], 100, [10, 10]) == pytest.approx(120)
    assert M.final_wealth([0.1], 100, [0]) == pytest.approx(110)
    w = M.wealth_path([0.0, 0.0, 0.5], 100, [-60, -60, 100])
    assert list(w) == [40, 0, 0]  # depleted wealth stays at zero


def test_shortfall_turnover():
    assert M.shortfall_probability([0.01, 0.05, -0.02, 0.03], 0.02) == pytest.approx(0.5)
    assert M.turnover([0.5, 0.5], [0.7, 0.3]) == pytest.approx(0.2)
