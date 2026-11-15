import sys, numpy as np
sys.path.insert(0, __import__("os").environ.get("BACKTEST_DIR", "research/backtest"))
from engine.data import load_returns
def roll(r, n):
    c = np.concatenate([[0.0], np.cumsum(np.log1p(r))]); return np.expm1(c[n:] - c[:-n])
def cv(x, a=.05):
    q = np.quantile(x, a, method="lower"); return -x[x <= q].mean()
R = load_returns(["US_MKT", "CA_GOV_10Y", "CA_TBILL", "GOLD", "UST_20Y", "UST_5Y"], start="1971-02", currency="CAD")
print(R.index[0], R.index[-1], len(R))
for w in [{"US_MKT": .6, "CA_GOV_10Y": .4}, {"US_MKT": 1.0}, {"US_MKT": .6, "CA_GOV_10Y": .3, "CA_TBILL": .1}]:
    r = R[list(w)].values @ np.array(list(w.values()))
    print(w, "CVaR95_12m %.4f  CVaR95_m %.4f" % (cv(roll(r, 12)), cv(r)))
for a in ["GOLD","UST_20Y","UST_5Y","CA_GOV_10Y"]:
    r=R[a].values; w=np.cumprod(1+r); dd=1-w/np.maximum.accumulate(w); print(a,"MDD %.3f CVaR12 %.3f y2022 %.3f"%(dd.max(),cv(roll(r,12)),np.prod(1+R[a].loc['2022'].values)-1))
