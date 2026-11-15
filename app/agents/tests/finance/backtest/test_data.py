import pytest

# The engine needs the `finance` dependency group (numpy, pandas, scipy), not installed by a plain `uv sync`.
pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("scipy")

import numpy as np
import pandas as pd

from alphaforge.finance.backtest.data import DATA_DIR, load_assets, load_inflation, load_returns

ALLOWED = {"equity_us", "equity_ca", "sector_us", "equity_single", "etf_equity", "etf_bond", "bond_synthetic",
           "cash", "commodity", "crypto"}


def test_catalogue_classes_and_universe():
    a = load_assets()
    assert set(a["asset_class"]) <= ALLOWED
    for t in ["RY.TO", "AAPL", "SPY", "XBB.TO", "GLD", "BTC-USD", "ETH-USD", "CNQ.TO"]:
        assert t in a.index
    proxies = {"US_MKT", "UST_TBILL", "US_IND_BUSEQ", "UST_2Y", "UST_5Y", "UST_10Y", "UST_20Y", "GOLD", "CA_EQ"}
    assert proxies <= set(a.index)


def test_common_dates_and_limiting_asset():
    with pytest.warns(UserWarning):
        R = load_returns(["US_MKT", "BTC-USD"], start="1926-07", currency="USD")
    assert R.notna().all().all()
    assert R.attrs["info"]["limiting_start_asset"] == "BTC-USD"
    assert R.index.min() >= pd.Timestamp("2014-09-30")


def test_cad_needs_fx_unless_flat():
    R = load_returns(["US_MKT"], currency="CAD")
    assert R.index.min() == pd.Timestamp("1971-02-28")
    Rf = load_returns(["US_MKT"], currency="CAD", fx_fill="flat")
    assert Rf.index.min() == pd.Timestamp("1926-07-31")
    assert "US_MKT" in Rf.attrs["info"]["fx_flat_filled"]


def test_fx_conversion_consistency():
    usd = load_returns(["SPY", "XIU.TO"], start="2010-01", end="2020-12", currency="USD")
    cad = load_returns(["SPY", "XIU.TO"], start="2010-01", end="2020-12", currency="CAD")
    fx = pd.read_parquet(DATA_DIR / "fx_monthly.parquet")
    fx = fx.set_index(pd.to_datetime(fx["date"]))["usdcad"]
    g = fx / fx.shift(1)
    lhs = (1 + cad["SPY"])
    rhs = (1 + usd["SPY"]) * g.reindex(usd.index)
    assert np.allclose(lhs, rhs, atol=1e-10)


def test_inflation_available_since_1926():
    for c in ("USD", "CAD"):
        s = load_inflation(c, "1926-01", "2024-12")
        assert s.index.min() == pd.Timestamp("1926-01-31") and s.notna().all()


def test_starter_period_uses_starter_source():
    from alphaforge.finance.backtest.data import _long
    d = _long()
    x = d[(d["asset_id"] == "AAPL") & (d["date"] >= "2021-12-31")]
    assert x["source"].str.contains("starter").all()
