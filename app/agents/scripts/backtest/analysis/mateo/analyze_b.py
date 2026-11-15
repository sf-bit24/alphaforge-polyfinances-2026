"""Stage B analysis: per-window tables, robust choice, walk-forward, ESG cost, tech drift / cap, reverse engineering.
Only reads engine traces (runs_B_*.json) + signals.py; writes results/mateo_analysis/*.csv and stageB_summary.json
(each entry keeps the trace path it comes from). SIMULATION ONLY."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402,F401  (data_ext + look-through wrapper for exposure_vector)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

import lib  # noqa: E402
import signals  # noqa: E402
from alphaforge.finance.backtest.constraints import exposure_vector  # noqa: E402  (patched in engine.constraints namespace)
import alphaforge.finance.backtest.constraints as EC  # noqa: E402
from alphaforge.finance.backtest.validation import robust_table  # noqa: E402

ERAS = ["usd_long", "usd_gold", "cad"]
pd.set_option("display.width", 260, "display.max_columns", 40, "display.max_rows", 400)
F = lambda x: f"{x:.4f}"  # noqa: E731
S = {}


def tech_of(weights: dict, date) -> float:
    a = list(weights)
    v = EC.exposure_vector(a, "tech", date=date)
    return float(np.dot(v, [weights[k] for k in a]))


def per_window(era, var, mode="non_overlapping", h=10):
    tp = lib.trace_path(f"mateo_{era}_{var}", mode, h, "1")
    if not tp:
        return None, None
    df = lib.rows(tp)
    ex = df[~df.hindsight]
    orc = df[df.hindsight].set_index("window")
    out = []
    for wdw, g in ex.groupby("window", sort=False):
        b = g.loc[g.score.idxmax()]
        o = orc.loc[wdw]
        gw = lib.grouped_weights(o["avg_weights"])
        top = sorted(((k, v) for k, v in o["avg_weights"].items() if v > 0.02), key=lambda x: -x[1])
        start = pd.Timestamp(o["start"])
        out.append({"window": wdw, "oracle_real": o["ann_real_return"], "oracle_vol": o["volatility"],
                    "oracle_maxdd": o["max_drawdown"], "oracle_cvar5": o["cvar_5"], "oracle_recovery_m": o["recovery_months"],
                    "oracle_equity": gw["equity_total"], "oracle_bonds": gw["bonds_total"], "oracle_gold": gw.get("gold", 0),
                    "oracle_cash": gw.get("cash", 0), "oracle_long_dur": gw["duration_long_share"],
                    "oracle_tech": tech_of(o["avg_weights"], start - pd.offsets.MonthEnd(1)),
                    "oracle_top": "; ".join(f"{k} {v:.2f}" for k, v in top[:5]),
                    "best_exante": b["strategy"], "best_real": b["ann_real_return"], "best_vol": b["volatility"],
                    "best_maxdd": b["max_drawdown"], "best_cvar5": b["cvar_5"], "best_recovery_m": b["recovery_months"],
                    "best_missed": b["missed_target"], "oracle_gap": o["score"] - b["score"]})
    return pd.DataFrame(out), tp


def robust(era, var, mode="rolling", h=10, mbr=None):
    tp = lib.trace_path(f"mateo_{era}_{var}", mode, h)
    if not tp:
        return None, None
    df = lib.rows(tp)
    return robust_table(df, 0.10, mbr), tp


def walkforward(tp):
    t = lib.load(tp)
    return pd.DataFrame(t["walk_forward"]), t["summary"]


def main():
    W = {}
    print("=" * 30, "PER WINDOW (non-overlapping h10)")
    for era in ERAS:
        for var in ["base", "esg"] + (["esgstrict"] if era == "cad" else []):
            d, tp = per_window(era, var)
            if d is None:
                continue
            d.insert(0, "era", era); d.insert(1, "variant", var); d["trace"] = tp
            W[(era, var)] = d
            print(f"\n-- {era} {var}  [{tp}]")
            print(d.drop(columns=["trace", "era", "variant"]).to_string(index=False, float_format=F))
    if W:
        pd.concat(W.values()).to_csv(lib.OUT / "per_window_h10.csv", index=False)

    print("=" * 30, "ROBUST SELECTION")
    R = {}
    for era in ERAS:
        for var in ["base", "esg"] + (["esgstrict"] if era == "cad" else []):
            for mode, h in [("rolling", 10), ("non_overlapping", 10), ("non_overlapping", 8), ("non_overlapping", 12),
                            ("rolling", 8), ("rolling", 12)]:
                for mbr in (None, 0.25, 0.5):
                    t, tp = robust(era, var, mode, h, mbr)
                    if t is None:
                        continue
                    t = t.reset_index()
                    t.insert(0, "era", era); t.insert(1, "variant", var); t.insert(2, "mode", mode); t.insert(3, "h", h)
                    t.insert(4, "max_breach_rate", mbr); t["trace"] = tp
                    R[(era, var, mode, h, mbr)] = t
                    if (mode, h) in [("rolling", 10), ("non_overlapping", 10)]:
                        print(f"\n-- {era} {var} {mode} h{h} max_breach_rate={mbr} [{tp}]")
                        print(t.head(6)[["strategy", "n_windows", "score_p10", "score_median", "score_worst",
                                         "max_drawdown_worst", "breach_rate", "shortfall_prob", "eligible"]].to_string(index=False, float_format=F))
    if R:
        pd.concat(R.values()).to_csv(lib.OUT / "robust_all.csv", index=False)

    print("=" * 30, "WALK-FORWARD (rolling h10 and non-overlapping h10)")
    WF = []
    for era in ERAS:
        for var in ["base", "esg"] + (["esgstrict"] if era == "cad" else []):
            for mode in ("rolling", "non_overlapping"):
                tp = lib.trace_path(f"mateo_{era}_{var}", mode, 10, "1")
                if not tp:
                    continue
                wf, summ = walkforward(tp)
                if len(wf):
                    WF.append({"era": era, "variant": var, "mode": mode, **summ["walk_forward"],
                               "most_chosen": wf["chosen"].value_counts().head(3).to_dict(), "trace": tp})
    WF = pd.DataFrame(WF)
    print(WF.to_string(index=False, float_format=F))
    WF.to_csv(lib.OUT / "walkforward_summary.csv", index=False)


def esg_cost():
    """Paired base vs esg per window and strategy (same windows, same strategies)."""
    print("=" * 30, "ESG COST (esg - base, paired by window x strategy)")
    recs = []
    for era in ERAS:
        for var in (["esg"] + (["esgstrict"] if era == "cad" else [])):
            for prof_suffix in ("", "_classes"):
                for mode in ("rolling", "non_overlapping"):
                    tb = lib.trace_path(f"mateo_{era}_base{prof_suffix}", mode, 10, "1")
                    te = lib.trace_path(f"mateo_{era}_{var}{prof_suffix}", mode, 10, "1")
                    if not (tb and te):
                        continue
                    b, e = lib.rows(tb), lib.rows(te)
                    m = b.merge(e, on=["window", "strategy"], suffixes=("_b", "_e"))
                    for strat in ["ORACLE", "static_eq60", "glide_delay5y_70_40", "trend10_policy", "min_variance_60",
                                  "mean_var_60_ra4", "sector_mom12_top3", "dual_mom12_top2", "risk_parity_iv36"]:
                        g = m[m.strategy == strat]
                        if g.empty:
                            continue
                        d = g.ann_real_return_e - g.ann_real_return_b
                        recs.append({"era": era, "variant": var, "universe": "classes" if prof_suffix else "sectors",
                                     "mode": mode, "strategy": strat, "n": len(g),
                                     "real_diff_median": d.median(), "real_diff_p10": d.quantile(0.1),
                                     "real_diff_worst": d.min(), "real_diff_mean": d.mean(),
                                     "p10_level_base": g.ann_real_return_b.quantile(0.1), "p10_level_esg": g.ann_real_return_e.quantile(0.1),
                                     "vol_diff_median": (g.volatility_e - g.volatility_b).median(),
                                     "maxdd_diff_median": (g.max_drawdown_e - g.max_drawdown_b).median(),
                                     "maxdd_worst_base": g.max_drawdown_b.max(), "maxdd_worst_esg": g.max_drawdown_e.max(),
                                     "shortfall_base": g.missed_target_b.astype(float).mean(),
                                     "shortfall_esg": g.missed_target_e.astype(float).mean(),
                                     "trace_base": tb, "trace_esg": te})
    D = pd.DataFrame(recs)
    D.to_csv(lib.OUT / "esg_cost.csv", index=False)
    print(D.drop(columns=["trace_base", "trace_esg"]).to_string(index=False, float_format=F))
    return D


def tech():
    print("=" * 30, "TECH LOOK-THROUGH (avg weights x exposure at window start) and TECH CAP GRID")
    recs = []
    for era in ERAS:
        for var in ("base", "esg"):
            for cap in [None, 35, 30, 25, 20]:
                pid = f"mateo_{era}_{var}" + (f"_tc{cap}" if cap else "")
                for mode in ("rolling", "non_overlapping"):
                    tp = lib.trace_path(pid, mode, 10)
                    if not tp:
                        continue
                    df = lib.rows(tp)
                    df["tech"] = [tech_of(w, pd.Timestamp(st) - pd.offsets.MonthEnd(1)) for w, st in zip(df.avg_weights, df.start)]
                    ex = df[~df.hindsight]
                    rt = robust_table(df, 0.10, None)
                    best = rt.index[0]
                    orc = df[df.hindsight]
                    rec = {"era": era, "variant": var, "tech_cap": cap / 100 if cap else None, "mode": mode,
                           "robust_choice": best, "robust_p10": rt.iloc[0]["score_p10"],
                           "robust_median": rt.iloc[0]["score_median"], "robust_maxdd_worst": rt.iloc[0]["max_drawdown_worst"],
                           "tech_avg_all_exante": ex.tech.mean(), "tech_max_all_exante": ex.tech.max(),
                           "tech_robust_avg": ex[ex.strategy == best].tech.mean(),
                           "static_eq60_tech_avg": ex[ex.strategy == "static_eq60"].tech.mean(),
                           "static_eq60_tech_max": ex[ex.strategy == "static_eq60"].tech.max(),
                           "mv_ra4_tech_max": ex[ex.strategy == "mean_var_60_ra4"].tech.max(),
                           "mom_tech_max": ex[ex.strategy == "sector_mom12_top3"].tech.max(),
                           "p10_by_strategy_mean": rt["score_p10"].mean(),
                           "trace": tp}
                    for st in ("mean_var_60_ra4", "sector_mom12_top3", "max_sharpe_60", "static_eq60"):
                        rec[f"p10_{st}"] = rt.loc[st, "score_p10"] if st in rt.index else np.nan
                        rec[f"maxddw_{st}"] = rt.loc[st, "max_drawdown_worst"] if st in rt.index else np.nan
                    if len(orc):
                        rec.update({"oracle_real_p10": orc.ann_real_return.quantile(0.1), "oracle_real_median": orc.ann_real_return.median(),
                                    "oracle_tech_avg": orc.tech.mean(), "oracle_tech_max": orc.tech.max()})
                    recs.append(rec)
    T = pd.DataFrame(recs)
    T.to_csv(lib.OUT / "tech_cap_grid.csv", index=False)
    print(T.drop(columns=["trace"]).to_string(index=False, float_format=F))
    return T


SIG = ["infl12_us", "tbill_us", "long_us", "slope_us", "real_short_us", "d_long_12m_us", "cape", "credit_spread",
       "mom12_us", "trend10_us"]
SIG_CA = ["infl12_ca", "tbill_ca", "long_ca", "slope_ca", "real_short_ca", "mom12_ca"]
TARGETS = ["equity_total", "bonds_total", "duration_long_share", "gold", "cash", "eq_core", "eq_sector"]


def reverse():
    print("=" * 30, "REVERSE ENGINEERING: oracle weights (class-level and sector-level) vs start-of-window signals")
    recs, stab, allw = [], [], []
    for era in ERAS:
        for suffix in ("_classes", ""):
            for mode in ("rolling", "non_overlapping"):
                tp = lib.trace_path(f"mateo_{era}_esg{suffix}", mode, 10, "1")
                if not tp:
                    continue
                df = lib.rows(tp)
                orc = df[df.hindsight].copy()
                G = pd.DataFrame([lib.grouped_weights(w) for w in orc.avg_weights]).fillna(0.0)
                for t in TARGETS:
                    if t not in G:
                        G[t] = 0.0
                sig = pd.DataFrame([signals.at_start(s) for s in orc.start])
                G["window"] = orc.window.values
                G["oracle_real"] = orc.ann_real_return.values
                X = pd.concat([G, sig], axis=1)
                X["era"], X["universe"], X["mode"], X["trace"] = era, ("classes" if suffix else "sectors"), mode, tp
                allw.append(X)
                stab.append({"era": era, "universe": "classes" if suffix else "sectors", "mode": mode, "n": len(G),
                             **{f"{t}_mean": G[t].mean() for t in TARGETS}, **{f"{t}_std": G[t].std() for t in TARGETS},
                             **{f"{t}_min": G[t].min() for t in TARGETS}, **{f"{t}_max": G[t].max() for t in TARGETS},
                             "trace": tp})
                sigs = SIG + (SIG_CA if era == "cad" else [])
                for t in TARGETS:
                    if G[t].std() < 1e-6:
                        continue
                    for sname in sigs:
                        ok = X[sname].notna()
                        if ok.sum() < 4:
                            continue
                        rho, pv = spearmanr(X.loc[ok, sname], X.loc[ok, t])
                        recs.append({"era": era, "universe": "classes" if suffix else "sectors", "mode": mode, "target": t,
                                     "signal": sname, "n": int(ok.sum()), "spearman": rho, "p_naive": pv, "trace": tp})
    C = pd.DataFrame(recs)
    C.to_csv(lib.OUT / "reverse_corr.csv", index=False)
    ST = pd.DataFrame(stab)
    ST.to_csv(lib.OUT / "oracle_stability.csv", index=False)
    AW = pd.concat(allw) if allw else pd.DataFrame()
    AW.to_csv(lib.OUT / "oracle_weights_signals.csv", index=False)
    print(ST.drop(columns=["trace"]).T.to_string())
    # consistency across eras (class-level, rolling): same sign everywhere and |rho| >= 0.3
    if len(C):
        cl = C[(C.universe == "classes")]
        piv = cl.pivot_table(index=["target", "signal"], columns=["era", "mode"], values="spearman")
        piv["n_cols"] = piv.notna().sum(axis=1)
        vals = piv.drop(columns="n_cols")
        piv["same_sign"] = (np.sign(vals).fillna(0).abs().sum(axis=1) == np.abs(np.sign(vals).fillna(0).sum(axis=1)))
        piv["min_abs"] = vals.abs().min(axis=1)
        piv = piv.sort_values("min_abs", ascending=False)
        piv.to_csv(lib.OUT / "reverse_consistency.csv")
        print(piv.head(30).to_string(float_format=F))
    return C


def regimes():
    """Oracle class weights by regime of the window (realised over the window, ex post description)."""
    print("=" * 30, "REGIMES (ex-post description of each rolling window, class-level oracle, esg)")
    out = []
    T = signals.table()
    for era in ERAS:
        tp = lib.trace_path(f"mateo_{era}_esg_classes", "rolling", 10, "1")
        if not tp:
            continue
        df = lib.rows(tp)
        orc = df[df.hindsight]
        for _, o in orc.iterrows():
            s, e = pd.Timestamp(o.start), pd.Timestamp(o.end)
            seg = T.loc[s:e]
            g = lib.grouped_weights(o.avg_weights)
            infl_col = "infl12_ca" if era == "cad" else "infl12_us"
            long_col = "long_ca" if era == "cad" else "long_us"
            avg_infl = seg[infl_col].mean()
            dlong = seg[long_col].dropna().iloc[-1] - seg[long_col].dropna().iloc[0]
            crises = [n for n, a, b in [("1929-32", "1929-09", "1932-06"), ("1973-74", "1973-01", "1974-12"),
                                        ("2000-02", "2000-03", "2002-10"), ("2008-09", "2007-10", "2009-03"),
                                        ("2022", "2022-01", "2022-10")] if pd.Timestamp(a) >= s and pd.Timestamp(b) <= e]
            out.append({"era": era, "window": o.window, "avg_infl": avg_infl, "d_long_yield": dlong,
                        "infl_regime": "high(>4%)" if avg_infl > 4 else "low(<=4%)",
                        "rate_regime": "rising(>+1pt)" if dlong > 1 else ("falling(<-1pt)" if dlong < -1 else "flat"),
                        "crises": ",".join(crises), **{k: g.get(k, 0) for k in TARGETS}, "oracle_real": o.ann_real_return,
                        "trace": tp})
    Rg = pd.DataFrame(out)
    Rg.to_csv(lib.OUT / "regimes.csv", index=False)
    if len(Rg):
        for key in ("infl_regime", "rate_regime"):
            print(Rg.groupby(["era", key])[["equity_total", "bonds_total", "duration_long_share", "gold", "cash", "oracle_real"]]
                  .agg(["mean", "count"]).to_string(float_format=F))
        has22 = Rg[Rg.crises.str.contains("2022")]
        print("windows containing 2022:", len(has22))
        print(has22[["era", "window", "equity_total", "bonds_total", "duration_long_share", "gold", "cash", "oracle_real"]].to_string(index=False, float_format=F))
    return Rg


if __name__ == "__main__":
    which = sys.argv[1:] or ["main", "esg", "tech", "reverse", "regimes"]
    if "main" in which:
        main()
    if "esg" in which:
        esg_cost()
    if "tech" in which:
        tech()
    if "reverse" in which:
        reverse()
    if "regimes" in which:
        regimes()


def cross_era(var="esg"):
    """Cross-era robustness: for each strategy, worst p10 across eras (rolling h10) and max breach rate;
    plus average weights (class level) of each strategy. Robust = max of min-p10 among strategies whose
    breach rate <= 0.25 in EVERY era."""
    print("=" * 30, f"CROSS-ERA ROBUSTNESS ({var}, rolling h10 + h8/h12 sensitivity)")
    recs = []
    for era in ERAS:
        for h in (10, 8, 12):
            tp = lib.trace_path(f"mateo_{era}_{var}", "rolling", h)
            if not tp:
                continue
            df = lib.rows(tp)
            rt = robust_table(df, 0.10, None)
            ex = df[~df.hindsight]
            for st, r in rt.iterrows():
                g = ex[ex.strategy == st]
                W = pd.DataFrame([lib.grouped_weights(w) for w in g.avg_weights]).fillna(0).mean()
                recs.append({"era": era, "h": h, "strategy": st, "p10": r["score_p10"], "median": r["score_median"],
                             "worst": r["score_worst"], "breach_rate": r["breach_rate"], "shortfall": r["shortfall_prob"],
                             "maxdd_worst": r["max_drawdown_worst"], "vol_median": g.volatility.median(),
                             "cvar5_median": g.cvar_5.median(), "recovery_p90": g.recovery_months.quantile(0.9),
                             "avg_equity": W.get("equity_total", 0), "avg_bonds": W.get("bonds_total", 0),
                             "avg_gold": W.get("gold", 0), "avg_cash": W.get("cash", 0), "trace": tp})
    D = pd.DataFrame(recs)
    D.to_csv(lib.OUT / f"cross_era_{var}.csv", index=False)
    d10 = D[D.h == 10]
    agg = d10.groupby("strategy").agg(min_p10=("p10", "min"), mean_p10=("p10", "mean"), max_breach=("breach_rate", "max"),
                                      max_shortfall=("shortfall", "max"), worst_dd=("maxdd_worst", "max"),
                                      avg_equity=("avg_equity", "mean"), n_eras=("era", "nunique"))
    agg["eligible_breach_le_0.25_all_eras"] = agg.max_breach <= 0.25
    agg = agg.sort_values(["eligible_breach_le_0.25_all_eras", "min_p10"], ascending=False)
    print(agg.to_string(float_format=F))
    agg.to_csv(lib.OUT / f"cross_era_{var}_agg.csv")
    piv = D.pivot_table(index="strategy", columns=["era", "h"], values="p10")
    print(piv.to_string(float_format=F))
    return D, agg


if __name__ == "__main__" and "cross" in sys.argv[1:]:
    cross_era("esg")
    cross_era("base")
