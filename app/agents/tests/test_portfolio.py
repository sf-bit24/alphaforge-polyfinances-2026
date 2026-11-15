import pytest

from alphaforge import starter
from alphaforge.collect.fetchers import Quote
from alphaforge.profile import portfolio as pf


def raw(**kwargs):
    return pf.raw_from_dict({"raw": kwargs.pop("raw", "ligne"), **kwargs})


@pytest.fixture(scope="module")
def fx():
    return starter.last_fx()


def test_starter_last_values():
    assert starter.last_prices()["RY.TO"].date == "2026-11-12"
    assert starter.last_fx().date == "2026-11-12"
    assert starter.last_fx().usdcad == pytest.approx(1.4255)
    assert len(starter.universe()) == 31


@pytest.mark.parametrize(
    ("ticker", "name", "expected"),
    [
        ("RY", None, "RY.TO"),
        ("TSX:TD", None, "TD.TO"),
        ("shop.to", None, "SHOP.TO"),
        ("AAPL", None, "AAPL"),
        ("NASDAQ: NVDA", None, "NVDA"),
        ("BTC", None, "BTC-USD"),
        ("Bitcoin", None, "BTC-USD"),
        (None, "Royal Bank of Canada", "RY.TO"),
        (None, "iShares S&P/TSX 60 Index ETF", "XIU.TO"),
        ("ZZZZ", None, None),
    ],
)
def test_symbol_resolution_against_the_universe(ticker, name, expected):
    asset = starter.find_asset(ticker, name)
    assert (asset.ticker if asset else None) == expected


def test_resolution_prices_converts_and_cites_sources(fx):
    view = pf.build_view(
        [
            raw(raw="100 RY", ticker="RY", quantity=100, account_type="CELI"),
            raw(raw="10 AAPL", ticker="AAPL", quantity=10, account_type="rrsp"),
            raw(raw="Encaisse 1 000 $", name="Encaisse", asset_class="cash", market_value=1000, currency="CAD"),
        ],
        status="draft",
    )
    ry, aapl, cash = view["positions"]
    ry_close = starter.last_prices()["RY.TO"].close
    assert ry["ticker"] == "RY.TO" and ry["resolved"] and ry["account_type"] == "tfsa"
    assert ry["price"] == round(ry_close, 4) and ry["price_date"] == "2026-11-12"
    assert ry["price_source"] == "starter:prices_daily.csv"
    assert ry["value_cad"] == pytest.approx(round(100 * round(ry_close, 4), 2))
    aapl_close = round(starter.last_prices()["AAPL"].close, 4)
    assert aapl["currency"] == "USD"
    assert aapl["value_cad"] == pytest.approx(round(10 * aapl_close * fx.usdcad, 2))
    assert cash["asset_class"] == "cash" and cash["value_cad"] == 1000
    resources = {s["resource"] for s in view["sources"]}
    assert {"starter:prices_daily.csv", "starter:fx_usdcad_daily.csv", "starter:assets_universe.csv"} <= resources
    assert view["fx"] == {
        "pair": "USDCAD",
        "rate": fx.usdcad,
        "date": "2026-11-12",
        "source": "starter:fx_usdcad_daily.csv",
    }
    total = view["exposures"]["total_value_cad"]
    assert total == pytest.approx(ry["value_cad"] + aapl["value_cad"] + 1000)
    assert sum(view["exposures"]["by_asset_class"].values()) == pytest.approx(1.0, abs=1e-3)


def test_market_value_in_cad_for_a_usd_listing_is_not_converted(fx):
    view = pf.build_view([raw(raw="AAPL 5000 CAD", ticker="AAPL", market_value=5000, currency="CAD")], status="draft")
    position = view["positions"][0]
    assert position["value_cad"] == 5000 and position["currency"] == "USD"


def test_unknown_ticker_uses_the_quote_fetcher():
    calls = []

    def fetcher(symbol):
        calls.append(symbol)
        if symbol != "BNS.TO":
            raise RuntimeError("not found")
        return Quote(
            symbol="BNS.TO",
            currency="CAD",
            exchange="Toronto",
            instrument_type="EQUITY",
            name="Bank of Nova Scotia",
            last_close=70.5,
            last_date="2026-11-13",
            market_time="2026-11-13T21:00:00Z",
            url="https://query1.finance.yahoo.com/v8/finance/chart/BNS.TO",
        )

    view = pf.build_view(
        [raw(raw="BNS 10", ticker="BNS", quantity=10, currency="CAD")], status="draft", quote_fetcher=fetcher
    )
    position = view["positions"][0]
    assert calls[0] == "BNS.TO"
    assert position["resolved"] and position["value_cad"] == 705.0 and position["market"] == "TSX"
    assert position["price_source"].startswith("https://query1.finance.yahoo.com/")


def test_unknown_currency_tries_the_us_then_the_toronto_listing():
    calls = []

    def fetcher(symbol):
        calls.append(symbol)
        if symbol != "XEQT.TO":
            return None
        return Quote(
            symbol="XEQT.TO",
            currency="CAD",
            exchange="Toronto",
            instrument_type="ETF",
            name="iShares XEQT",
            last_close=40.0,
            last_date="2026-11-13",
            market_time="2026-11-13T21:00:00Z",
            url="https://query1.finance.yahoo.com/v8/finance/chart/XEQT.TO",
        )

    view = pf.build_view([raw(raw="40 XEQT", ticker="XEQT", quantity=40)], status="draft", quote_fetcher=fetcher)
    position = view["positions"][0]
    assert calls == ["XEQT", "XEQT.TO"]
    assert (
        position["ticker"] == "XEQT.TO" and position["value_cad"] == 1600.0 and position["asset_class"] == "etf_equity"
    )
    usd_calls = []
    pf.build_view(
        [raw(raw="ZZZZ 1", ticker="ZZZZ", quantity=1, currency="USD")],
        status="draft",
        quote_fetcher=lambda s: usd_calls.append(s),
    )
    assert usd_calls == ["ZZZZ"]


def test_unresolved_lines_keep_their_reason():
    view = pf.build_view(
        [raw(raw="fonds maison XYZ", name="fonds maison XYZ"), raw(raw="RY sans quantité", ticker="RY")],
        status="draft",
    )
    reasons = {u["raw"]: u["reason"] for u in view["unresolved"]}
    assert reasons["fonds maison XYZ"] == "titre introuvable et aucune valeur fournie"
    assert reasons["RY sans quantité"] == "quantité manquante"
    assert view["exposures"]["total_value_cad"] == 0
    assert view["exposures"]["flags"] == ["unvalued_positions"]


def test_flags_concentration_and_home_bias():
    view = pf.build_view(
        [
            raw(raw="RY", ticker="RY.TO", quantity=200),
            raw(raw="TD", ticker="TD.TO", quantity=10),
            raw(raw="ENB", ticker="ENB.TO", quantity=10),
        ],
        status="draft",
    )
    flags = view["exposures"]["flags"]
    assert "concentration_single_position" in flags
    assert "home_bias_canada" in flags
    assert "few_holdings" in flags
    top = view["exposures"]["top_positions"]
    assert top[0]["id"] == "p1" and top[0]["weight"] > 0.5


def test_diversified_funds_are_not_single_position_concentration():
    view = pf.build_view(
        [raw(raw="SPY", ticker="SPY", quantity=10), raw(raw="XIU", ticker="XIU", quantity=10)], status="confirmed"
    )
    flags = view["exposures"]["flags"]
    assert "concentration_single_position" not in flags and "few_holdings" not in flags
    assert view["status"] == "confirmed"


def test_crypto_and_cash_flags():
    view = pf.build_view(
        [raw(raw="BTC", ticker="BTC", quantity=1), raw(raw="cash", asset_class="cash", market_value=100000)],
        status="draft",
    )
    flags = view["exposures"]["flags"]
    assert "crypto_exposure_high" in flags and "cash_heavy" in flags


def test_corrected_positions_are_recomputed_by_code():
    raws = pf.positions_to_raws(
        [
            {"id": "p1", "raw": "RY", "ticker": "RY.TO", "quantity": 10, "price": 1.0, "value_cad": 999999},
            {"id": "p2"},
            "garbage",
        ]
    )
    assert len(raws) == 1
    view = pf.build_view(raws, status="confirmed")
    assert view["positions"][0]["value_cad"] != 999999
