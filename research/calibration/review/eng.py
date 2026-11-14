import sys, numpy as np, pandas as pd
sys.path.insert(0, __import__("os").environ.get("BACKTEST_DIR", "research/backtest"))
from engine.data import load_returns
def roll(r, n):
    c = np.concatenate([[0.0], np.cumsum(np.log1p(r))]); return np.expm1(c[n:] - c[:-n])
def cv(x, a=.05):
    q = np.quantile(x, a, method="lower"); return -x[x <= q].mean()
R = load_returns(["US_MKT", "CA_GOV_10Y", "CA_EQ", "CA_TBILL"], start="1971-02", currency="CAD")
for w in [{"US_MKT": .6, "CA_GOV_10Y": .4}, {"US_MKT": 1.0}]:
    r = R.dropna(subset=list(w))[list(w)].values @ np.array(list(w.values()))
    print("sanity", w, "CVaR95_12m", round(cv(roll(r, 12)), 4), "CVaR95_m", round(cv(r), 4), "n", len(r))
# block bootstrap CI of 12m CVaR (CAD77 main e=60)
R2 = load_returns(["CA_EQ", "US_MKT", "CA_GOV_10Y", "CA_TBILL"], start="1977-01", currency="CAD")
w = np.array([.3, .3, .3, .1]); r = R2.values @ w
rng = np.random.default_rng(0); B = 2000; L = 24; n = len(r); out = []; outm = []
for _ in range(B):
    idx = []
    while len(idx) < n:
        s0 = rng.integers(0, n); idx += [(s0 + j) % n for j in range(L)]
    rb = r[idx[:n]]; out.append(cv(roll(rb, 12))); outm.append(cv(rb))
print("CAD77 e60 CVaR12 point", round(cv(roll(r, 12)), 3), "boot 5-95%", np.round(np.quantile(out, [.05, .5, .95]), 3),
      "| CVaRm point", round(cv(r), 4), "boot", np.round(np.quantile(outm, [.05, .5, .95]), 4))
# 10y lookback (2016-10..2026-09) monthly CVaR vs long: the optimizer default lookback
rr = r[-120:]; print("CAD77 e60 CVaRm last120m", round(cv(rr), 4), "vs full", round(cv(r), 4))
r100 = R2[["CA_EQ", "US_MKT"]].values @ np.array([.5, .5]); print("e100 CVaRm last120m", round(cv(r100[-120:]), 4), "full", round(cv(r100), 4))
