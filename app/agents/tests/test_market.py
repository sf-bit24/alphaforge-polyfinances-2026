"""Couche de données de marché (alphaforge.market) : repli sur le jeu de départ, parquets quotidiens, univers."""

import json
import re
from pathlib import Path

import pytest

from alphaforge import market, starter

SRC = Path(__file__).resolve().parents[1] / "src" / "alphaforge"
DATES = ("2022-06-30", "2024-12-25", "2026-11-12")


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    monkeypatch.setenv("ALPHAFORGE_BT_DATA", str(tmp_path / "empty"))
    monkeypatch.delenv("ALPHAFORGE_MARKET_SOURCE", raising=False)
    monkeypatch.delenv("ALPHAFORGE_MARKET_INCLUDE_PROPOSED", raising=False)
    market.reset_cache()
    yield
    market.reset_cache()


# ----------------------------------------------------------------------------- repli : identique au starter
def test_fallback_is_the_starter_dataset():
    assert market.source() == "starter"
    assert market.universe() == starter.universe()
    assert market.last_prices() == starter.last_prices()
    assert market.last_fx() == starter.last_fx()
    assert market.fx_resource() == "starter:fx_usdcad_daily.csv"
    assert market.source_entry("prices_daily.csv", "t", observed_at="2026-11-12") == starter.source_entry(
        "prices_daily.csv", "t", observed_at="2026-11-12"
    )
    assert market.data_version()["source"] == "starter"


def test_fallback_series_match_the_starter_for_every_ticker():
    for t in starter.universe():
        for d in DATES:
            assert market.daily(t, d) == starter.daily(t, d)
            assert market.close_on_or_before(t, d) == starter.close_on_or_before(t, d)
            assert market.dividends(t, "2021-01-01", d) == starter.dividends(t, "2021-01-01", d)
            assert market.dividend_yield_ttm(t, d) == starter.dividend_yield_ttm(t, d)
            assert market.median_dollar_volume_cad(t, d) == starter.median_dollar_volume_cad(t, d)
    for d in DATES:
        assert market.usdcad_on_or_before(d) == starter.usdcad_on_or_before(d)
    assert market.find_asset("TSX:RY") == starter.find_asset("TSX:RY")


def test_forced_starter_source(monkeypatch, tmp_path):
    _write_parquets(tmp_path)
    monkeypatch.setenv("ALPHAFORGE_BT_DATA", str(tmp_path))
    monkeypatch.setenv("ALPHAFORGE_MARKET_SOURCE", "starter")
    assert market.source() == "starter"


# ----------------------------------------------------------------------------- univers
def test_proposed_assets_stay_out_by_default(monkeypatch):
    assert "XRE.TO" not in market.universe() and len(market.universe()) == 31
    monkeypatch.setenv("ALPHAFORGE_MARKET_INCLUDE_PROPOSED", "1")
    assert market.universe()["XRE.TO"].sector == "Real Estate"
    assert market.find_asset("XRE") is not None


# ----------------------------------------------------------------------------- parquets quotidiens
def _write_parquets(where: Path) -> None:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    where.mkdir(parents=True, exist_ok=True)
    days = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"])
    pd.DataFrame(
        {
            "date": list(days) * 2,
            "ticker": ["RY.TO"] * 4 + ["AAPL"] * 4,
            "close": [100.0, 101.0, 102.0, 103.0, 200.0, 201.0, 202.0, 203.0],
            "adj_close": [99.0, 100.0, 101.0, 102.0, 199.0, 200.0, 201.0, 202.0],
            "volume": [1e6] * 8,
            "currency": ["CAD"] * 4 + ["USD"] * 4,
        }
    ).to_parquet(where / "daily_prices.parquet", index=False)
    pd.DataFrame({"date": days, "usdcad": [1.40, 1.41, 1.42, 1.43], "cadusd": [0.714, 0.709, 0.704, 0.699]}).to_parquet(
        where / "fx_daily.parquet", index=False
    )
    pd.DataFrame(
        {
            "ex_date": pd.to_datetime(["2026-01-06", "2026-01-08"]),
            "ticker": ["RY.TO", "AAPL"],
            "action": ["dividend", "split"],
            "value": [1.5, 4.0],
            "unit": ["CAD per share", "ratio"],
        }
    ).to_parquet(where / "corporate_actions.parquet", index=False)
    (where / "data_version.json").write_text(
        json.dumps({"daily": {"data_sha256": "abc123", "built_utc": "2026-11-15T20:00:00+00:00", "files": {}}})
    )


def test_parquets_are_read_point_in_time(monkeypatch, tmp_path):
    _write_parquets(tmp_path)
    monkeypatch.setenv("ALPHAFORGE_BT_DATA", str(tmp_path))
    assert market.source() == "market"
    rows = market.daily("RY.TO", "2026-01-06")
    assert [r.date for r in rows] == ["2026-01-05", "2026-01-06"]
    assert all(r.date <= "2026-01-06" for t in ("RY.TO", "AAPL") for r in market.daily(t, "2026-01-06"))
    assert market.close_on_or_before("AAPL", "2026-01-07").close == 202.0
    assert market.usdcad_on_or_before("2026-01-06") == 1.41
    assert market.dividends("RY.TO", "2026-01-01", "2026-01-31") == [("2026-01-06", 1.5)]
    assert market.dividends("AAPL", "2026-01-01", "2026-01-31") == []  # un fractionnement n'est pas un dividende
    assert market.dividend_yield_ttm("RY.TO", "2026-01-05") == 0.0
    last = market.last_prices()
    assert last["AAPL"].date == "2026-01-08" and last["AAPL"].currency == "USD" and "TSLA" not in last
    assert market.last_fx().date == "2026-01-08" and market.last_fx().usdcad == 1.43
    entry = market.source_entry("prices_daily.csv", "ignoré", observed_at="2026-01-08")
    assert entry["resource"] == "market:daily_prices.parquet" and entry["retrieved_at"].startswith("2026-11-15")
    assert market.fx_resource() == "market:fx_daily.parquet"
    assert market.data_version() == {
        "source": "market",
        "version": "abc123",
        "built_utc": "2026-11-15T20:00:00+00:00",
        "files": {},
    }


def test_daily_tables_from_raw_files(tmp_path):
    pytest.importorskip("pandas")
    from alphaforge.finance.backtest import daily_data

    raw = tmp_path / "raw"
    (raw / "yfinance_daily").mkdir(parents=True)
    (raw / "bankofcanada").mkdir()
    (raw / "yfinance_daily" / "RY.TO.csv").write_text(
        "date,close,adj_close,volume,dividends,stock_splits\n"
        "2026-01-05,100,99,1000,0,0\n2026-01-06,101,100,1200,1.5,0\n2026-01-07,,,0,0,0\n2026-01-08,50,49.5,900,0,2\n"
    )
    (raw / "bankofcanada" / "FXUSDCAD.csv").write_text(
        '"TERMS AND CONDITIONS"\n"x"\n\n"OBSERVATIONS"\n"date","FXUSDCAD"\n'
        '"2026-01-05","1.4000"\n"2026-01-06","1.4100"\n'
    )
    assets = [{"ticker": "RY.TO", "currency": "CAD"}, {"ticker": "XRE.TO", "currency": "CAD"}]
    px, fx, ca = daily_data.daily_tables(raw, assets)
    assert list(px["ticker"].unique()) == ["RY.TO"] and len(px) == 3  # la ligne sans prix est retirée
    assert list(fx["usdcad"]) == [1.40, 1.41] and fx["cadusd"].iloc[0] == pytest.approx(0.714286)
    assert ca[["action", "value", "unit"]].values.tolist() == [
        ["dividend", 1.5, "CAD per share"],
        ["split", 2.0, "ratio"],
    ]
    block = daily_data.build_daily(tmp_path / "out", raw, assets)
    assert set(block["files"]) == {"daily_prices.parquet", "fx_daily.parquet", "corporate_actions.parquet"}
    assert json.loads((tmp_path / "out" / "data_version.json").read_text())["daily"]["last_date"] == "2026-01-08"


def test_universe_yaml_keeps_the_starter_columns():
    from alphaforge.finance.backtest import daily_data

    rows = daily_data.universe_rows(include_proposed=False)
    assert [r["ticker"] for r in rows] == list(starter.universe())


# ----------------------------------------------------------------------------- aucune lecture directe du starter
def test_no_module_reads_the_starter_directly():
    pattern = re.compile(
        r"^\s*(from\s+(alphaforge|\.\.?)\s+import\s+[^\n]*\bstarter\b|import\s+alphaforge\.starter)", re.M
    )
    offenders = [
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if p.name not in ("market.py", "starter.py") and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
