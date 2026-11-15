# ruff: noqa: E402  # script de recherche : sys.path avant les imports, import * voulu
"""Envelope table (5% equity grid), worst-12m dates, stock-bond correlations. Run like calib.py.
Reuses calib.py from $CALIB_DIR (loaded by path because -I disables script-dir imports)."""

import os
import pathlib

_HERE = pathlib.Path(os.environ.get("CALIB_DIR", pathlib.Path.cwd()))
import importlib.util

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("calib", str(_HERE / "calib.py"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
from alphaforge.finance.backtest.data import load_returns

C.EQ = list(range(0, 101, 5))
fams = ["CAD77_main", "CAD71_USeq", "USD46", "USD26"]
rows = []
for k in fams:
    a, eq, fi, s, cur, fq, g = C.FAM[k]
    rows += C.run_family(k, a, eq, fi, s, cur, fq, g)[0]
df = pd.DataFrame(rows)
df.to_csv(C.OUT + "calib_grid5.csv", index=False)
cols = [
    "vol",
    "mdd",
    "rec_m",
    "uw_max",
    "mdd_real",
    "cvar95_12m",
    "cvar95_12m_real",
    "worst12",
    "y2022",
    "ploss_1y",
    "ploss_3y",
    "ploss_5y",
    "ploss_10y",
    "ploss_real_1y",
    "ploss_real_3y",
    "ploss_real_5y",
    "ploss_real_10y",
    "ploss_real_15y",
]
env = df[df.mix.isin(["CAD77_main", "CAD71_USeq", "USD46"])].copy()
env["worst12"] = -env["worst12"]
env["y2022"] = -env["y2022"]
E = env.groupby("eq")[cols].max()
E.columns = [c + "_env" for c in cols]
E.to_csv(C.OUT + "envelope_grid5.csv")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
print(
    "ENVELOPE = max over CAD77_main(CAD,1977-2026), CAD71_USeq(CAD,1971-2026), USD46(USD,1946-2026); worst12/y2022 as positive loss"  # noqa: E501
)
print(E.round(3).to_string())
print("\nUSD26 (incl. 1929-32) for reference")
print(
    df[df.mix == "USD26"]
    .set_index("eq")[["vol", "mdd", "rec_m", "uw_max", "cvar95_12m", "worst12"]]
    .round(3)
    .to_string()
)
print("\nCAD77_main 5% grid")
print(
    df[df.mix == "CAD77_main"]
    .set_index("eq")[["vol", "mdd", "rec_m", "uw_max", "cvar95_12m", "worst12", "y2022"]]
    .round(3)
    .to_string()
)

# worst 12m end dates
for k, e in [
    ("CAD77_main", 0),
    ("CAD77_main", 20),
    ("CAD77_main", 50),
    ("CAD77_main", 100),
    ("CAD71_USeq", 0),
    ("CAD71_USeq", 100),
    ("USD46", 0),
    ("USD46", 20),
]:
    a, eq, fi, s, cur, fq, g = C.FAM[k]
    R = load_returns(a, start=s, currency=cur)
    f = e / 100
    w = {x: f * v for x, v in eq.items()}
    for x, v in fi.items():
        w[x] = w.get(x, 0) + (1 - f) * v
    r = C.rebal(R, w)
    r12 = C.roll(r, 12)
    i = int(np.argmin(r12))
    print(f"worst12 {k} e={e}: {r12[i]:.3f} ending {R.index[i + 11]:%Y-%m}")

# stock-bond correlations
R = load_returns(["US_MKT", "UST_10Y"], start="1926-08", currency="USD")
Rc = load_returns(["CA_EQ", "CA_GOV_10Y"], start="1977-01", currency="CAD")
print("\nCorrelation of monthly returns by period")
for s, e in [
    ("1926", "1945"),
    ("1946", "1965"),
    ("1966", "1999"),
    ("2000", "2020"),
    ("2021", "2026"),
    ("2022", "2022"),
]:
    a = R.loc[s:e]
    b = Rc.loc[s:e]
    cb = b.corr().iloc[0, 1] if len(b) > 6 else np.nan
    print(f"{s}-{e}: US_MKT~UST_10Y {a.corr().iloc[0, 1]:+.2f}  CA_EQ~CA_GOV_10Y {cb:+.2f}")
rc = R["US_MKT"].rolling(36).corr(R["UST_10Y"])
print(
    "rolling36 US corr min/max:",
    round(rc.min(), 2),
    f"{rc.idxmin():%Y-%m}",
    round(rc.max(), 2),
    f"{rc.idxmax():%Y-%m}",
    "last",
    round(rc.iloc[-1], 2),
)
