"""Rebuild the monthly long-history dataset from scratch.

Usage (from app/agents/):
    uv run --group finance --group backtest-data python -I -m alphaforge.finance.backtest.build_data
        [--refresh]   # re-download everything
        [--offline]   # build from <data dir>/raw only, no network
        [--daily-only]  # only the daily market parquets (daily_data.py)

Security: every downloaded file is treated as untrusted DATA. Each source lives in
its own folder <data dir>/raw/<source>/ with a manifest.json (url, retrieval time,
sha256). Nothing downloaded is ever executed; we only parse CSV/XLS/text.

Data dir = alphaforge/data/long/ (override: ALPHAFORGE_BT_DATA); the official starter is read in place
from alphaforge/data/starter/ (override: ALPHAFORGE_STARTER_DIR). Parquets and raw/ are not versioned.

Outputs (<data dir>/):
    monthly_returns.parquet  long format: date, asset_id, return_usd, return_cad, source, flag
    assets.csv               asset catalogue (class, currency, start/end, tags, exposures, mapping)
    fx_monthly.parquet       USDCAD month-end
    inflation_monthly.parquet  US & Canada CPI monthly inflation
    lookthrough_us_mkt.parquet  share of each KF industry in US market cap (time-varying)
    daily_prices.parquet, fx_daily.parquet, corporate_actions.parquet
                             daily market data for alphaforge.market (daily_data.py), universe of
                             data/market/universe.yaml; "daily" block of data_version.json
    qa_overlap.csv           yfinance vs starter dataset concordance on the overlap
    coverage.csv             asset_id, start, end, n_months
    data_version.json        content hash + build metadata
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import daily_data
from .bonds import bond_returns_from_yields
from .paths import data_dir, starter_dir

OUT = data_dir()
RAW = OUT / "raw"
# The `source` labels written in monthly_returns.parquet still say "engine/bonds.py" (path before the move to
# alphaforge.finance.backtest): they are part of data_sha256, so they are kept as is.
# Official starter dataset, committed once in the app (byte-identical to the organisers' copy; never duplicated).
# Override with ALPHAFORGE_STARTER_DIR to read another copy.
STARTER = starter_dir()
FLOOR = pd.Timestamp("1926-01-31")  # we do not publish anything before 1926
LAST_COMPLETE = pd.Timestamp.today().normalize().replace(day=1) - pd.Timedelta(days=1)  # last full month
STARTER_FIRST_RETURN = pd.Timestamp("2021-12-31")  # first month whose base (2021-11-30) is in the starter
STARTER_BASE = pd.Timestamp("2021-11-30")  # first month end of the starter (base of its first monthly return)
FIRST_GS_MONTH = pd.Timestamp("1953-04-30")  # FRED's monthly GS* yields start here; fallbacks before
# FRED's bot filter rejects unknown/browser-like agents from scripts; a plain curl UA is accepted.
USER_AGENT = "curl/8.5.0"

KF = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
FRED_SERIES = [
    "GS1",
    "GS2",
    "GS3",
    "GS5",
    "GS10",
    "GS20",
    "GS30",
    "AAA",
    "BAA",
    "DGS1",
    "DGS2",
    "DGS3",
    "DGS5",
    "DGS10",
    "DGS20",
    "DGS30",
    "DAAA",
    "DBAA",
    "CPIAUCNS",
    "DEXCAUS",
    "CANCPIALLMINMEI",
    "IRLTLT01CAM156N",
    "IR3TIB01CAM156N",
]
DOWNLOADS = {
    "kenfrench": {
        "F-F_Research_Data_Factors_CSV.zip": KF + "F-F_Research_Data_Factors_CSV.zip",
        "12_Industry_Portfolios_CSV.zip": KF + "12_Industry_Portfolios_CSV.zip",
        "F-F_International_Countries.zip": KF + "F-F_International_Countries.zip",
    },
    "fred": {f"{s}.csv": FRED + s for s in FRED_SERIES},
    "shiller": {
        "ie_data.xls": "https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/ie_data.xls",
    },
    "datahub_gold": {
        "monthly.csv": "https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv",
    },
    "bankofcanada": {
        "V41690973.csv": "https://www.bankofcanada.ca/valet/observations/V41690973/csv?start_date=1990-01-01",
        "FXUSDCAD.csv": daily_data.FX_URL,
    },
}


# --------------------------------------------------------------------------- download
def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _manifest(source_dir: Path) -> dict:
    path = source_dir / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _write_manifest(source_dir: Path, manifest: dict) -> None:
    (source_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))


def _manifest_entry(url: str, content: bytes) -> dict:
    return {
        "url": url,
        "retrieved_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "sha256": _sha256(content),
        "bytes": len(content),
    }


def fetch(url: str, timeout: int = 120) -> bytes:
    # Only the fixed https URLs of DOWNLOADS reach this point (no file:// nor user-supplied scheme).
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-https URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 (https checked above)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https checked above)
        return response.read()


def download_all(*, refresh: bool) -> None:
    for source, files in DOWNLOADS.items():
        folder = RAW / source
        folder.mkdir(parents=True, exist_ok=True)
        manifest = _manifest(folder)
        for file_name, url in files.items():
            target = folder / file_name
            if target.exists() and not refresh:
                continue
            print(f"[download] {source}/{file_name}")
            content = fetch(url)
            target.write_bytes(content)
            manifest[file_name] = _manifest_entry(url, content)
            _write_manifest(folder, manifest)
    download_yfinance(refresh=refresh)
    daily_data.download_yfinance_daily(RAW, [str(a["ticker"]) for a in daily_data.universe_rows()], refresh=refresh)


def universe() -> pd.DataFrame:
    return pd.read_csv(STARTER / "assets_universe.csv")


def download_yfinance(*, refresh: bool) -> None:
    folder = RAW / "yfinance"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(folder)
    tickers = list(universe()["ticker"])
    todo = [ticker for ticker in tickers if refresh or not (folder / f"{ticker}.csv").exists()]
    if not todo:
        return
    import yfinance  # imported lazily: only needed when downloading

    for ticker in todo:
        print(f"[download] yfinance/{ticker}")
        prices = yfinance.download(
            ticker,
            period="max",
            interval="1d",
            auto_adjust=False,
            actions=False,
            progress=False,
            threads=False,
            multi_level_index=False,
        )
        if prices is None or prices.empty:
            raise RuntimeError(f"yfinance returned no data for {ticker}")
        prices = prices[["Close", "Adj Close"]].rename(columns={"Close": "close", "Adj Close": "adj_close"})
        prices.index.name = "date"
        content = prices.to_csv().encode()
        (folder / f"{ticker}.csv").write_bytes(content)
        call = f"yfinance.download('{ticker}', period='max', interval='1d', auto_adjust=False)"
        manifest[f"{ticker}.csv"] = _manifest_entry(call, content)
    _write_manifest(folder, manifest)


# --------------------------------------------------------------------------- parsers
def month_end(dates) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(dates)).to_period("M").to_timestamp(how="end").normalize()


def _yyyymm_to_month_end(values: pd.Series) -> pd.DatetimeIndex:
    return month_end(pd.to_datetime(values.astype(str).str.strip(), format="%Y%m"))


def _kf_block(text: str, header_startswith: str | None) -> pd.DataFrame:
    """Parse a monthly block (YYYYMM rows) from a Ken French CSV text."""
    lines = text.splitlines()
    start = 0
    if header_startswith is not None:
        start = next(i for i, line in enumerate(lines) if line.strip().startswith(header_startswith))
    # header line = first line after start that begins with ','
    header = next(i for i in range(start, len(lines)) if lines[i].startswith(","))
    columns = [column.strip() for column in lines[header].split(",")[1:]]
    rows = []
    for line in lines[header + 1 :]:
        cells = [cell.strip() for cell in line.split(",")]
        if len(cells[0]) != 6 or not cells[0].isdigit():
            break
        rows.append(cells)
    block = pd.DataFrame(rows, columns=["yyyymm"] + columns)
    block.index = _yyyymm_to_month_end(block.pop("yyyymm"))
    block = block.apply(pd.to_numeric)
    return block.mask(block <= -99.99)


def read_zip_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        name = [member for member in archive.namelist() if member.lower().endswith((".csv", ".txt"))][0]
        return archive.read(name).decode("latin-1")


def load_kf_factors() -> pd.DataFrame:
    text = read_zip_text(RAW / "kenfrench" / "F-F_Research_Data_Factors_CSV.zip")
    return _kf_block(text, None) / 100.0  # first block is monthly


def load_kf_industries() -> tuple[pd.DataFrame, pd.DataFrame]:
    text = read_zip_text(RAW / "kenfrench" / "12_Industry_Portfolios_CSV.zip")
    value_weighted = _kf_block(text, "Average Value Weighted Returns -- Monthly") / 100.0
    firm_count = _kf_block(text, "Number of Firms in Portfolios")
    firm_size = _kf_block(text, "Average Firm Size")
    market_cap = firm_count * firm_size
    share = market_cap.div(market_cap.sum(axis=1), axis=0)
    return value_weighted, share


def _kf_country_block(lines: list[str], title: str) -> pd.Series:
    """Monthly market returns (decimal) of the "Not Reqd" block titled `title` in a KF country file."""
    start = next(i for i, line in enumerate(lines) if title in line and "Not Reqd" in line)
    returns = {}
    for line in lines[start + 3 :]:
        cells = line.split()
        if not cells or len(cells[0]) != 6 or not cells[0].isdigit():
            break
        returns[cells[0]] = float(cells[1])
    series = pd.Series(returns)
    series.index = _yyyymm_to_month_end(pd.Series(series.index))
    return series.mask(series <= -99.99) / 100.0


def load_kf_canada() -> pd.DataFrame:
    with zipfile.ZipFile(RAW / "kenfrench" / "F-F_International_Countries.zip") as archive:
        name = [member for member in archive.namelist() if member.lower().startswith("canada")][0]
        text = archive.read(name).decode("latin-1")
    lines = text.splitlines()
    return pd.DataFrame(
        {
            "usd": _kf_country_block(lines, "Value-Weight Dollar Returns"),
            "local": _kf_country_block(lines, "Value-Weight Local  Returns"),
        }
    )


def load_fred(series_id: str) -> pd.Series:
    frame = pd.read_csv(RAW / "fred" / f"{series_id}.csv")
    frame.columns = ["date", "value"]
    values = pd.to_numeric(frame["value"], errors="coerce").values
    return pd.Series(values, index=pd.to_datetime(frame["date"]), name=series_id)


def fred_monthly(series_id: str) -> pd.Series:
    monthly = load_fred(series_id)
    monthly.index = month_end(monthly.index)
    return monthly


def load_shiller_gs10() -> pd.Series:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pandas deprecation notice for the xlrd engine (.xls format)
        sheet = pd.read_excel(RAW / "shiller" / "ie_data.xls", sheet_name="Data", header=None, engine="xlrd")
    sheet = sheet.iloc[8:, [0, 6]].dropna()
    sheet = sheet[pd.to_numeric(sheet[0], errors="coerce").notna()]
    decimal_date = sheet[0].astype(float)  # YYYY.MM
    year = np.floor(decimal_date).astype(int)
    month = np.round((decimal_date - year) * 100).astype(int)
    months = month_end(pd.to_datetime({"year": year, "month": month, "day": 1}))
    return pd.Series(pd.to_numeric(sheet[6]).values, index=months, name="SHILLER_GS10")


def load_gold() -> pd.Series:
    frame = pd.read_csv(RAW / "datahub_gold" / "monthly.csv")
    months = month_end(pd.to_datetime(frame["Date"], format="%Y-%m"))
    return pd.Series(frame["Price"].astype(float).values, index=months)


def load_boc(series_id: str) -> pd.Series:
    text = (RAW / "bankofcanada" / f"{series_id}.csv").read_text()
    body = text.split('"OBSERVATIONS"', 1)[1]
    frame = pd.read_csv(io.StringIO(body.strip()))
    values = pd.to_numeric(frame[series_id], errors="coerce").values
    return pd.Series(values, index=month_end(pd.to_datetime(frame["date"])))


def daily_to_month_end(daily: pd.Series) -> pd.Series:
    """Last available observation of each calendar month (no forward fill across months)."""
    observed = daily.dropna()
    last_of_month = observed.groupby(observed.index.to_period("M")).last()
    last_of_month.index = last_of_month.index.to_timestamp(how="end").normalize()
    return last_of_month


CNQ_FIX: dict = {}  # filled by fix_cnq_special_dividend, reported in data_version.json (qa)


def fix_cnq_special_dividend(
    returns: pd.Series, flags: pd.Series, starter_prices: pd.DataFrame
) -> tuple[pd.Series, pd.Series]:
    """CNQ.TO 2022-08-22: Yahoo recorded the special dividend both as a 1.021 'split' and as a
    0.75 dividend, so adj_close double-counts ~2 % on that day. We replace that day's adj_close
    return by the true total return (close_t + dividend) / (close_{t-1} * split) - 1, using the
    starter's own close, corporate_actions.csv split and dividend values."""
    actions = pd.read_csv(STARTER / "corporate_actions.csv", parse_dates=["ex_date"])
    event = pd.Timestamp("2022-08-22")
    on_event = (actions.ticker == "CNQ.TO") & (actions.ex_date == event)
    split = actions[on_event & (actions.action == "split")]["value"]
    dividend = actions[on_event & (actions.action == "dividend")]["value"]
    if split.empty or dividend.empty:
        return returns, flags
    prices = starter_prices[starter_prices["ticker"] == "CNQ.TO"].set_index("date").sort_index()
    position = prices.index.get_loc(event)
    previous, current = prices.iloc[position - 1], prices.iloc[position]
    adjusted_return = current["adj_close"] / previous["adj_close"] - 1
    true_return = (current["close"] + float(dividend.iloc[0])) / (previous["close"] * float(split.iloc[0])) - 1
    month = month_end([event])[0]
    if month in returns.index:
        returns = returns.copy()
        returns[month] = (1 + returns[month]) * (1 + true_return) / (1 + adjusted_return) - 1
        flags = flags.copy()
        flags[month] = "corrected_double_counted_special_dividend"
    CNQ_FIX.update(
        {
            "day_adj_close_return": round(float(adjusted_return), 6),
            "day_true_total_return": round(float(true_return), 6),
        }
    )
    return returns, flags


# --------------------------------------------------------------------------- build
class _AssetCollector:
    """Long-format return records and asset catalogue, in the order the assets are added (that order is the row
    order of assets.csv)."""

    def __init__(self) -> None:
        self.records: list[pd.DataFrame] = []
        self.catalogue: dict[str, dict] = {}

    def add(
        self,
        asset_id: str,
        return_usd: pd.Series | None,
        return_cad: pd.Series | None,
        source: str,
        flag: str | pd.Series,
        **meta: object,
    ) -> None:
        index = (return_usd if return_usd is not None else return_cad).index
        records = pd.DataFrame(
            {
                "date": index,
                "return_usd": return_usd.reindex(index).values if return_usd is not None else np.nan,
                "return_cad": return_cad.reindex(index).values if return_cad is not None else np.nan,
            }
        )
        records["asset_id"] = asset_id
        records["source"] = source
        records["flag"] = flag.reindex(index).fillna("").values if isinstance(flag, pd.Series) else flag
        records = records[(records["date"] >= FLOOR) & (records["date"] <= LAST_COMPLETE)]
        records = records.dropna(subset=["return_usd", "return_cad"], how="all")
        self.add_records(asset_id, records, meta)

    def add_records(self, asset_id: str, records: pd.DataFrame, meta: dict) -> None:
        self.records.append(records)
        self.catalogue[asset_id] = meta


class _FxConverter:
    """Converts monthly returns between USD and CAD (unhedged investor) with the month-end USDCAD."""

    def __init__(self, fx_return: pd.Series) -> None:
        self.fx_return = fx_return  # CAD return of holding 1 USD

    def usd_to_cad(self, return_usd: pd.Series) -> pd.Series:
        return (1 + return_usd) * (1 + self.fx_return.reindex(return_usd.index)) - 1

    def cad_to_usd(self, return_cad: pd.Series) -> pd.Series:
        return (1 + return_cad) / (1 + self.fx_return.reindex(return_cad.index)) - 1

    def in_both_currencies(self, returns: pd.Series, currency: str) -> tuple[pd.Series, pd.Series]:
        """(USD, CAD) returns of an asset quoted in `currency`."""
        if currency == "CAD":
            return self.cad_to_usd(returns), returns
        return returns, self.usd_to_cad(returns)


def _write_fx_monthly() -> tuple[_FxConverter, pd.DataFrame]:
    """USDCAD month end (CAD per USD): FRED DEXCAUS, then the starter's FX from its first month end.

    Writes fx_monthly.parquet; returns the converter and the FRED/starter overlap (QA)."""
    fred = daily_to_month_end(load_fred("DEXCAUS").dropna())
    source = pd.Series("FRED DEXCAUS (last business day of month)", index=fred.index)
    starter_daily = pd.read_csv(STARTER / "fx_usdcad_daily.csv", parse_dates=["date"]).set_index("date")["usdcad"]
    starter = daily_to_month_end(starter_daily)
    starter = starter[starter.index >= STARTER_BASE]
    starter = starter[starter.index <= LAST_COMPLETE]
    overlap = pd.concat([fred, starter], axis=1, keys=["fred", "starter"]).dropna()
    usdcad = pd.concat([fred[fred.index < STARTER_BASE], starter])
    source = source.reindex(usdcad.index).fillna(
        "Bank of Canada via starter fx_usdcad_daily.csv (last available day of month)"
    )
    usdcad = usdcad[usdcad.index <= LAST_COMPLETE]
    fx_monthly = pd.DataFrame(
        {"date": usdcad.index, "usdcad": usdcad.values, "source": source.reindex(usdcad.index).values}
    )
    fx_monthly.to_parquet(OUT / "fx_monthly.parquet", index=False)
    return _FxConverter(usdcad / usdcad.shift(1) - 1.0), overlap


def _us_inflation() -> tuple[pd.Series, pd.Series]:
    """US CPI-U monthly inflation and its quality flag."""
    cpi = fred_monthly("CPIAUCNS")
    # BLS did not publish some months (e.g. Oct 2025, US government shutdown): log-linear
    # interpolation of the index for interior gaps, flagged in the output
    gap = cpi.isna() & (cpi.index > cpi.first_valid_index()) & (cpi.index < cpi.last_valid_index())
    cpi = np.exp(np.log(cpi).interpolate(limit_area="inside"))
    inflation = cpi / cpi.shift(1) - 1
    flags = pd.Series("", index=cpi.index, dtype=object)
    for month in cpi.index[gap]:
        flags[month] = "cpi_interpolated"
        following = cpi.index[cpi.index.get_loc(month) + 1]
        flags[following] = "cpi_interpolated"  # the following month's inflation also depends on the gap
    return inflation, flags


def _canada_inflation() -> tuple[pd.Series, pd.DataFrame]:
    """Canada CPI monthly inflation (OECD, then StatCan) and the OECD/StatCan overlap (QA)."""
    cpi_oecd = fred_monthly("CANCPIALLMINMEI").dropna()
    cpi_statcan = load_boc("V41690973").dropna()
    inflation_oecd = cpi_oecd / cpi_oecd.shift(1) - 1
    inflation_statcan = cpi_statcan / cpi_statcan.shift(1) - 1
    overlap = pd.concat([inflation_oecd, inflation_statcan], axis=1, keys=["oecd", "statcan"]).dropna()
    splice = inflation_statcan.index.min()  # StatCan from its 2nd month onward
    inflation = pd.concat(
        [inflation_oecd[inflation_oecd.index < splice + pd.offsets.MonthEnd(1)], inflation_statcan.dropna()]
    )
    inflation = inflation[~inflation.index.duplicated(keep="last")].sort_index()
    return inflation, overlap


def _write_inflation_monthly() -> pd.DataFrame:
    """Writes inflation_monthly.parquet; returns the OECD/StatCan overlap (QA)."""
    inflation_us, flags_us = _us_inflation()
    inflation_ca, overlap = _canada_inflation()
    inflation = pd.DataFrame({"infl_us": inflation_us, "infl_ca": inflation_ca, "flag_us": flags_us})
    inflation["flag_us"] = inflation["flag_us"].fillna("")
    inflation = inflation[(inflation.index >= FLOOR) & (inflation.index <= LAST_COMPLETE)]
    inflation.index.name = "date"
    inflation.reset_index().to_parquet(OUT / "inflation_monthly.parquet", index=False)
    return overlap


def _add_us_market(collector: _AssetCollector, fx: _FxConverter) -> pd.Series:
    """US_MKT and UST_TBILL from the Ken French factors; returns RF (monthly, decimal)."""
    factors = load_kf_factors()
    risk_free = factors["RF"]
    market = factors["Mkt-RF"] + factors["RF"]
    collector.add(
        "US_MKT",
        market,
        fx.usd_to_cad(market),
        "Ken French Data Library: Mkt-RF + RF (CRSP value-weighted)",
        "",
        name="US total stock market (CRSP VW, total return)",
        cls="equity_us",
        ccy="USD",
        tags="equity;broad_market",
        universe="SPY;ESGV;QQQ(partial)",
        notes=(
            "Value-weighted NYSE/AMEX/NASDAQ incl. dividends; before 1962 NYSE-dominated. Look-through "
            "sector shares: lookthrough_us_mkt.parquet."
        ),
    )
    collector.add(
        "UST_TBILL",
        risk_free,
        fx.usd_to_cad(risk_free),
        "Ken French Data Library: RF (1-month T-bill, Ibbotson/CRSP)",
        "",
        name="US 1-month Treasury bill",
        cls="cash",
        ccy="USD",
        tags="cash;defensive;government",
        universe="(cash);ZST.TO(approx, CAD)",
        notes="Risk-free proxy. Before 1934 from Ibbotson/CRSP sources (per Ken French).",
    )
    return risk_free


INDUSTRY_TAGS = {
    "NoDur": "consumer_staples;defensive_sector",
    "Durbl": "consumer_discretionary;cyclical",
    "Manuf": "industrials;cyclical",
    "Enrgy": "energy;fossil_fuel;cyclical",
    "Chems": "materials;chemicals",
    "BusEq": "tech",
    "Telcm": "communication",
    "Utils": "utilities;defensive_sector",
    "Shops": "consumer_discretionary;retail",
    "Hlth": "healthcare;defensive_sector",
    "Money": "financials",
    "Other": "other;industrials",
}
INDUSTRY_NAMES = {
    "NoDur": "Consumer non-durables",
    "Durbl": "Consumer durables",
    "Manuf": "Manufacturing",
    "Enrgy": "Oil, gas & coal",
    "Chems": "Chemicals",
    "BusEq": "Business equipment (computers, software, electronics)",
    "Telcm": "Telecom",
    "Utils": "Utilities",
    "Shops": "Wholesale/retail & services",
    "Hlth": "Healthcare & drugs",
    "Money": "Finance",
    "Other": "Other (transport, construction, mining, hotels...)",
}
INDUSTRY_TICKERS = {
    "NoDur": "PG;ATD.TO(retail, approx)",
    "Durbl": "TSLA",
    "Manuf": "",
    "Enrgy": "XOM;CNQ.TO;ENB.TO(pipeline: SIC 4922 = KF Utils)",
    "Chems": "",
    "BusEq": "AAPL;MSFT;NVDA;GOOGL;CSU.TO;SHOP.TO;QQQ(partial)",
    "Telcm": "",
    "Utils": "FTS.TO;ENB.TO(partial)",
    "Shops": "AMZN;ATD.TO",
    "Hlth": "JNJ",
    "Money": "JPM;RY.TO;TD.TO;MFC.TO",
    "Other": "CNR.TO",
}


def _industry_id(industry: str) -> str:
    return f"US_IND_{industry.upper()}"


def _add_us_industries(collector: _AssetCollector, fx: _FxConverter) -> pd.DataFrame:
    """The 12 KF value-weighted industries. Writes their share of US market cap (lookthrough_us_mkt.parquet) and
    returns it."""
    returns, cap_share = load_kf_industries()
    for industry in returns.columns:
        collector.add(
            _industry_id(industry),
            returns[industry],
            fx.usd_to_cad(returns[industry]),
            f"Ken French 12 Industry Portfolios, value-weighted ({industry})",
            "",
            name=f"US industry: {INDUSTRY_NAMES[industry]}",
            cls="sector_us",
            ccy="USD",
            tags="equity;sector;" + INDUSTRY_TAGS[industry],
            universe=INDUSTRY_TICKERS[industry],
            notes="SIC-based KF 12-industry definition (not GICS). Mapping to tickers is approximate.",
        )
    lookthrough = cap_share.copy()
    lookthrough.columns = [_industry_id(industry) for industry in lookthrough.columns]
    lookthrough = lookthrough[(lookthrough.index >= FLOOR) & (lookthrough.index <= LAST_COMPLETE)]
    lookthrough.index.name = "date"
    lookthrough.reset_index().to_parquet(OUT / "lookthrough_us_mkt.parquet", index=False)
    return lookthrough


def _before_gs_yields(series: pd.Series) -> pd.Series:
    """Months before FRED's monthly GS* yields (they start in 1953-04)."""
    return series[series.index < FIRST_GS_MONTH]


def _bill_long_interpolation(maturity_years: float, bill_yield_pct: pd.Series, long_yield_pct: pd.Series) -> pd.Series:
    """Linear-in-maturity interpolation between bill (0.083y) and long yield (10y), pre-1953 only."""
    weight = (maturity_years - 1 / 12) / (10 - 1 / 12)
    return (bill_yield_pct + weight * (long_yield_pct - bill_yield_pct)).dropna()


def _splice_yields(sources: list[tuple[pd.Series, str]]) -> tuple[pd.Series, pd.Series]:
    """Yields and the flag of their source: each source, in order of preference, only fills the months still
    missing."""
    yields = pd.Series(dtype=float)
    flags = pd.Series(dtype=object)
    for source, flag in sources:
        available = source.dropna()
        new = available.index.difference(yields.index)
        yields = pd.concat([yields, available.reindex(new)])
        flags = pd.concat([flags, pd.Series(flag, index=new)])
    return yields.sort_index(), flags.sort_index()


def _flag_splices(source_flags: pd.Series) -> pd.Series:
    """A month whose return mixes two yield sources is flagged as a splice."""
    flags = source_flags.copy()
    changed = source_flags != source_flags.shift(1)
    flags[changed] = (source_flags[changed] + ";splice").str.strip(";")
    flags.iloc[0] = source_flags.iloc[0]
    return flags


TREASURIES = {  # asset id -> constant maturity (years), name, universe tickers
    "UST_2Y": (2, "US Treasury ~2y constant maturity (synthetic)", "AGG(partial);ZST.TO(very approx)"),
    "UST_5Y": (5, "US Treasury ~5y constant maturity (synthetic)", "AGG(approx: aggregate index incl. MBS/corporates)"),
    "UST_10Y": (10, "US Treasury ~10y constant maturity (synthetic)", "AGG(partial);TLT(partial)"),
    "UST_20Y": (20, "US Treasury ~20y constant maturity (synthetic)", "TLT"),
}
MONTHLY_AVERAGE = "monthly_avg_yield"  # flag of a yield averaged over the month (smooths returns)


def _treasury_yield_sources(risk_free: pd.Series) -> dict[str, list[tuple[pd.Series, str]]]:
    """Yield sources (percent) of each synthetic Treasury, in order of preference: month-end yields from daily FRED
    series (preferred: no averaging), then monthly averages, then fallbacks."""
    shiller = load_shiller_gs10()  # Shiller long rate (GS10 after 1953, long gov yields before)
    monthly = {series_id: fred_monthly(series_id) for series_id in ["GS1", "GS2", "GS3", "GS5", "GS10", "GS20", "GS30"]}
    bill_yield_pct = ((1 + risk_free) ** 12 - 1) * 100  # annualised T-bill yield, %
    daily = ["DGS1", "DGS2", "DGS3", "DGS5", "DGS10", "DGS20", "DGS30"]
    month_ends = {series_id: daily_to_month_end(load_fred(series_id).dropna()) for series_id in daily}
    month_ends = {series_id: yields[yields.index <= LAST_COMPLETE] for series_id, yields in month_ends.items()}
    month_end_1_3 = ((month_ends["DGS1"] + month_ends["DGS3"]) / 2).dropna()
    monthly_1_3 = ((monthly["GS1"] + monthly["GS3"]) / 2).dropna()
    interpolated = {
        maturity: _before_gs_yields(_bill_long_interpolation(maturity, bill_yield_pct, shiller)) for maturity in (2, 5)
    }
    long_rate = _before_gs_yields(shiller)
    average = MONTHLY_AVERAGE
    return {
        "UST_2Y": [
            (month_ends["DGS2"], ""),
            (month_end_1_3, "fallback_avg_DGS1_DGS3"),
            (monthly_1_3, average + ";fallback_avg_GS1_GS3"),
            (interpolated[2], average + ";fallback_interp_bill_long"),
        ],
        "UST_5Y": [
            (month_ends["DGS5"], ""),
            (monthly["GS5"], average),
            (interpolated[5], average + ";fallback_interp_bill_long"),
        ],
        "UST_10Y": [(month_ends["DGS10"], ""), (monthly["GS10"], average), (long_rate, average + ";shiller_long_rate")],
        "UST_20Y": [
            (month_ends["DGS20"], ""),
            (month_ends["DGS30"], "fallback_DGS30"),
            (monthly["GS20"], average),
            (monthly["GS30"], average + ";fallback_GS30"),
            (long_rate, average + ";shiller_long_rate"),
        ],
    }


def _add_treasury_bonds(collector: _AssetCollector, fx: _FxConverter, risk_free: pd.Series) -> None:
    sources = _treasury_yield_sources(risk_free)
    for asset_id, (maturity, name, universe_tickers) in TREASURIES.items():
        yields, source_flags = _splice_yields(sources[asset_id])
        returns = bond_returns_from_yields(yields, maturity)
        collector.add(
            asset_id,
            returns,
            fx.usd_to_cad(returns),
            "Synthetic par-bond return from yields (FRED GS*, Shiller long rate, KF RF); engine/bonds.py",
            _flag_splices(source_flags),
            name=name,
            cls="bond_synthetic",
            ccy="USD",
            tags="bond;government;defensive",
            universe=universe_tickers,
            notes=(
                f"Constant maturity {maturity}y par bond; month-end yields from daily FRED DGS* when available, else "
                f"monthly averages (flag monthly_avg_yield); no costs. See SOURCES.md for fallbacks."
            ),
            maturity=maturity,
        )


CORPORATE_BONDS = [  # Moody's FRED series, name, tags
    ("AAA", "US corporate Moody's Aaa (synthetic, ~20y)", "bond;corporate;investment_grade;defensive"),
    ("BAA", "US corporate Moody's Baa (synthetic, ~20y)", "bond;corporate;investment_grade;credit_risk"),
]


def _add_corporate_bonds(collector: _AssetCollector, fx: _FxConverter) -> None:
    for series_id, name, tags in CORPORATE_BONDS:
        month_end_yields = daily_to_month_end(load_fred("D" + series_id).dropna())
        month_end_yields = month_end_yields[month_end_yields.index <= LAST_COMPLETE]
        yields, flags = _splice_yields(
            [(month_end_yields, "no_default_losses"), (fred_monthly(series_id), "no_default_losses;monthly_avg_yield")]
        )
        returns = bond_returns_from_yields(yields, 20)
        flags[flags != flags.shift(1)] = flags[flags != flags.shift(1)] + ";splice"
        flags.iloc[0] = flags.iloc[1].replace(";splice", "") if len(flags) > 1 else flags.iloc[0]
        collector.add(
            f"CORP_{series_id}",
            returns,
            fx.usd_to_cad(returns),
            (
                f"Synthetic par-bond return from FRED D{series_id} (month-end) / {series_id} (monthly avg), "
                f"Moody's seasoned yields; engine/bonds.py"
            ),
            flags,
            name=name,
            cls="bond_synthetic",
            ccy="USD",
            tags=tags,
            universe="AGG(partial: corporate sleeve)",
            notes=(
                "Yield-based reconstruction ignores defaults, downgrades and calls -> overstates realised "
                "return, especially Baa."
            ),
            maturity=20,
        )


def _gold_flags(months: pd.DatetimeIndex) -> pd.Series:
    flags = pd.Series("", index=months, dtype=object)
    flags[months < pd.Timestamp("1960-01-31")] = "annual_avg_repeated_monthly"
    flags[(months <= pd.Timestamp("1971-08-31"))] += ";fixed_official_price"
    flags[(months >= pd.Timestamp("1933-04-30")) & (months <= pd.Timestamp("1974-12-31"))] += (
        ";non_investable_us_private_ban"
    )
    return flags.str.strip(";")


def _add_gold(collector: _AssetCollector, fx: _FxConverter) -> None:
    gold = load_gold()
    returns = gold / gold.shift(1) - 1
    collector.add(
        "GOLD",
        returns,
        fx.usd_to_cad(returns),
        "datahub core/gold-prices (Timothy Green annual to 1959; World Bank Pink Sheet monthly avg 1960+)",
        _gold_flags(returns.index),
        name="Gold spot (USD/oz, no storage cost or yield)",
        cls="commodity",
        ccy="USD",
        tags="commodity;gold;defensive",
        universe="GLD",
        notes=(
            "Before 1960 annual averages repeated monthly (zero intra-year returns). Official fixed price "
            "until Aug 1971; US private holding banned 1933-1974: treat pre-1975 gold as non-investable / "
            "uninformative."
        ),
    )


def _xiu_monthly_returns() -> pd.Series:
    """XIU.TO monthly returns: yfinance before the starter's first month end, the starter from it."""
    yahoo = daily_to_month_end(
        pd.read_csv(RAW / "yfinance" / "XIU.TO.csv", parse_dates=["date"]).set_index("date")["adj_close"]
    )
    starter = pd.read_csv(STARTER / "prices_daily.csv", parse_dates=["date"])
    starter = daily_to_month_end(starter[starter["ticker"] == "XIU.TO"].set_index("date")["adj_close"])
    prices = pd.concat([yahoo[yahoo.index < STARTER_BASE], starter])
    return prices / prices.shift(1) - 1


def _add_canadian_equity(collector: _AssetCollector, fx: _FxConverter) -> None:
    kf_canada = load_kf_canada()
    # KF international data is updated once a year: extend with XIU.TO (starter / yfinance) after its last month
    xiu = _xiu_monthly_returns()
    extension = xiu[(xiu.index > kf_canada.index.max()) & (xiu.index <= LAST_COMPLETE)].dropna()
    local = pd.concat([kf_canada["local"], extension])
    usd = pd.concat([kf_canada["usd"], fx.cad_to_usd(extension)])
    flags = pd.Series("", index=local.index, dtype=object)
    flags[extension.index] = "extended_with_XIU.TO"
    collector.add(
        "CA_EQ",
        usd,
        local,
        "Ken French International Countries: Canada, value-weighted (MSCI/Bloomberg-based), USD and local",
        flags,
        name="Canadian stock market (KF value-weighted, total return)",
        cls="equity_ca",
        ccy="CAD",
        tags="equity;broad_market;canada",
        universe="XIU.TO;RY.TO;TD.TO;MFC.TO;ENB.TO;CNQ.TO;CNR.TO;FTS.TO;ATD.TO;SHOP.TO;CSU.TO",
        notes=(
            "Starts 1977; KF international files are updated annually -> months after the KF end are XIU.TO "
            "total returns (flag extended_with_XIU.TO). return_usd is KF's own USD series."
        ),
    )


def _add_canadian_rates(collector: _AssetCollector, fx: _FxConverter) -> None:
    long_yield = fred_monthly("IRLTLT01CAM156N")
    returns = bond_returns_from_yields(long_yield, 10)
    collector.add(
        "CA_GOV_10Y",
        fx.cad_to_usd(returns),
        returns,
        "Synthetic par-bond return from FRED IRLTLT01CAM156N (OECD MEI, Canada long-term gov yield); engine/bonds.py",
        "monthly_avg_yield",
        name="Government of Canada ~10y (synthetic)",
        cls="bond_synthetic",
        ccy="CAD",
        tags="bond;government;defensive;canada",
        universe="XBB.TO(approx: universe index incl. provincials/corporates)",
        notes="OECD long-term yield (~10y benchmark), monthly average (smooths returns); no costs.",
        maturity=10,
    )
    interbank = fred_monthly("IR3TIB01CAM156N")
    returns = (interbank.shift(1) / 100) / 12  # rate known at start of month, earned over the month
    collector.add(
        "CA_TBILL",
        fx.cad_to_usd(returns),
        returns,
        "FRED IR3TIB01CAM156N (OECD 3-month interbank rate, Canada), simple monthly accrual",
        "proxy_interbank_rate",
        name="Canadian cash (~3-month money market)",
        cls="cash",
        ccy="CAD",
        tags="cash;defensive;canada",
        universe="ZST.TO(approx)",
        notes="Interbank rate, not an investable T-bill index; accrual = previous month rate / 12.",
    )


TICKER_CLASSES = {  # starter asset_class -> catalogue asset_class
    "equity": "equity_single",
    "etf_equity": "etf_equity",
    "etf_bond": "etf_bond",
    "etf_commodity": "commodity",
    "crypto": "crypto",
}
SECTOR_TAGS = {
    "Financials": "financials",
    "Energy": "energy;fossil_fuel",
    "Industrials": "industrials",
    "Utilities": "utilities;defensive_sector",
    "Consumer Staples": "consumer_staples;defensive_sector",
    "Information Technology": "tech",
    "Communication Services": "communication;tech_platform",
    "Consumer Discretionary": "consumer_discretionary",
    "Health Care": "healthcare;defensive_sector",
}
TICKER_TAGS = {
    "GOOGL": "tech",
    "AMZN": "tech_platform",
    "QQQ": "tech_heavy;broad_market",
    "SPY": "broad_market",
    "XIU.TO": "broad_market;canada",
    "ESGV": "broad_market;esg_screened",
    "XBB.TO": "bond;defensive;canada",
    "ZST.TO": "bond;cash_like;defensive;canada",
    "AGG": "bond;defensive",
    "TLT": "bond;government;defensive;long_duration",
    "GLD": "gold;defensive",
    "BTC-USD": "speculative",
    "ETH-USD": "speculative",
}
TICKER_PROXIES = {
    "SPY": "US_MKT",
    "ESGV": "US_MKT",
    "QQQ": "US_IND_BUSEQ(partial);US_MKT",
    "XIU.TO": "CA_EQ",
    "XBB.TO": "CA_GOV_10Y",
    "ZST.TO": "CA_TBILL",
    "AGG": "UST_5Y;CORP_AAA",
    "TLT": "UST_20Y",
    "GLD": "GOLD",
}


def _yfinance_monthly_returns(ticker: str) -> pd.Series:
    prices = pd.read_csv(RAW / "yfinance" / f"{ticker}.csv", parse_dates=["date"]).set_index("date")["adj_close"]
    prices.index = (
        pd.DatetimeIndex(prices.index).tz_localize(None) if getattr(prices.index, "tz", None) else prices.index
    )
    monthly_prices = daily_to_month_end(prices)
    return (monthly_prices / monthly_prices.shift(1) - 1).dropna()


def _starter_monthly_returns(ticker: str, starter_prices: pd.DataFrame) -> pd.Series:
    monthly_prices = daily_to_month_end(
        starter_prices[starter_prices["ticker"] == ticker].set_index("date")["adj_close"]
    )
    returns = (monthly_prices / monthly_prices.shift(1) - 1).dropna()
    return returns[(returns.index >= STARTER_FIRST_RETURN) & (returns.index <= LAST_COMPLETE)]


def _overlap_check(ticker: str, yahoo: pd.Series, starter: pd.Series) -> dict:
    """yfinance vs starter concordance on their common months (one row of qa_overlap.csv)."""
    both = pd.concat([yahoo, starter], axis=1, keys=["yf", "st"]).dropna()
    return {
        "ticker": ticker,
        "n_overlap_months": len(both),
        "corr": round(both["yf"].corr(both["st"]), 6) if len(both) > 2 else np.nan,
        "mean_abs_diff": round((both["yf"] - both["st"]).abs().mean(), 6),
        "max_abs_diff": round((both["yf"] - both["st"]).abs().max(), 6),
    }


def _spliced_ticker_returns(
    ticker: str, yahoo: pd.Series, starter: pd.Series, starter_prices: pd.DataFrame
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Monthly returns (yfinance before the starter's first return, the starter from it), their source and flags."""
    returns = pd.concat([yahoo[yahoo.index < STARTER_FIRST_RETURN], starter])
    source = pd.Series("yfinance adj_close (daily -> last day of month)", index=returns.index)
    source[returns.index >= STARTER_FIRST_RETURN] = "starter prices_daily.csv adj_close (daily -> last day of month)"
    flags = pd.Series("", index=returns.index, dtype=object)
    flags.iloc[0] = "first_month_after_listing"
    if ticker == "CNQ.TO":
        returns, flags = fix_cnq_special_dividend(returns, flags, starter_prices)
    return returns, source, flags


def _ticker_tags(row: pd.Series) -> str:
    ticker = row["ticker"]
    return ";".join(
        tag
        for tag in [
            "equity" if row["asset_class"] in ("equity", "etf_equity") else "",
            SECTOR_TAGS.get(row["sector"], ""),
            TICKER_TAGS.get(ticker, ""),
            "canada" if row["currency"] == "CAD" and ticker not in TICKER_TAGS else "",
            "crypto" if row["asset_class"] == "crypto" else "",
        ]
        if tag
    )


def _ticker_catalogue_entry(row: pd.Series) -> dict:
    return {
        "name": row["name"],
        "cls": TICKER_CLASSES[row["asset_class"]],
        "ccy": row["currency"],
        "tags": _ticker_tags(row),
        "universe": row["ticker"],
        "proxy": TICKER_PROXIES.get(row["ticker"], ""),
        "notes": (
            f"Real ticker ({row['market']}). Starter sector: {row['sector']}. Survivorship bias: universe "
            f"chosen in 2026."
        ),
    }


def _add_starter_tickers(collector: _AssetCollector, fx: _FxConverter, starter_prices: pd.DataFrame) -> list[dict]:
    """Real tickers: yfinance history, then the starter from 2021-12. Returns the rows of qa_overlap.csv."""
    overlap_rows = []
    for _, row in universe().iterrows():
        ticker = row["ticker"]
        yahoo = _yfinance_monthly_returns(ticker)
        starter = _starter_monthly_returns(ticker, starter_prices)
        overlap_rows.append(_overlap_check(ticker, yahoo, starter))
        returns, source, flags = _spliced_ticker_returns(ticker, yahoo, starter, starter_prices)
        return_usd, return_cad = fx.in_both_currencies(returns, row["currency"])
        records = pd.DataFrame(
            {
                "date": returns.index,
                "return_usd": return_usd.values,
                "return_cad": return_cad.values,
                "asset_id": ticker,
                "source": source.values,
                "flag": flags.values,
            }
        )
        records = records[(records["date"] >= FLOOR) & (records["date"] <= LAST_COMPLETE)]
        collector.add_records(ticker, records, _ticker_catalogue_entry(row))
    return overlap_rows


def _write_long_table(records: list[pd.DataFrame]) -> pd.DataFrame:
    long = pd.concat(records, ignore_index=True)
    long = long[["date", "asset_id", "return_usd", "return_cad", "source", "flag"]]
    long = long.sort_values(["asset_id", "date"]).reset_index(drop=True)
    long["date"] = pd.to_datetime(long["date"])
    long.to_parquet(OUT / "monthly_returns.parquet", index=False)
    return long


EXPOSURE_TAGS = ("tech", "energy", "financials", "utilities", "healthcare", "crypto", "gold")
US_MKT_LOOKTHROUGH = {  # exposure tag -> KF industry whose share of US market cap measures it
    "tech": "US_IND_BUSEQ",
    "energy": "US_IND_ENRGY",
    "financials": "US_IND_MONEY",
    "utilities": "US_IND_UTILS",
    "healthcare": "US_IND_HLTH",
}
COVERAGE_COLUMNS = ["asset_id", "asset_class", "start", "end", "n_months"]


def _exposures(asset_id: str, tags: str, last_share: pd.Series) -> dict[str, float]:
    """Exposures for look-through constraints (static, data-derived where possible): 1.0 for each exposure tag the
    asset carries; US_MKT gets the latest market-cap share of its industries."""
    if asset_id == "US_MKT":
        return {tag: round(float(last_share[industry]), 4) for tag, industry in US_MKT_LOOKTHROUGH.items()}
    tag_list = [tag for tag in tags.split(";") if tag]
    return {tag: 1.0 for tag in EXPOSURE_TAGS if tag in tag_list}


def _catalogue_row(asset_id: str, entry: dict, long: pd.DataFrame, last_share: pd.Series) -> dict:
    rows = long[long["asset_id"] == asset_id]
    valid = rows.dropna(subset=["return_usd"]) if entry["ccy"] == "USD" else rows.dropna(subset=["return_cad"])
    exposures = _exposures(asset_id, entry["tags"], last_share)
    return {
        "asset_id": asset_id,
        "name": entry["name"],
        "asset_class": entry["cls"],
        "currency": entry["ccy"],
        "start": valid["date"].min().date(),
        "end": valid["date"].max().date(),
        "n_months": len(valid),
        "tags": entry["tags"],
        "exposures": ";".join(f"{tag}={value}" for tag, value in exposures.items()),
        "universe_tickers": entry["universe"],
        "proxy_for_ticker": entry.get("proxy", ""),
        "maturity_years": entry.get("maturity", ""),
        "notes": entry["notes"],
    }


def _write_catalogue(catalogue: dict[str, dict], long: pd.DataFrame, lookthrough: pd.DataFrame) -> pd.DataFrame:
    """Writes assets.csv and coverage.csv; returns the catalogue."""
    last_share = lookthrough.iloc[-1]
    assets = pd.DataFrame([_catalogue_row(asset_id, entry, long, last_share) for asset_id, entry in catalogue.items()])
    assets.to_csv(OUT / "assets.csv", index=False)
    assets[COVERAGE_COLUMNS].to_csv(OUT / "coverage.csv", index=False)
    return assets


def _write_qa_overlap(overlap_rows: list[dict]) -> pd.DataFrame:
    overlap = pd.DataFrame(overlap_rows)
    overlap.to_csv(OUT / "qa_overlap.csv", index=False)
    return overlap


PROXY_PAIRS = [  # proxy, real ETF, column of the ETF's currency
    ("US_MKT", "SPY", "return_usd"),
    ("UST_20Y", "TLT", "return_usd"),
    ("UST_10Y", "AGG", "return_usd"),
    ("UST_5Y", "AGG", "return_usd"),
    ("CORP_AAA", "AGG", "return_usd"),
    ("GOLD", "GLD", "return_usd"),
    ("CA_EQ", "XIU.TO", "return_cad"),
    ("CA_GOV_10Y", "XBB.TO", "return_cad"),
    ("CA_TBILL", "ZST.TO", "return_cad"),
    ("US_IND_BUSEQ", "QQQ", "return_usd"),
]


def _proxy_vs_etf(long: pd.DataFrame) -> dict[str, dict]:
    """Proxy vs real ETF concordance on their overlap (in the ETF's currency)."""
    concordance = {}
    for proxy, etf, column in PROXY_PAIRS:
        pair = long[long["asset_id"].isin([proxy, etf]) & ~long["flag"].str.contains("extended_with")]
        pair = pair.pivot(index="date", columns="asset_id", values=column).dropna()
        concordance[f"{proxy}~{etf}"] = {
            "n_months": len(pair),
            "first": str(pair.index.min().date()),
            "last": str(pair.index.max().date()),
            "corr": round(float(pair[proxy].corr(pair[etf])), 4),
            "ann_mean_proxy": round(float(pair[proxy].mean() * 12), 4),
            "ann_mean_etf": round(float(pair[etf].mean() * 12), 4),
            "vol_proxy": round(float(pair[proxy].std() * 12**0.5), 4),
            "vol_etf": round(float(pair[etf].std() * 12**0.5), 4),
        }
    return concordance


def _cnq_month_returns(long: pd.DataFrame) -> dict[str, float]:
    months = pd.to_datetime(["2022-07-31", "2022-08-31", "2022-09-30"])
    cnq = long[(long["asset_id"] == "CNQ.TO") & (long["date"].isin(months))]
    return {
        str(month.date()): round(float(value), 6) for month, value in zip(cnq["date"], cnq["return_cad"], strict=True)
    }


def _cnq_daily_returns(starter_prices: pd.DataFrame) -> dict[str, dict[str, float]]:
    """CNQ.TO daily close and adj_close returns around its 2022-08-22 special dividend (starter)."""
    days = starter_prices[starter_prices["ticker"] == "CNQ.TO"].set_index("date").loc["2022-08-17":"2022-08-25"]
    return {
        str(day.date()): {"close_ret": round(float(close), 5), "adj_close_ret": round(float(adjusted), 5)}
        for day, close, adjusted in zip(
            days.index[1:],
            (days["close"] / days["close"].shift(1) - 1).iloc[1:],
            (days["adj_close"] / days["adj_close"].shift(1) - 1).iloc[1:],
            strict=True,
        )
    }


def _quality_checks(
    fx_overlap: pd.DataFrame, cpi_overlap: pd.DataFrame, long: pd.DataFrame, starter_prices: pd.DataFrame
) -> dict:
    return {
        "fx_fred_vs_starter_month_end": {
            "n": len(fx_overlap),
            "max_abs_diff": float((fx_overlap["fred"] - fx_overlap["starter"]).abs().max()),
        },
        "cpi_ca_oecd_vs_statcan_monthly_inflation": {
            "n": len(cpi_overlap),
            "corr": float(cpi_overlap.corr().iloc[0, 1]),
            "mean_abs_diff": float((cpi_overlap["oecd"] - cpi_overlap["statcan"]).abs().mean()),
        },
        "cnq_2022_08_month_return_starter": _cnq_month_returns(long),
        "proxy_vs_etf": _proxy_vs_etf(long),
        "cnq_fix_2022_08_22": CNQ_FIX,
        "cnq_daily_around_2022_08_22": _cnq_daily_returns(starter_prices),
    }


def _write_data_version(long: pd.DataFrame, checks: dict) -> dict:
    canon = long.to_csv(index=False, float_format="%.8f").encode()  # 1e-8: ignores Yahoo float noise on re-download
    version = {
        "data_sha256": _sha256(canon)[:16],
        "built_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "last_complete_month": str(LAST_COMPLETE.date()),
        "n_rows": len(long),
        "n_assets": long["asset_id"].nunique(),
        "qa": checks,
        "raw_manifests": {
            path.parent.name: json.loads(path.read_text()) for path in sorted(RAW.glob("*/manifest.json"))
        },
    }
    (OUT / "data_version.json").write_text(json.dumps(version, indent=2, default=str))
    return version


def _print_summary(version: dict, assets: pd.DataFrame, overlap: pd.DataFrame) -> None:
    print(f"[build] {version['n_rows']} rows, {version['n_assets']} assets, version {version['data_sha256']}")
    print(assets[COVERAGE_COLUMNS].to_string(index=False))
    print(overlap.to_string(index=False))
    print(json.dumps(version["qa"], indent=1))


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    collector = _AssetCollector()
    fx, fx_overlap = _write_fx_monthly()
    cpi_overlap = _write_inflation_monthly()
    risk_free = _add_us_market(collector, fx)
    lookthrough = _add_us_industries(collector, fx)
    _add_treasury_bonds(collector, fx, risk_free)
    _add_corporate_bonds(collector, fx)
    _add_gold(collector, fx)
    _add_canadian_equity(collector, fx)
    _add_canadian_rates(collector, fx)
    starter_prices = pd.read_csv(STARTER / "prices_daily.csv", parse_dates=["date"])
    overlap_rows = _add_starter_tickers(collector, fx, starter_prices)
    long = _write_long_table(collector.records)
    assets = _write_catalogue(collector.catalogue, long, lookthrough)
    overlap = _write_qa_overlap(overlap_rows)
    version = _write_data_version(long, _quality_checks(fx_overlap, cpi_overlap, long, starter_prices))
    _print_summary(version, assets, overlap)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="re-download all raw files")
    parser.add_argument("--offline", action="store_true", help="do not download, build from <data dir>/raw only")
    parser.add_argument("--daily-only", action="store_true", help="only build the daily market parquets")
    arguments = parser.parse_args()
    if not arguments.offline:
        download_all(refresh=arguments.refresh)
    if not arguments.daily_only:
        build()
    daily_data.build_daily(OUT, RAW)


if __name__ == "__main__":
    main()
