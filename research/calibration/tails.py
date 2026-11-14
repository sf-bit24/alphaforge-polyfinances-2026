"""Tail add-ons: single names, sectors, crypto; daily vs monthly drawdowns. Run like calib.py."""
import os, pathlib
_HERE = pathlib.Path(os.environ.get("CALIB_DIR", pathlib.Path.cwd()))
import numpy as np, pandas as pd, warnings
from engine.data import load_returns
from engine import metrics as M
warnings.filterwarnings("ignore")
OUT = os.environ.get("CALIB_OUT", str(_HERE / "out")) + "/"
ST = os.environ["STARTER_DIR"].rstrip("/") + "/"  # dossier alphaforge_starter (non versionné)


def roll(r, n):
    lg = np.log1p(r); c = np.concatenate([[0.0], np.cumsum(lg)]); return np.expm1(c[n:] - c[:-n])


def cv(x):
    q = np.quantile(x, .05, method="lower"); return -x[x <= q].mean()


def ddinfo(r, idx):
    w = np.cumprod(1 + r); pk = np.maximum.accumulate(np.concatenate([[1.0], w]))[1:]; dd = 1 - w / pk
    t = int(np.argmax(dd)); p = np.where(dd[:t + 1] <= 1e-12)[0]
    return dd[t], (f"{idx[p[-1]]:%Y-%m}" if p.size else "start"), f"{idx[t]:%Y-%m}", M.recovery_months(r)


rows = []
names = ["TSLA", "NVDA", "AAPL", "AMZN", "MSFT", "GOOGL", "JPM", "XOM", "JNJ", "PG", "SHOP.TO", "CSU.TO", "MFC.TO", "RY.TO", "ENB.TO", "CNQ.TO",
         "BTC-USD", "ETH-USD", "US_MKT", "US_IND_BUSEQ", "US_IND_DURBL", "US_IND_ENRGY", "US_IND_MONEY", "US_IND_TELCM", "QQQ", "SPY", "XIU.TO"]
for cur in ["CAD", "USD"]:
    for n in names:
        for s in [None, "2021-12"]:
            try:
                R = load_returns([n], start=s, currency=cur)
            except Exception as e:
                continue
            r = R[n].values; d, p, t, rec = ddinfo(r, R.index); r12 = roll(r, 12)
            rows.append(dict(asset=n, cur=cur, start=f"{R.index[0]:%Y-%m}", end=f"{R.index[-1]:%Y-%m}", n=len(r),
                             vol=M.volatility(r), mdd=d, peak=p, trough=t, rec_m=rec, worst12=r12.min(), cvar95_12m=cv(r12),
                             worst_month=r.min()))
T = pd.DataFrame(rows); T.to_csv(OUT + "tails_monthly.csv", index=False)
pd.set_option("display.width", 250)
print(T.round(3).to_string())

# daily (starter, 2021-11-12..), local currency + CAD
P = pd.read_csv(ST + "prices_daily.csv", parse_dates=["date"]).pivot(index="date", columns="ticker", values="adj_close")
fx = pd.read_csv(ST + "fx_usdcad_daily.csv", parse_dates=["date"]).set_index("date")["usdcad"]
cur = pd.read_csv(ST + "prices_daily.csv", usecols=["ticker", "currency"]).drop_duplicates().set_index("ticker")["currency"]
drows = []
for t in ["TSLA", "NVDA", "BTC-USD", "ETH-USD", "SHOP.TO", "SPY", "QQQ", "XIU.TO", "AGG", "XBB.TO", "TLT", "GLD"]:
    s = P[t].dropna()
    for base in ["local", "CAD"]:
        x = s.copy()
        if base == "CAD" and cur[t] == "USD":
            x = x * fx.reindex(x.index).ffill().bfill()
        dd = 1 - x / x.cummax(); i = dd.idxmax(); pk = x.loc[:i].idxmax()
        m = x.resample("ME").last(); ddm = (1 - m / m.cummax()).max()
        r1 = np.log(x).diff().dropna()
        drows.append(dict(ticker=t, base=base, start=f"{x.index[0]:%Y-%m-%d}", end=f"{x.index[-1]:%Y-%m-%d}",
                          mdd_daily=dd.max(), peak=f"{pk:%Y-%m-%d}", trough=f"{i:%Y-%m-%d}", mdd_monthend=ddm,
                          understate_pp=dd.max() - ddm, worst_day=np.expm1(r1.min())))
D = pd.DataFrame(drows); D.to_csv(OUT + "tails_daily_starter.csv", index=False)
print(D.round(3).to_string())

# weight caps: w such that repeat of worst DD costs <= budget, assuming the rest of the portfolio is flat
print("\nWeight caps w = budget / MDD (rest flat). Uses max(monthly long-history MDD, daily starter MDD)")
ref = {"BTC-USD": None, "ETH-USD": None, "TSLA": None, "NVDA": None, "SHOP.TO": None, "US_IND_BUSEQ": None, "US_IND_DURBL": None}
crow = []
for a in ref:
    m = T[(T.asset == a) & (T.cur == "CAD") & (T.start == T[(T.asset == a) & (T.cur == "CAD")].start.min())].mdd.max()
    dd = D[(D.ticker == a) & (D.base == "CAD")].mdd_daily.max() if a in set(D.ticker) else np.nan
    worst = np.nanmax([m, dd])
    crow.append(dict(asset=a, mdd_monthly_long_CAD=m, mdd_daily_2021_26_CAD=dd, mdd_used=worst,
                     **{f"w_{b}pct": b / 100 / worst for b in [1, 2, 3, 5]}))
W = pd.DataFrame(crow); W.to_csv(OUT + "weight_caps.csv", index=False); print(W.round(3).to_string())
