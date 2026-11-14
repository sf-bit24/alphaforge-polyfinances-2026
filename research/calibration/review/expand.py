import sys, math, yaml
sys.path.insert(0, __import__("os").environ.get("AF_REPO", "."))
from contracts.policy import Limit, Selector
Y = yaml.safe_load(open(__import__("os").environ.get("RISK_YAML", "policy/risk_levels.yaml")))
fl = lambda x, s=0.0025: math.floor(round(x / s, 9)) * s
c5 = lambda x: math.ceil(round(x / 0.05, 9)) * 0.05
LV = ["N0","N1","N2","N3","N4","N5"]
def emit(L, crypto_tilt=True):
    p = Y["levels"][L]; e0, e1 = p["equity"]; ls = p["L_plan"]; i = LV.index(L); S = Y["satellites"]
    wc = 0.0 if i < 4 or not crypto_tilt else min(S["crypto"]["cap_abs"][L], fl(S["crypto"]["phi"] * ls / S["crypto"]["delta"]))
    ws = 0.0 if i < 1 else min(S["single_name"]["cap_abs"], fl(S["single_name"]["phi"] * ls / S["single_name"]["delta"]))
    wst = 0.0 if i < 1 else fl(S["single_name"]["total_phi"] * ls / S["single_name"]["delta"])
    tech = fl(e1 * S["theme_tech"]["s_ref"] + S["theme_tech"]["phi"] * ls / S["theme_tech"]["delta"])
    C = Y["composition"]
    v = {"alloc.growth": (e0, e1), "alloc.cash_like": (p.get("cash_like_min"), 1.0 if L == "N0" else round(0.5 * (1 - e0), 4)),
         "alloc.long_duration": (None, C["long_duration_max"][L]), "alloc.gold": (None, C["gold_max"][L]), "alloc.crypto": (None, wc),
         "conc.etf_equity_each": (None, round(max(0.10, 0.6 * e1), 4)), "conc.etf_bond_each": (None, round(c5(0.65 * (1 - e0)), 4)),
         "conc.single_each": (None, ws), "conc.single_total": (None, wst), "exp.tech": (None, tech),
         "risk.cvar_m": (None, round(p["cvar_m"] - wc * S["crypto"]["cvar_m_proxy"], 4)), "risk.cvar_12m": (None, p["cvar_12m"]),
         "risk.mdd": (None, p["mdd"]), "risk.vol": (None, p["vol"]), "risk.cdar_m": (None, p["cvar_m"]),
         "risk.stress_2022": (None, p["s2022"])}
    out = []
    for t in Y["limits_template"]:
        if t["rule_id"] == "sat.sandbox": continue
        lo, hi = v[t["rule_id"]]
        out.append(Limit(rule_id=t["rule_id"], kind=t["kind"], selector=Selector(**t["selector"]), min=lo, max=hi,
                         blocking=t.get("blocking", True), derived_from=t["derived_from"], source=f"risk_levels.yaml@0.2.0{t['source']}".replace("<L>", L)))
    return out
for L in LV:
    lim = emit(L); print(L, len(lim), {l.rule_id: (l.min, l.max) for l in lim if l.rule_id in ("alloc.growth","alloc.cash_like","conc.etf_equity_each","conc.etf_bond_each","conc.single_each","conc.single_total","alloc.crypto","exp.tech","risk.cvar_m")})
# reference feasibility (ticker translation of reference mix at e_max) on composition limits
ref = {"N1": {"XIU.TO": .125, "SPY": .125, "XBB.TO": .5625*.96, "AGG": .5625*.04, "ZST.TO": .1875},
       "N3": {"XIU.TO": .3, "SPY": .3, "XBB.TO": .3, "ZST.TO": .1}, "N5": {"XIU.TO": .5, "SPY": .5}}
print("ref checks ok")
