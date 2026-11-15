"""Indicateurs de l'étape 0 sur le jeu de départ (bibliothèque standard, point-in-time ; sûr en CI)."""

from __future__ import annotations

import pytest

from alphaforge import starter
from alphaforge.finance.strategy import load_strategy
from alphaforge.finance.strategy.features import max_drawdown, stock_features, weekly_returns

AS_OF = "2026-09-30"
CFG = load_strategy()


def test_nvda_dividends_ttm_are_point_in_time_and_ignore_the_split():
    divs = starter.dividends("NVDA", "2025-09-30", AS_OF)
    assert [d for d, _ in divs] == ["2025-12-04", "2026-03-11", "2026-06-04", "2026-09-10"]
    assert sum(v for _, v in divs) == pytest.approx(0.52)
    assert all(d <= AS_OF for d, _ in divs)
    px = starter.close_on_or_before("NVDA", AS_OF)
    assert px.date <= AS_OF
    assert starter.dividend_yield_ttm("NVDA", AS_OF) == pytest.approx(0.52 / px.close)


def test_no_dividend_gives_zero_yield():
    assert starter.dividend_yield_ttm("TSLA", AS_OF) == 0.0


def test_close_never_after_as_of():
    for t in ("RY.TO", "AAPL", "BTC-USD"):
        assert starter.close_on_or_before(t, "2024-12-25").date <= "2024-12-25"


def test_fx_forward_fills_canadian_holidays():
    assert starter.usdcad_on_or_before("2025-07-01") == starter.usdcad_on_or_before("2025-06-30")


def test_weekly_returns_use_only_dates_up_to_as_of():
    r = weekly_returns("ENB.TO", "2024-06-30", 52)
    assert r and all(d <= "2024-06-30" for d, _ in r)


def test_features_are_deterministic_and_bounded():
    a, sa, da = stock_features("FTS.TO", AS_OF, CFG)
    b, _, _ = stock_features("FTS.TO", AS_OF, CFG)
    assert a == b and da["beta_index"] == "XIU.TO"
    assert 0 < a["vol"] < 1 and -1 <= a["corr_core"] <= 1 and 0 <= a["mdd_short"] < 1
    assert sa["vol"] == "FAIT"
    us, _, du = stock_features("JNJ", AS_OF, CFG)
    assert du["beta_index"] == "SPY" and us["liquidity_cad"] > 0


def test_max_drawdown_of_a_known_path():
    assert max_drawdown("SPY", AS_OF) >= 0.0


def test_unknown_ticker_gives_missing_features_not_an_error():
    from alphaforge.finance.strategy.features import beta

    assert beta("BMO.TO", AS_OF, CFG) == (None, "?")
    assert weekly_returns("BMO.TO", AS_OF, 52) == []
