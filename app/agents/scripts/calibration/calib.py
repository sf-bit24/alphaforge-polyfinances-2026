# ruff: noqa: E402  # script de recherche : sys.path avant les imports, import * voulu
"""AlphaForge risk-band calibration (simulation only). Run:
cd app/agents && CALIB_OUT=/tmp/calib uv run --group finance python scripts/calibration/calib.py
(données longues : python -m alphaforge.finance.backtest.build_data)
Outputs -> $CALIB_OUT (défaut : $CALIB_DIR/out/)
"""

import os
import pathlib

_HERE = pathlib.Path(os.environ.get("CALIB_DIR", pathlib.Path.cwd()))
import json
import warnings

import numpy as np
import pandas as pd

from alphaforge.finance.backtest import metrics as M
from alphaforge.finance.backtest.data import data_version, load_inflation, load_returns
from alphaforge.finance.backtest.windows import windows

warnings.filterwarnings("ignore")
OUT = os.environ.get("CALIB_OUT", str(_HERE / "out")) + "/"
EQ = list(range(0, 101, 10))
HZ = [1, 3, 5, 10, 15]


def rebal(R, w, freq="M"):
    """Static mix. freq M = monthly rebalance (r = w.r); A = annual (rebalance each December-end), drift otherwise."""
    w = pd.Series(w, dtype=float)
    X = R[w.index]
    if freq == "M":
        return X.values @ w.values
    out, cur = [], w.values.copy()
    for d, row in zip(X.index, X.values, strict=False):
        g = cur * (1 + row)
        rp = g.sum() / cur.sum() - 1
        out.append(rp)
        cur = g / g.sum()
        if d.month == 12:
            cur = w.values.copy()
    return np.array(out)


def dd_info(r, idx):
    w = np.cumprod(1 + r)
    peak = np.maximum.accumulate(np.concatenate([[1.0], w]))[1:]
    dd = 1 - w / peak
    t = int(np.argmax(dd))
    pk = np.where(dd[: t + 1] <= 1e-12)[0]
    pk_i = pk[-1] if pk.size else -1
    return dict(
        mdd=float(dd[t]),
        trough=f"{idx[t]:%Y-%m}",
        peak=(f"{idx[pk_i]:%Y-%m}" if pk_i >= 0 else "start"),
        rec_m=M.recovery_months(r),
        uw_max=M.max_underwater_months(r),
    )


def roll(r, n):
    lg = np.log1p(r)
    c = np.concatenate([[0.0], np.cumsum(lg)])
    return np.expm1(c[n:] - c[:-n])


def var_cvar(x, a=0.05):
    q = np.quantile(x, a, method="lower")
    return float(-q), float(-x[x <= q].mean())


def episode(r, idx, s, e):
    m = (idx >= pd.Timestamp(s)) & (idx <= pd.Timestamp(e) + pd.offsets.MonthEnd(0))
    if m.sum() == 0 or idx[0] > pd.Timestamp(s):
        return np.nan
    return M.max_drawdown(r[m])


def cal_year(r, idx, y):
    m = idx.year == y
    return float(np.prod(1 + r[m]) - 1) if m.sum() == 12 else np.nan


def stats(name, e, r, idx, infl):
    rr = M.real_returns(r, infl)
    d = dd_info(r, idx)
    dr = dd_info(rr, idx)
    r12, rr12 = roll(r, 12), roll(rr, 12)
    v12, c12 = var_cvar(r12)
    vm, cm = var_cvar(r)
    v12r, c12r = var_cvar(rr12)
    row = dict(
        mix=name,
        eq=e,
        start=f"{idx[0]:%Y-%m}",
        end=f"{idx[-1]:%Y-%m}",
        n=len(r),
        ann=M.annualized_return(r),
        ann_real=M.annualized_return(rr),
        vol=M.volatility(r),
        mdd=d["mdd"],
        mdd_peak=d["peak"],
        mdd_trough=d["trough"],
        rec_m=d["rec_m"],
        uw_max=d["uw_max"],
        mdd_real=dr["mdd"],
        mdd_real_trough=dr["trough"],
        rec_real_m=dr["rec_m"],
        uw_real_max=dr["uw_max"],
        var95_m=vm,
        cvar95_m=cm,
        var95_12m=v12,
        cvar95_12m=c12,
        var95_12m_real=v12r,
        cvar95_12m_real=c12r,
        worst12=float(r12.min()),
        worst12_real=float(rr12.min()),
        y2022=cal_year(r, idx, 2022),
        y2022_real=cal_year(rr, idx, 2022),
        y2008=cal_year(r, idx, 2008),
        dd_1973_74=episode(r, idx, "1973-01", "1974-12"),
        dd_2000_02=episode(r, idx, "2000-01", "2002-12"),
        dd_gfc=episode(r, idx, "2007-06", "2009-06"),
        dd_2020=episode(r, idx, "2020-01", "2020-06"),
        dd_2022=episode(r, idx, "2021-11", "2023-10"),
        dd_1929_32=episode(r, idx, "1929-08", "1932-06"),
    )
    for h in HZ:
        n = 12 * h
        if len(r) < n:
            continue
        a, b = roll(r, n), roll(rr, n)
        row[f"ploss_{h}y"] = float((a < 0).mean())
        row[f"ploss_real_{h}y"] = float((b < 0).mean())
        row[f"nwin_{h}y"] = len(a)
        row[f"nnonov_{h}y"] = len(windows(h, idx[0], idx[-1], index=idx))
        row[f"worst_{h}y_ann"] = float((1 + a.min()) ** (1 / h) - 1)
        row[f"worst_real_{h}y_ann"] = float((1 + b.min()) ** (1 / h) - 1)
    return row


def run_family(name, assets, eq_w, fi_w, start, cur, freq="M", gold=0.0, end=None, fx_fill="none"):
    R = load_returns(assets, start=start, end=end, currency=cur, fx_fill=fx_fill)
    infl = load_inflation(cur).reindex(R.index)
    ok = infl.notna()
    R = R[ok]
    infl = infl[ok]
    rows = []
    for e in EQ:
        f = e / 100
        w = {}
        for k, v in eq_w.items():
            w[k] = w.get(k, 0) + f * v
        rest = 1 - f - gold
        if rest < -1e-9:
            continue
        for k, v in fi_w.items():
            w[k] = w.get(k, 0) + max(rest, 0) * v
        if gold:
            w["GOLD"] = gold
        r = rebal(R, w, freq)
        rows.append(stats(name, e, r, R.index, infl.values))
    return rows, R.attrs["info"]


FAM = {
    # main: Canadian investor, 1977+, eq = 50/50 CA_EQ/US_MKT(CAD), FI = 75% CA_GOV_10Y + 25% CA_TBILL
    "CAD77_main": (
        ["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL"],
        {"CA_EQ": 0.5, "US_MKT": 0.5},
        {"CA_GOV_10Y": 0.75, "CA_TBILL": 0.25},
        "1977-01",
        "CAD",
        "M",
        0.0,
    ),
    "CAD77_annual": (
        ["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL"],
        {"CA_EQ": 0.5, "US_MKT": 0.5},
        {"CA_GOV_10Y": 0.75, "CA_TBILL": 0.25},
        "1977-01",
        "CAD",
        "A",
        0.0,
    ),
    "CAD77_allbond": (
        ["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL"],
        {"CA_EQ": 0.5, "US_MKT": 0.5},
        {"CA_GOV_10Y": 1.0},
        "1977-01",
        "CAD",
        "M",
        0.0,
    ),
    "CAD77_halfcash": (
        ["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL"],
        {"CA_EQ": 0.5, "US_MKT": 0.5},
        {"CA_GOV_10Y": 0.5, "CA_TBILL": 0.5},
        "1977-01",
        "CAD",
        "M",
        0.0,
    ),
    "CAD77_gold5": (
        ["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL", "GOLD"],
        {"CA_EQ": 0.5, "US_MKT": 0.5},
        {"CA_GOV_10Y": 0.75, "CA_TBILL": 0.25},
        "1977-01",
        "CAD",
        "M",
        0.05,
    ),
    # Canadian investor with US equity only, 1971-02+ (covers 1973-74 in CAD)
    "CAD71_USeq": (
        ["US_MKT", "CA_GOV_10Y", "CA_TBILL"],
        {"US_MKT": 1.0},
        {"CA_GOV_10Y": 0.75, "CA_TBILL": 0.25},
        "1971-02",
        "CAD",
        "M",
        0.0,
    ),
    # US investor, USD, 1926+, FI = 75% UST_5Y + 25% T-bill
    "USD26": (
        ["US_MKT", "UST_5Y", "UST_TBILL"],
        {"US_MKT": 1.0},
        {"UST_5Y": 0.75, "UST_TBILL": 0.25},
        "1926-08",
        "USD",
        "M",
        0.0,
    ),
    "USD26_10y": (
        ["US_MKT", "UST_10Y", "UST_TBILL"],
        {"US_MKT": 1.0},
        {"UST_10Y": 0.75, "UST_TBILL": 0.25},
        "1926-08",
        "USD",
        "M",
        0.0,
    ),
    # same US mix, post-war only (excludes 1929-32)
    "USD46": (
        ["US_MKT", "UST_5Y", "UST_TBILL"],
        {"US_MKT": 1.0},
        {"UST_5Y": 0.75, "UST_TBILL": 0.25},
        "1946-01",
        "USD",
        "M",
        0.0,
    ),
    # recent-only window used by the team (2021-2026), for comparison
    "CAD21_recent": (
        ["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL"],
        {"CA_EQ": 0.5, "US_MKT": 0.5},
        {"CA_GOV_10Y": 0.75, "CA_TBILL": 0.25},
        "2021-01",
        "CAD",
        "M",
        0.0,
    ),
}

if __name__ == "__main__":
    allrows, infos = [], {}
    for k, (assets, eq, fi, s, cur, fq, g) in FAM.items():
        rows, info = run_family(k, assets, eq, fi, s, cur, fq, g)
        allrows += rows
        infos[k] = info
    df = pd.DataFrame(allrows)
    df.to_csv(OUT + "calib_all.csv", index=False)
    json.dump(
        {"data_version": data_version(), "load_info": infos}, open(OUT + "calib_meta.json", "w"), indent=1, default=str
    )
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 60)
    for k in FAM:
        d = df[df.mix == k].set_index("eq")
        print("\n===", k, d.start.iloc[0], d.end.iloc[0], "n=", d.n.iloc[0])
        print(
            d[
                [
                    "ann",
                    "ann_real",
                    "vol",
                    "mdd",
                    "mdd_peak",
                    "mdd_trough",
                    "rec_m",
                    "uw_max",
                    "mdd_real",
                    "uw_real_max",
                    "cvar95_m",
                    "var95_12m",
                    "cvar95_12m",
                    "cvar95_12m_real",
                    "worst12",
                    "worst12_real",
                ]
            ]
            .round(3)
            .to_string()
        )
        print(
            d[
                [
                    "y2022",
                    "y2022_real",
                    "y2008",
                    "dd_gfc",
                    "dd_2000_02",
                    "dd_1973_74",
                    "dd_1929_32",
                    "dd_2020",
                    "dd_2022",
                ]
            ]
            .round(3)
            .to_string()
        )
        pc = [c for c in d.columns if c.startswith("ploss") or c.startswith("nnonov")]
        print(d[pc].round(3).to_string())
