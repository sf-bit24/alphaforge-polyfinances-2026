import sys, numpy as np, pandas as pd
sys.path.insert(0, __import__("os").environ.get("BACKTEST_DIR", "research/backtest"))
pd.set_option("display.width", 250)
O = __import__("os").environ.get("CALIB_OUT", "research/calibration/out").rstrip("/") + "/"
g = pd.read_csv(O + "calib_grid5.csv"); hc = pd.read_csv(O + "halfcash_env.csv")
F = ["CAD77_main", "CAD71_USeq", "USD46"]
cols = ["vol", "cvar95_m", "cvar95_12m", "mdd", "y2022", "worst12", "ploss_3y", "ploss_5y", "ploss_10y", "ploss_15y", "uw_max", "rec_m"]
x = g[g.mix.isin(F)].copy(); x["y2022"] = -x.y2022; x["worst12"] = -x.worst12
env = x.groupby("eq")[cols].max()
print("ENV grid5 (main mix):\n", env.round(3).to_string())
h = hc.copy(); h["y2022"] = -h.y2022; h["worst12"] = -h.worst12
print("ENV halfcash:\n", h.groupby("eq")[["vol", "cvar95_m", "cvar95_12m", "mdd", "y2022"]].max().round(3).to_string())
env["k12"] = env.cvar95_12m / env.cvar95_m
print("k = CVaR12m/CVaRm (env):", env.k12.round(2).to_dict(), " sqrt12=", round(12**.5, 2))
# PhD1 separation check
P1 = {"N0": (.10, .03, .025, .05), "N1": (.30, .09, .055, .08), "N2": (.50, .16, .085, .11),
      "N3": (.70, .225, .115, .14), "N4": (.85, .27, .135, .17), "N5": (1.0, .33, .16, .20)}
def emax(col, b):
    ok = env.index[env[col] <= b + 1e-12]; return int(ok.max()) if len(ok) else None
print("\nPhD1: equity max implied by each budget (ENV, main mix)")
for k, (e, cv, vo, s22) in P1.items():
    E = env.loc[int(e * 100)]
    print(k, "e_max", e, "| CVaR12 budget", cv, "env@e", round(E.cvar95_12m, 3), "-> e_ok<=", emax("cvar95_12m", cv),
          "| vol", vo, round(E.vol, 3), "->", emax("vol", vo), "| 2022", s22, round(E.y2022, 3), "->", emax("y2022", s22),
          "| MDD env@e", round(E.mdd, 3))
# PhD1 crash scenario (eq -40, bonds +5, st +3) for its own ref portfolios
for k, (e, a) in {"N1": (.3, .3), "N2": (.5, .5), "N3": (.7, .7), "N4": (.85, .75), "N5": (1, .8)}.items():
    s = 1 - e; print(k, "PhD1 crash-scen loss", round(.4 * e - .05 * a * s - .03 * (1 - a) * s, 3), "hist ENV MDD", round(env.loc[int(e*100)].mdd, 3))
# tails: single names long history
t = pd.read_csv(O + "tails_monthly.csv"); t = t[(t.cur == "CAD")]
tl = t.sort_values("n").groupby("asset").tail(1)
print("\nLong-history CAD MDD by asset:\n", tl[["asset", "start", "mdd", "cvar95_12m", "worst12"]].sort_values("mdd").round(3).to_string(index=False))
sing = ["RY.TO","TD.TO","MFC.TO","ENB.TO","CNQ.TO","CNR.TO","FTS.TO","ATD.TO","SHOP.TO","CSU.TO","AAPL","MSFT","NVDA","GOOGL","AMZN","TSLA","JPM","JNJ","PG","XOM"]
s = tl[tl.asset.isin(sing)].mdd
print("single-name MDD n=%d median %.3f p75 %.3f max %.3f" % (len(s), s.median(), s.quantile(.75), s.max()))
# engine-based checks
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
