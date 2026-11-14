"""Reconciled v0.2 calculator (scratch). Simulation only."""
import math, numpy as np, pandas as pd
from math import log, prod
O = __import__("os").environ.get("CALIB_OUT", "research/calibration/out").rstrip("/") + "/"
g = pd.read_csv(O + "calib_grid5.csv"); hc = pd.read_csv(O + "halfcash_env.csv")
F = ["CAD77_main", "CAD71_USeq", "USD46"]; FH = ["CAD77_hc", "CAD71_hc", "USD46_hc"]
cols = ["vol", "cvar95_m", "cvar95_12m", "mdd", "y2022", "ploss_1y", "ploss_3y", "ploss_5y", "ploss_10y"]
def envof(df, fam):
    x = df[df.mix.isin(fam)].copy(); x["y2022"] = -x.y2022; return x.groupby("eq")[cols].max()
EM, EH = envof(g, F), envof(hc, FH)
def ref(e):  # reference envelope row: half-cash for e<=10 (N0), main mix above
    return EH.loc[e] if e <= 10 else EM.loc[e]
BUF = 0.04
def Lplan(e): return ref(e).mdd + BUF
LV = ["N0", "N1", "N2", "N3", "N4", "N5"]; CUT = [15, 30, 45, 60, 75]
BAND = {"N0": (0, 10), "N1": (10, 25), "N2": (25, 40), "N3": (40, 60), "N4": (60, 80), "N5": (80, 100)}
HCAP = [(1, "N0"), (3, "N1"), (5, "N2"), (10, "N4"), (999, "N5")]   # T < 1 -> N0 ; 1<=T<3 -> N1 ; 3<=T<5 -> N2 ; 5<=T<10 -> N4 ; T>=10 -> N5
def hcap(T):
    if T < 1: return 0
    if T < 3: return 1
    if T < 5: return 2
    if T < 10: return 4
    return 5
up = lambda x, s: math.ceil(round(x / s, 9)) * s
fl = lambda x, s=0.0025: math.floor(round(x / s, 9)) * s
def budgets(e):
    r = ref(e)
    return dict(vol=up(r.vol, .005), cvar_m=up(r.cvar95_m, .001), cvar_12m=up(r.cvar95_12m, .005),
                mdd=up(r.mdd, .005), s2022=up(r.y2022, .005))
if __name__ == "__main__":
    print("LEVEL TABLE (budgets at band e_max)")
    for L, (a, b) in BAND.items():
        print(L, a, b, budgets(b), "L_plan", round(Lplan(b), 3), "ref:", ref(b)[["vol","cvar95_m","cvar95_12m","mdd","y2022"]].round(4).to_dict())
    print("horizon check ploss at e_max (nominal):")
    for L, (a, b) in BAND.items(): print(L, ref(b)[["ploss_1y","ploss_3y","ploss_5y","ploss_10y"]].round(3).to_dict())
