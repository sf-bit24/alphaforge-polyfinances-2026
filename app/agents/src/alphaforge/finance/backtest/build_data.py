"""Rebuild the monthly long-history dataset from scratch.

Usage (from app/agents/):
    uv run --group finance --group backtest-data python -I -m alphaforge.finance.backtest.build_data
        [--refresh]   # re-download everything
        [--offline]   # build from <data dir>/raw only, no network

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
LAST_COMPLETE = (pd.Timestamp.today().normalize().replace(day=1) - pd.Timedelta(days=1))  # last full month
STARTER_FIRST_RETURN = pd.Timestamp("2021-12-31")  # first month whose base (2021-11-30) is in the starter
# FRED's bot filter rejects unknown/browser-like agents from scripts; a plain curl UA is accepted.
UA = "curl/8.5.0"

KF = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
FRED_SERIES = ["GS1", "GS2", "GS3", "GS5", "GS10", "GS20", "GS30", "AAA", "BAA",
               "DGS1", "DGS2", "DGS3", "DGS5", "DGS10", "DGS20", "DGS30", "DAAA", "DBAA",
               "CPIAUCNS", "DEXCAUS", "CANCPIALLMINMEI", "IRLTLT01CAM156N", "IR3TIB01CAM156N"]
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
    },
}


# --------------------------------------------------------------------------- download
def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _manifest(src_dir: Path) -> dict:
    p = src_dir / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _write_manifest(src_dir: Path, man: dict) -> None:
    (src_dir / "manifest.json").write_text(json.dumps(man, indent=2, sort_keys=True))


def fetch(url: str, timeout: int = 120) -> bytes:
    # Only the fixed https URLs of DOWNLOADS reach this point (no file:// nor user-supplied scheme).
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-https URL: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})  # noqa: S310 (https checked above)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (https checked above)
        return r.read()


def download_all(refresh: bool) -> None:
    for source, files in DOWNLOADS.items():
        d = RAW / source
        d.mkdir(parents=True, exist_ok=True)
        man = _manifest(d)
        for fname, url in files.items():
            target = d / fname
            if target.exists() and not refresh:
                continue
            print(f"[download] {source}/{fname}")
            b = fetch(url)
            target.write_bytes(b)
            man[fname] = {"url": url, "retrieved_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                          "sha256": _sha256(b), "bytes": len(b)}
            _write_manifest(d, man)
    download_yfinance(refresh)


def universe() -> pd.DataFrame:
    return pd.read_csv(STARTER / "assets_universe.csv")


def download_yfinance(refresh: bool) -> None:
    d = RAW / "yfinance"
    d.mkdir(parents=True, exist_ok=True)
    man = _manifest(d)
    tickers = list(universe()["ticker"])
    todo = [t for t in tickers if refresh or not (d / f"{t}.csv").exists()]
    if not todo:
        return
    import yfinance as yf  # imported lazily: only needed when downloading

    for t in todo:
        print(f"[download] yfinance/{t}")
        df = yf.download(t, period="max", interval="1d", auto_adjust=False, actions=False,
                         progress=False, threads=False, multi_level_index=False)
        if df is None or df.empty:
            raise RuntimeError(f"yfinance returned no data for {t}")
        df = df[["Close", "Adj Close"]].rename(columns={"Close": "close", "Adj Close": "adj_close"})
        df.index.name = "date"
        b = df.to_csv().encode()
        (d / f"{t}.csv").write_bytes(b)
        man[f"{t}.csv"] = {"url": f"yfinance.download('{t}', period='max', interval='1d', auto_adjust=False)",
                           "retrieved_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                           "sha256": _sha256(b), "bytes": len(b)}
    _write_manifest(d, man)


# --------------------------------------------------------------------------- parsers
def month_end(idx) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(idx)).to_period("M").to_timestamp(how="end").normalize()


def _yyyymm_to_me(s: pd.Series) -> pd.DatetimeIndex:
    return month_end(pd.to_datetime(s.astype(str).str.strip(), format="%Y%m"))


def _kf_block(text: str, header_startswith: str | None, first_block: bool = False) -> pd.DataFrame:
    """Parse a monthly block (YYYYMM rows) from a Ken French CSV text."""
    lines = text.splitlines()
    start = 0
    if header_startswith is not None:
        start = next(i for i, ln in enumerate(lines) if ln.strip().startswith(header_startswith))
    # header line = first line after start that begins with ','
    h = next(i for i in range(start, len(lines)) if lines[i].startswith(","))
    cols = [c.strip() for c in lines[h].split(",")[1:]]
    rows = []
    for ln in lines[h + 1:]:
        parts = [p.strip() for p in ln.split(",")]
        if len(parts[0]) != 6 or not parts[0].isdigit():
            break
        rows.append(parts)
    df = pd.DataFrame(rows, columns=["yyyymm"] + cols)
    df.index = _yyyymm_to_me(df.pop("yyyymm"))
    df = df.apply(pd.to_numeric)
    return df.mask(df <= -99.99)


def read_zip_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))][0]
        return z.read(name).decode("latin-1")


def load_kf_factors() -> pd.DataFrame:
    txt = read_zip_text(RAW / "kenfrench" / "F-F_Research_Data_Factors_CSV.zip")
    return _kf_block(txt, None) / 100.0  # first block is monthly


def load_kf_industries() -> tuple[pd.DataFrame, pd.DataFrame]:
    txt = read_zip_text(RAW / "kenfrench" / "12_Industry_Portfolios_CSV.zip")
    vw = _kf_block(txt, "Average Value Weighted Returns -- Monthly") / 100.0
    nfirms = _kf_block(txt, "Number of Firms in Portfolios")
    size = _kf_block(txt, "Average Firm Size")
    cap = nfirms * size
    share = cap.div(cap.sum(axis=1), axis=0)
    return vw, share


def load_kf_canada() -> pd.DataFrame:
    with zipfile.ZipFile(RAW / "kenfrench" / "F-F_International_Countries.zip") as z:
        name = [n for n in z.namelist() if n.lower().startswith("canada")][0]
        txt = z.read(name).decode("latin-1")
    lines = txt.splitlines()

    def block(title: str) -> pd.Series:
        i = next(k for k, ln in enumerate(lines) if title in ln and "Not Reqd" in ln)
        out = {}
        for ln in lines[i + 3:]:
            p = ln.split()
            if not p or len(p[0]) != 6 or not p[0].isdigit():
                break
            out[p[0]] = float(p[1])
        s = pd.Series(out)
        s.index = _yyyymm_to_me(pd.Series(s.index))
        return (s.mask(s <= -99.99) / 100.0)

    return pd.DataFrame({"usd": block("Value-Weight Dollar Returns"), "local": block("Value-Weight Local  Returns")})


def load_fred(series: str) -> pd.Series:
    df = pd.read_csv(RAW / "fred" / f"{series}.csv")
    df.columns = ["date", "value"]
    s = pd.Series(pd.to_numeric(df["value"], errors="coerce").values, index=pd.to_datetime(df["date"]), name=series)
    return s


def fred_monthly(series: str) -> pd.Series:
    s = load_fred(series)
    s.index = month_end(s.index)
    return s


def load_shiller_gs10() -> pd.Series:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # pandas deprecation notice for the xlrd engine (.xls format)
        x = pd.read_excel(RAW / "shiller" / "ie_data.xls", sheet_name="Data", header=None, engine="xlrd")
    x = x.iloc[8:, [0, 6]].dropna()
    x = x[pd.to_numeric(x[0], errors="coerce").notna()]
    d = x[0].astype(float)
    year = np.floor(d).astype(int)
    month = np.round((d - year) * 100).astype(int)
    idx = month_end(pd.to_datetime(dict(year=year, month=month, day=1)))
    return pd.Series(pd.to_numeric(x[6]).values, index=idx, name="SHILLER_GS10")


def load_gold() -> pd.Series:
    g = pd.read_csv(RAW / "datahub_gold" / "monthly.csv")
    s = pd.Series(g["Price"].astype(float).values, index=month_end(pd.to_datetime(g["Date"], format="%Y-%m")))
    return s


def load_boc(series: str) -> pd.Series:
    txt = (RAW / "bankofcanada" / f"{series}.csv").read_text()
    body = txt.split('"OBSERVATIONS"', 1)[1]
    df = pd.read_csv(io.StringIO(body.strip()))
    s = pd.Series(pd.to_numeric(df[series], errors="coerce").values, index=month_end(pd.to_datetime(df["date"])))
    return s


def daily_to_month_end(px: pd.Series) -> pd.Series:
    """Last available observation of each calendar month (no forward fill across months)."""
    px = px.dropna()
    m = px.groupby(px.index.to_period("M")).last()
    m.index = m.index.to_timestamp(how="end").normalize()
    return m


def fix_cnq_special_dividend(r: pd.Series, fl: pd.Series, st_px: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """CNQ.TO 2022-08-22: Yahoo recorded the special dividend both as a 1.021 'split' and as a
    0.75 dividend, so adj_close double-counts ~2 % on that day. We replace that day's adj_close
    return by the true total return (close_t + dividend) / (close_{t-1} * split) - 1, using the
    starter's own close, corporate_actions.csv split and dividend values."""
    ca = pd.read_csv(STARTER / "corporate_actions.csv", parse_dates=["ex_date"])
    ev = pd.Timestamp("2022-08-22")
    sp = ca[(ca.ticker == "CNQ.TO") & (ca.ex_date == ev) & (ca.action == "split")]["value"]
    dv = ca[(ca.ticker == "CNQ.TO") & (ca.ex_date == ev) & (ca.action == "dividend")]["value"]
    if sp.empty or dv.empty:
        return r, fl
    d = st_px[st_px["ticker"] == "CNQ.TO"].set_index("date").sort_index()
    i = d.index.get_loc(ev)
    prev, cur = d.iloc[i - 1], d.iloc[i]
    adj_ret = cur["adj_close"] / prev["adj_close"] - 1
    true_ret = (cur["close"] + float(dv.iloc[0])) / (prev["close"] * float(sp.iloc[0])) - 1
    m = month_end([ev])[0]
    if m in r.index:
        r = r.copy()
        r[m] = (1 + r[m]) * (1 + true_ret) / (1 + adj_ret) - 1
        fl = fl.copy()
        fl[m] = "corrected_double_counted_special_dividend"
    CNQ_FIX.update(
        {"day_adj_close_return": round(float(adj_ret), 6), "day_true_total_return": round(float(true_ret), 6)}
    )
    return r, fl


CNQ_FIX: dict = {}


# --------------------------------------------------------------------------- build
def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rec: list[pd.DataFrame] = []  # long records
    meta: dict[str, dict] = {}  # asset catalogue

    def add(asset_id, r_usd, r_cad, source, flag, **m):
        idx = (r_usd if r_usd is not None else r_cad).index
        df = pd.DataFrame(
            {
                "date": idx,
                "return_usd": r_usd.reindex(idx).values if r_usd is not None else np.nan,
                "return_cad": r_cad.reindex(idx).values if r_cad is not None else np.nan,
            }
        )
        df["asset_id"] = asset_id
        df["source"] = source
        df["flag"] = flag.reindex(idx).fillna("").values if isinstance(flag, pd.Series) else flag
        df = df[(df["date"] >= FLOOR) & (df["date"] <= LAST_COMPLETE)]
        df = df.dropna(subset=["return_usd", "return_cad"], how="all")
        rec.append(df)
        meta[asset_id] = m

    # ---------------- FX (CAD per USD), month-end
    dex = load_fred("DEXCAUS").dropna()
    fx = daily_to_month_end(dex)
    fx_src = pd.Series("FRED DEXCAUS (last business day of month)", index=fx.index)
    st_fx = pd.read_csv(STARTER / "fx_usdcad_daily.csv", parse_dates=["date"]).set_index("date")["usdcad"]
    st_fx_m = daily_to_month_end(st_fx)
    st_fx_m = st_fx_m[st_fx_m.index >= pd.Timestamp("2021-11-30")]
    st_fx_m = st_fx_m[st_fx_m.index <= LAST_COMPLETE]
    qa_fx = pd.concat([fx, st_fx_m], axis=1, keys=["fred", "starter"]).dropna()
    fx = fx[fx.index < pd.Timestamp("2021-11-30")]
    fx = pd.concat([fx, st_fx_m])
    fx_src = fx_src.reindex(fx.index).fillna(
        "Bank of Canada via starter fx_usdcad_daily.csv (last available day of month)"
    )
    fx = fx[fx.index <= LAST_COMPLETE]
    fx_df = pd.DataFrame({"date": fx.index, "usdcad": fx.values, "source": fx_src.reindex(fx.index).values})
    fx_df.to_parquet(OUT / "fx_monthly.parquet", index=False)
    fx_ret = fx / fx.shift(1) - 1.0  # CAD return of holding 1 USD

    def usd_to_cad(r_usd: pd.Series) -> pd.Series:
        return (1 + r_usd) * (1 + fx_ret.reindex(r_usd.index)) - 1

    def cad_to_usd(r_cad: pd.Series) -> pd.Series:
        return (1 + r_cad) / (1 + fx_ret.reindex(r_cad.index)) - 1

    # ---------------- Inflation
    cpi_us = fred_monthly("CPIAUCNS")
    # BLS did not publish some months (e.g. Oct 2025, US government shutdown): log-linear
    # interpolation of the index for interior gaps, flagged in the output
    gap = cpi_us.isna() & (cpi_us.index > cpi_us.first_valid_index()) & (cpi_us.index < cpi_us.last_valid_index())
    cpi_us = np.exp(np.log(cpi_us).interpolate(limit_area="inside"))
    infl_us = cpi_us / cpi_us.shift(1) - 1
    us_flag = pd.Series("", index=cpi_us.index, dtype=object)
    for d in cpi_us.index[gap]:
        us_flag[d] = "cpi_interpolated"
        nxt = cpi_us.index[cpi_us.index.get_loc(d) + 1]
        us_flag[nxt] = "cpi_interpolated"  # the following month's inflation also depends on the gap
    cpi_ca_oecd = fred_monthly("CANCPIALLMINMEI").dropna()
    cpi_ca_sc = load_boc("V41690973").dropna()
    infl_ca_oecd = cpi_ca_oecd / cpi_ca_oecd.shift(1) - 1
    infl_ca_sc = cpi_ca_sc / cpi_ca_sc.shift(1) - 1
    qa_cpi = pd.concat([infl_ca_oecd, infl_ca_sc], axis=1, keys=["oecd", "statcan"]).dropna()
    splice = infl_ca_sc.index.min()  # StatCan from its 2nd month onward
    infl_ca = pd.concat([infl_ca_oecd[infl_ca_oecd.index < splice + pd.offsets.MonthEnd(1)], infl_ca_sc.dropna()])
    infl_ca = infl_ca[~infl_ca.index.duplicated(keep="last")].sort_index()
    infl = pd.DataFrame({"infl_us": infl_us, "infl_ca": infl_ca, "flag_us": us_flag})
    infl["flag_us"] = infl["flag_us"].fillna("")
    infl = infl[(infl.index >= FLOOR) & (infl.index <= LAST_COMPLETE)]
    infl.index.name = "date"
    infl.reset_index().to_parquet(OUT / "inflation_monthly.parquet", index=False)

    # ---------------- Ken French US market, RF, industries
    ff = load_kf_factors()
    rf = ff["RF"]
    mkt = ff["Mkt-RF"] + ff["RF"]
    add(
        "US_MKT",
        mkt,
        usd_to_cad(mkt),
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
    add(
        "UST_TBILL",
        rf,
        usd_to_cad(rf),
        "Ken French Data Library: RF (1-month T-bill, Ibbotson/CRSP)",
        "",
        name="US 1-month Treasury bill",
        cls="cash",
        ccy="USD",
        tags="cash;defensive;government",
        universe="(cash);ZST.TO(approx, CAD)",
        notes="Risk-free proxy. Before 1934 from Ibbotson/CRSP sources (per Ken French).",
    )

    vw, share = load_kf_industries()
    ind_tags = {
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
    ind_names = {
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
    ind_map = {
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
    for c in vw.columns:
        aid = f"US_IND_{c.upper()}"
        add(
            aid,
            vw[c],
            usd_to_cad(vw[c]),
            f"Ken French 12 Industry Portfolios, value-weighted ({c})",
            "",
            name=f"US industry: {ind_names[c]}",
            cls="sector_us",
            ccy="USD",
            tags="equity;sector;" + ind_tags[c],
            universe=ind_map[c],
            notes="SIC-based KF 12-industry definition (not GICS). Mapping to tickers is approximate.",
        )
    sh = share.copy()
    sh.columns = [f"US_IND_{c.upper()}" for c in sh.columns]
    sh = sh[(sh.index >= FLOOR) & (sh.index <= LAST_COMPLETE)]
    sh.index.name = "date"
    sh.reset_index().to_parquet(OUT / "lookthrough_us_mkt.parquet", index=False)

    # ---------------- US Treasury synthetic bonds
    shiller = load_shiller_gs10()
    gs = {s: fred_monthly(s) for s in ["GS1", "GS2", "GS3", "GS5", "GS10", "GS20", "GS30"]}
    rf_yield_pct = ((1 + rf) ** 12 - 1) * 100  # annualised T-bill yield, %
    y_long_pre53 = shiller  # Shiller long rate (GS10 after 1953, long gov yields before)
    pre53 = lambda s: s[s.index < pd.Timestamp("1953-04-30")]  # noqa: E731

    def interp(m: float) -> pd.Series:
        # linear-in-maturity interpolation between bill (0.083y) and long yield (10y), pre-1953 only
        yb, yl = rf_yield_pct, y_long_pre53
        a = (m - 1 / 12) / (10 - 1 / 12)
        return (yb + a * (yl - yb)).dropna()

    def assemble(parts: list[tuple[pd.Series, str]]) -> tuple[pd.Series, pd.Series]:
        y = pd.Series(dtype=float)
        f = pd.Series(dtype=object)
        for s, flag in parts:
            s = s.dropna()
            new = s.index.difference(y.index)
            y = pd.concat([y, s.reindex(new)])
            f = pd.concat([f, pd.Series(flag, index=new)])
        return y.sort_index(), f.sort_index()

    # month-end yields from daily FRED series (preferred: no averaging), then monthly averages, then fallbacks
    dgs = {
        s: daily_to_month_end(load_fred(s).dropna())
        for s in ["DGS1", "DGS2", "DGS3", "DGS5", "DGS10", "DGS20", "DGS30"]
    }
    dgs = {k: v[v.index <= LAST_COMPLETE] for k, v in dgs.items()}
    dgs1_3 = ((dgs["DGS1"] + dgs["DGS3"]) / 2).dropna()
    gs1_3 = ((gs["GS1"] + gs["GS3"]) / 2).dropna()
    A = "monthly_avg_yield"
    specs = {
        "UST_2Y": (
            2,
            [
                (dgs["DGS2"], ""),
                (dgs1_3, "fallback_avg_DGS1_DGS3"),
                (gs1_3, A + ";fallback_avg_GS1_GS3"),
                (pre53(interp(2)), A + ";fallback_interp_bill_long"),
            ],
            "US Treasury ~2y constant maturity (synthetic)",
            "AGG(partial);ZST.TO(very approx)",
        ),
        "UST_5Y": (
            5,
            [(dgs["DGS5"], ""), (gs["GS5"], A), (pre53(interp(5)), A + ";fallback_interp_bill_long")],
            "US Treasury ~5y constant maturity (synthetic)",
            "AGG(approx: aggregate index incl. MBS/corporates)",
        ),
        "UST_10Y": (
            10,
            [(dgs["DGS10"], ""), (gs["GS10"], A), (pre53(shiller), A + ";shiller_long_rate")],
            "US Treasury ~10y constant maturity (synthetic)",
            "AGG(partial);TLT(partial)",
        ),
        "UST_20Y": (
            20,
            [
                (dgs["DGS20"], ""),
                (dgs["DGS30"], "fallback_DGS30"),
                (gs["GS20"], A),
                (gs["GS30"], A + ";fallback_GS30"),
                (pre53(shiller), A + ";shiller_long_rate"),
            ],
            "US Treasury ~20y constant maturity (synthetic)",
            "TLT",
        ),
    }
    for aid, (mat, parts, nm, uni) in specs.items():
        y, f = assemble(parts)
        # a month whose return mixes two yield sources is flagged as a splice
        r = bond_returns_from_yields(y, mat)
        fl = f.copy()
        fl[f != f.shift(1)] = (f[f != f.shift(1)] + ";splice").str.strip(";")
        fl.iloc[0] = f.iloc[0]
        add(
            aid,
            r,
            usd_to_cad(r),
            "Synthetic par-bond return from yields (FRED GS*, Shiller long rate, KF RF); engine/bonds.py",
            fl,
            name=nm,
            cls="bond_synthetic",
            ccy="USD",
            tags="bond;government;defensive",
            universe=uni,
            notes=(
                f"Constant maturity {mat}y par bond; month-end yields from daily FRED DGS* when available, else "
                f"monthly averages (flag monthly_avg_yield); no costs. See SOURCES.md for fallbacks."
            ),
            maturity=mat,
        )

    for s, nm, tg in [
        ("AAA", "US corporate Moody's Aaa (synthetic, ~20y)", "bond;corporate;investment_grade;defensive"),
        ("BAA", "US corporate Moody's Baa (synthetic, ~20y)", "bond;corporate;investment_grade;credit_risk"),
    ]:
        dly = daily_to_month_end(load_fred("D" + s).dropna())
        dly = dly[dly.index <= LAST_COMPLETE]
        y, f = assemble([(dly, "no_default_losses"), (fred_monthly(s), "no_default_losses;monthly_avg_yield")])
        r = bond_returns_from_yields(y, 20)
        f[f != f.shift(1)] = f[f != f.shift(1)] + ";splice"
        f.iloc[0] = f.iloc[1].replace(";splice", "") if len(f) > 1 else f.iloc[0]
        add(
            f"CORP_{s}",
            r,
            usd_to_cad(r),
            (
                f"Synthetic par-bond return from FRED D{s} (month-end) / {s} (monthly avg), Moody's seasoned "
                f"yields; engine/bonds.py"
            ),
            f,
            name=nm,
            cls="bond_synthetic",
            ccy="USD",
            tags=tg,
            universe="AGG(partial: corporate sleeve)",
            notes=(
                "Yield-based reconstruction ignores defaults, downgrades and calls -> overstates realised "
                "return, especially Baa."
            ),
            maturity=20,
        )

    # ---------------- Gold
    gold = load_gold()
    gr = gold / gold.shift(1) - 1
    gflag = pd.Series("", index=gr.index, dtype=object)
    gflag[gr.index < pd.Timestamp("1960-01-31")] = "annual_avg_repeated_monthly"
    gflag[(gr.index <= pd.Timestamp("1971-08-31"))] += ";fixed_official_price"
    gflag[(gr.index >= pd.Timestamp("1933-04-30")) & (gr.index <= pd.Timestamp("1974-12-31"))] += (
        ";non_investable_us_private_ban"
    )
    gflag = gflag.str.strip(";")
    add(
        "GOLD",
        gr,
        usd_to_cad(gr),
        "datahub core/gold-prices (Timothy Green annual to 1959; World Bank Pink Sheet monthly avg 1960+)",
        gflag,
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

    # ---------------- Canada
    kc = load_kf_canada()
    # KF international data is updated once a year: extend with XIU.TO (starter / yfinance) after its last month
    xiu = daily_to_month_end(
        pd.read_csv(RAW / "yfinance" / "XIU.TO.csv", parse_dates=["date"]).set_index("date")["adj_close"]
    )
    st_xiu = pd.read_csv(STARTER / "prices_daily.csv", parse_dates=["date"])
    st_xiu = daily_to_month_end(st_xiu[st_xiu["ticker"] == "XIU.TO"].set_index("date")["adj_close"])
    xiu = pd.concat([xiu[xiu.index < pd.Timestamp("2021-11-30")], st_xiu])
    xiu_r = xiu / xiu.shift(1) - 1
    ext = xiu_r[(xiu_r.index > kc.index.max()) & (xiu_r.index <= LAST_COMPLETE)].dropna()
    ca_local = pd.concat([kc["local"], ext])
    ca_usd = pd.concat([kc["usd"], cad_to_usd(ext)])
    ca_flag = pd.Series("", index=ca_local.index, dtype=object)
    ca_flag[ext.index] = "extended_with_XIU.TO"
    add(
        "CA_EQ",
        ca_usd,
        ca_local,
        "Ken French International Countries: Canada, value-weighted (MSCI/Bloomberg-based), USD and local",
        ca_flag,
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
    ca10 = fred_monthly("IRLTLT01CAM156N")
    r = bond_returns_from_yields(ca10, 10)
    add(
        "CA_GOV_10Y",
        cad_to_usd(r),
        r,
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
    ca3m = fred_monthly("IR3TIB01CAM156N")
    r = (ca3m.shift(1) / 100) / 12  # rate known at start of month, earned over the month
    add(
        "CA_TBILL",
        cad_to_usd(r),
        r,
        "FRED IR3TIB01CAM156N (OECD 3-month interbank rate, Canada), simple monthly accrual",
        "proxy_interbank_rate",
        name="Canadian cash (~3-month money market)",
        cls="cash",
        ccy="CAD",
        tags="cash;defensive;canada",
        universe="ZST.TO(approx)",
        notes="Interbank rate, not an investable T-bill index; accrual = previous month rate / 12.",
    )

    # ---------------- Real tickers (yfinance history + starter for 2021-12..)
    uni = universe()
    st_px = pd.read_csv(STARTER / "prices_daily.csv", parse_dates=["date"])
    qa_rows = []
    cls_map = {
        "equity": "equity_single",
        "etf_equity": "etf_equity",
        "etf_bond": "etf_bond",
        "etf_commodity": "commodity",
        "crypto": "crypto",
    }
    sector_tags = {
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
    ticker_extra = {
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
    proxy_of = {
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
    for _, row in uni.iterrows():
        t = row["ticker"]
        y = pd.read_csv(RAW / "yfinance" / f"{t}.csv", parse_dates=["date"]).set_index("date")["adj_close"]
        y.index = pd.DatetimeIndex(y.index).tz_localize(None) if getattr(y.index, "tz", None) else y.index
        ym = daily_to_month_end(y)
        yr = (ym / ym.shift(1) - 1).dropna()
        s = st_px[st_px["ticker"] == t].set_index("date")["adj_close"]
        sm = daily_to_month_end(s)
        sr = (sm / sm.shift(1) - 1).dropna()
        sr = sr[(sr.index >= STARTER_FIRST_RETURN) & (sr.index <= LAST_COMPLETE)]
        both = pd.concat([yr, sr], axis=1, keys=["yf", "st"]).dropna()
        qa_rows.append(
            {
                "ticker": t,
                "n_overlap_months": len(both),
                "corr": round(both["yf"].corr(both["st"]), 6) if len(both) > 2 else np.nan,
                "mean_abs_diff": round((both["yf"] - both["st"]).abs().mean(), 6),
                "max_abs_diff": round((both["yf"] - both["st"]).abs().max(), 6),
            }
        )
        r = pd.concat([yr[yr.index < STARTER_FIRST_RETURN], sr])
        src = pd.Series("yfinance adj_close (daily -> last day of month)", index=r.index)
        src[r.index >= STARTER_FIRST_RETURN] = "starter prices_daily.csv adj_close (daily -> last day of month)"
        fl = pd.Series("", index=r.index, dtype=object)
        fl.iloc[0] = "first_month_after_listing"
        if t == "CNQ.TO":
            r, fl = fix_cnq_special_dividend(r, fl, st_px)
        if row["currency"] == "CAD":
            r_cad, r_usd = r, cad_to_usd(r)
        else:
            r_usd, r_cad = r, usd_to_cad(r)
        df = pd.DataFrame(
            {
                "date": r.index,
                "return_usd": r_usd.values,
                "return_cad": r_cad.values,
                "asset_id": t,
                "source": src.values,
                "flag": fl.values,
            }
        )
        df = df[(df["date"] >= FLOOR) & (df["date"] <= LAST_COMPLETE)]
        rec.append(df)
        tags = ";".join(
            x
            for x in [
                "equity" if row["asset_class"] in ("equity", "etf_equity") else "",
                sector_tags.get(row["sector"], ""),
                ticker_extra.get(t, ""),
                "canada" if row["currency"] == "CAD" and t not in ticker_extra else "",
                "crypto" if row["asset_class"] == "crypto" else "",
            ]
            if x
        )
        meta[t] = dict(
            name=row["name"],
            cls=cls_map[row["asset_class"]],
            ccy=row["currency"],
            tags=tags,
            universe=t,
            proxy=proxy_of.get(t, ""),
            notes=(
                f"Real ticker ({row['market']}). Starter sector: {row['sector']}. Survivorship bias: universe "
                f"chosen in 2026."
            ),
        )

    # ---------------- assemble long table
    long = pd.concat(rec, ignore_index=True)
    long = long[["date", "asset_id", "return_usd", "return_cad", "source", "flag"]]
    long = long.sort_values(["asset_id", "date"]).reset_index(drop=True)
    long["date"] = pd.to_datetime(long["date"])
    long.to_parquet(OUT / "monthly_returns.parquet", index=False)

    # exposures for look-through constraints (static, data-derived where possible)
    last_share = sh.iloc[-1]
    rows = []
    for aid, m in meta.items():
        sub = long[long["asset_id"] == aid]
        valid = sub.dropna(subset=["return_usd"]) if m["ccy"] == "USD" else sub.dropna(subset=["return_cad"])
        exp = {}
        tags = [x for x in m["tags"].split(";") if x]
        for tg in ("tech", "energy", "financials", "utilities", "healthcare", "crypto", "gold"):
            if tg in tags:
                exp[tg] = 1.0
        if aid == "US_MKT":
            exp = {
                "tech": round(float(last_share["US_IND_BUSEQ"]), 4),
                "energy": round(float(last_share["US_IND_ENRGY"]), 4),
                "financials": round(float(last_share["US_IND_MONEY"]), 4),
                "utilities": round(float(last_share["US_IND_UTILS"]), 4),
                "healthcare": round(float(last_share["US_IND_HLTH"]), 4),
            }
        rows.append(
            {
                "asset_id": aid,
                "name": m["name"],
                "asset_class": m["cls"],
                "currency": m["ccy"],
                "start": valid["date"].min().date(),
                "end": valid["date"].max().date(),
                "n_months": len(valid),
                "tags": m["tags"],
                "exposures": ";".join(f"{k}={v}" for k, v in exp.items()),
                "universe_tickers": m["universe"],
                "proxy_for_ticker": m.get("proxy", ""),
                "maturity_years": m.get("maturity", ""),
                "notes": m["notes"],
            }
        )
    assets = pd.DataFrame(rows)
    assets.to_csv(OUT / "assets.csv", index=False)
    assets[["asset_id", "asset_class", "start", "end", "n_months"]].to_csv(OUT / "coverage.csv", index=False)

    qa = pd.DataFrame(qa_rows)
    qa.to_csv(OUT / "qa_overlap.csv", index=False)
    qa_extra = {
        "fx_fred_vs_starter_month_end": {
            "n": len(qa_fx),
            "max_abs_diff": float((qa_fx["fred"] - qa_fx["starter"]).abs().max()),
        },
        "cpi_ca_oecd_vs_statcan_monthly_inflation": {
            "n": len(qa_cpi),
            "corr": float(qa_cpi.corr().iloc[0, 1]),
            "mean_abs_diff": float((qa_cpi["oecd"] - qa_cpi["statcan"]).abs().mean()),
        },
        "cnq_2022_08_month_return_starter": None,
    }
    cnq = long[
        (long["asset_id"] == "CNQ.TO") & (long["date"].isin(pd.to_datetime(["2022-07-31", "2022-08-31", "2022-09-30"])))
    ]
    qa_extra["cnq_2022_08_month_return_starter"] = {
        str(d.date()): round(float(v), 6) for d, v in zip(cnq["date"], cnq["return_cad"], strict=True)
    }
    # proxy vs real ETF concordance on their overlap (in the ETF's currency)
    proxy_pairs = [
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
    pv = {}
    for a, b, col in proxy_pairs:
        x = long[long["asset_id"].isin([a, b]) & ~long["flag"].str.contains("extended_with")]
        x = x.pivot(index="date", columns="asset_id", values=col).dropna()
        pv[f"{a}~{b}"] = {
            "n_months": len(x),
            "first": str(x.index.min().date()),
            "last": str(x.index.max().date()),
            "corr": round(float(x[a].corr(x[b])), 4),
            "ann_mean_proxy": round(float(x[a].mean() * 12), 4),
            "ann_mean_etf": round(float(x[b].mean() * 12), 4),
            "vol_proxy": round(float(x[a].std() * 12**0.5), 4),
            "vol_etf": round(float(x[b].std() * 12**0.5), 4),
        }
    qa_extra["proxy_vs_etf"] = pv
    qa_extra["cnq_fix_2022_08_22"] = CNQ_FIX
    st_d = st_px[st_px["ticker"] == "CNQ.TO"].set_index("date")
    w = st_d.loc["2022-08-17":"2022-08-25"]
    qa_extra["cnq_daily_around_2022_08_22"] = {
        str(d.date()): {"close_ret": round(float(c), 5), "adj_close_ret": round(float(a_), 5)}
        for d, c, a_ in zip(
            w.index[1:],
            (w["close"] / w["close"].shift(1) - 1).iloc[1:],
            (w["adj_close"] / w["adj_close"].shift(1) - 1).iloc[1:],
            strict=True,
        )
    }
    canon = long.to_csv(index=False, float_format="%.8f").encode()  # 1e-8: ignores Yahoo float noise on re-download
    version = {
        "data_sha256": _sha256(canon)[:16],
        "built_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "last_complete_month": str(LAST_COMPLETE.date()),
        "n_rows": len(long),
        "n_assets": long["asset_id"].nunique(),
        "qa": qa_extra,
        "raw_manifests": {p.parent.name: json.loads(p.read_text()) for p in sorted(RAW.glob("*/manifest.json"))},
    }
    (OUT / "data_version.json").write_text(json.dumps(version, indent=2, default=str))
    print(f"[build] {len(long)} rows, {long['asset_id'].nunique()} assets, version {version['data_sha256']}")
    print(assets[["asset_id", "asset_class", "start", "end", "n_months"]].to_string(index=False))
    print(qa.to_string(index=False))
    print(json.dumps(qa_extra, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-download all raw files")
    ap.add_argument("--offline", action="store_true", help="do not download, build from <data dir>/raw only")
    a = ap.parse_args()
    if not a.offline:
        download_all(a.refresh)
    build()


if __name__ == "__main__":
    main()
