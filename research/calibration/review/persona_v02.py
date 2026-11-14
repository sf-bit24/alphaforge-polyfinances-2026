import sys; sys.path.insert(0, __import__("os").environ.get("REVIEW_DIR", "research/calibration/review"))
import math
from math import log, prod
from v02 import *
def clip(x, a=0, b=1): return max(a, min(b, x))
def cH(T): return clip(log(T / 2) / log(7.5)) if T > 0 else 0
def capacity(T, E, Ereq, q, qmax, cI, nm_debt, inc, mu, phi=0.8):   # PhD1 persona.py, unchanged
    cE = clip(E / Ereq); cD = clip(1 - phi * q / qmax); cL = clip(1 - nm_debt / inc) if inc else 0.5
    lcap = min(1 - q / qmax, 1 - (1 + mu) ** (-T)); cA = clip(lcap / 0.40)
    c = dict(H=cH(T), A=cA, E=cE, D=cD, I=cI, L=cL); w = dict(H=.3, A=.2, E=.15, D=.15, I=.1, L=.1)
    return 100 * prod(max(c[k], 0.05) ** w[k] for k in c), lcap
def tol(Dv, kD, X, kX, Cp, wD=1, wX=2, T0=25):                       # PhD1 persona.py, unchanged
    Tb = (wD * kD * Dv + wX * kX * X) / (wD * kD + wX * kX); beta = clip((abs(Dv - X) - 10) / 30)
    T1 = (1 - beta) * Tb + beta * min(Dv, X); k = 1 - (1 - kD) * (1 - kX); T2 = T1 - (1 - k) * max(0, T1 - T0)
    return T2 - 0.5 * max(0, T2 - (Cp + 15)) if Cp is not None else T2 - 5
def lvl(R): return sum(R >= c for c in CUT)
GRID = [0, 5, 10] + list(range(15, 101, 5))
def run(name, T, cap_args, tol_args, l_decl, W, M, tilt_crypto, sandbox_req, buf=BUF, knowledge="intermediaire"):
    C, lcap = capacity(T, *cap_args); T3 = tol(*tol_args); R = min(T3, C)
    L0 = min(lvl(R), hcap(T)); emax = BAND[LV[L0]][1]
    Lp = lambda e: ref(e).mdd + buf
    lstar = min(Lp(emax), l_decl if l_decl is not None else 9, lcap)
    ok = [e for e in GRID if e <= emax and Lp(e) <= lstar + 1e-12]
    ecap = max(ok) if ok else None
    if ecap is None: return print(name, "PROTECTION: l* < perte du niveau le plus prudent", round(lstar, 3))
    L = next(i for i, l in enumerate(LV) if BAND[l][0] < ecap <= BAND[l][1]) if ecap > 0 else 0
    L = min(L, L0); lv = LV[L]
    b = budgets(ecap)
    crypto = 0 if (L < 4 or not tilt_crypto) else min({4: .02, 5: .025}[L], fl(.04 * lstar / .90))
    single = 0 if L < 1 else min(.05, fl(.10 * lstar / .80))
    sandbox = 0 if L < 1 else min(.03, fl(.05 * lstar / .90), fl(3 * M / W) if W else 0)
    if knowledge == "debutant": crypto, sandbox, single = fl(crypto / 2), fl(sandbox / 2), min(single, .02)
    tech = fl(min(ecap, BAND[lv][1]) / 100 * .44 + .10 * lstar / .80, .005)
    print(f"{name}: C={C:.1f} T3={T3:.1f} R={R:.1f} -> level R {LV[lvl(R)]}, horizon cap {LV[hcap(T)]}, l*={lstar:.3f} "
          f"(decl {l_decl}, l_cap {lcap:.3f}) -> e_cap={ecap}% => {lv} band {BAND[lv]} budgets {b} "
          f"| crypto {crypto:.4f} single/name {single:.4f} sandbox {sandbox:.4f} (= {sandbox*W:,.0f}$ vs requested {sandbox_req:,.0f}$) tech_LT<= {tech:.3f}")
# HYPOTHESE inputs: PhD1 persona.py ; W, M, declared loss: HYPOTHESE (not in persona.py), chosen to reproduce PhD1's l*
for buf in (0.04, 0.0):
    print(f"\n=== daily buffer {buf}")
    BUFX = buf
    run("Amira", 20, (4, 3, 0, .045, 1.0, 12000, 95000, .04), (80, .7, 72, .8, 60), None, 150000, 4000, True, 0, buf)
    run("Amira decl35", 20, (4, 3, 0, .045, 1.0, 12000, 95000, .04), (80, .7, 72, .8, 60), .35, 150000, 4000, True, 0, buf)
    run("Mateo(indiv)", 9, (5, 3, 0, .045, 1.0, 18000, 160000, .04), (55, .7, 50, .8, 55), .25, 400000, 9000, False, 0, buf)
    run("Mateo(menage=min)", 9, (5, 3, 0, .045, 1.0, 18000, 160000, .04), (45, .6, 48, .7, 50), .25, 400000, 9000, False, 0, buf)
    run("Robert", 7, (8, 6, 30000 / 900000, .045, .3 + .7 * 3400 / 6500, 0, 140000, .04), (35, .7, 52, .6, 30), .133, 900000, 6500, False, 50000, buf)
    run("Robert decl20", 7, (8, 6, 30000 / 900000, .045, .3 + .7 * 3400 / 6500, 0, 140000, .04), (35, .7, 52, .6, 30), .20, 900000, 6500, False, 50000, buf)
