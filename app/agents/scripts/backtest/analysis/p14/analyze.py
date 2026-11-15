"""Persona 14 - read the engine traces (analysis/p14/runs_*.json) and build the report tables. No new returns are
simulated here except the start-of-window signals of R1 (read from the same data). SIMULATION ONLY.
Outputs (results/p14_analysis/): per_window_*.csv, robust_summary.csv, cross_era.csv, walkforward_summary.csv,
oracle_classes.csv, robust_classes.csv, energy_cap_effect.csv, reverse_signals.csv
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as K  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from alphaforge.finance.backtest.data import load_inflation, load_returns  # noqa: E402

CLASS = {"CA_EQ": "fnb_actions", "US_MKT": "fnb_actions", "US_MKT_XEN": "fnb_actions",
         "US_IND_ENRGY": "energie_directe", "CNQ.TO": "energie_directe", "ENB.TO": "energie_directe", "XOM": "energie_directe",
         "US_IND_HLTH": "actions_us_hors_energie", "US_IND_NODUR": "actions_us_hors_energie", "US_IND_UTILS": "actions_us_hors_energie",
         "JNJ": "actions_us_hors_energie", "PG": "actions_us_hors_energie",
         "GOLD": "or", "CA_TBILL": "fnb_oblig_et_encaisse", "UST_TBILL": "fnb_oblig_et_encaisse"}


def cls(a):
    return CLASS.get(a, "fnb_oblig_et_encaisse")


def runs():
    d = {}
    for f in sorted(glob.glob(str(K.HERE / "runs_*.json"))):
        d.update(json.loads(Path(f).read_text()))
    return d


def load(path):
    return json.loads((K.BT / path).read_text())


def df_rows(t):
    return pd.DataFrame(t["results"])


def top(w, n=3):
    return "; ".join(f"{a} {x:.2f}" for a, x in sorted(w.items(), key=lambda kv: -kv[1])[:n] if x > 0.005)


def grouped(w):
    g = {}
    for a, x in w.items():
        g[cls(a)] = g.get(cls(a), 0) + float(x)
    return g


def main():
    RU = runs()
    get = lambda pid, mode, h: next((v for k, v in RU.items() if k.startswith(f"{pid}:{mode}:{h}:")), None)
    pids = sorted({k.split(":")[0] for k in RU})
    # 1 per window (non-overlapping)
    for pid in pids:
        h = {"coussin": 1, "etudes": 10, "retraite": 16, "titres": 10}[pid.split("_")[1]]
        p = get(pid, "non_overlapping", h)
        if not p:
            continue
        t = load(p)
        R = df_rows(t)
        out = []
        for w, g in R.groupby("window", sort=False):
            o = g[g.hindsight]
            ex = g[~g.hindsight].sort_values("score", ascending=False)
            b = ex.iloc[0]
            row = {"window": w, "best_ex_ante": b.strategy, "best_real": b.ann_real_return, "best_maxdd": b.max_drawdown}
            if len(o):
                o = o.iloc[0]
                row.update({"oracle_real": o.ann_real_return, "oracle_vol": o.volatility, "oracle_maxdd": o.max_drawdown,
                            "oracle_top": top(o.avg_weights), "oracle_energy_direct": grouped(o.avg_weights).get("energie_directe", 0.0),
                            "gap": o.score - b.score})
            out.append(row)
        pd.DataFrame(out).to_csv(K.OUT / f"per_window_{pid}.csv", index=False)
    # 2 robust summary + 5/6 classes + 4 walk-forward
    rob, wf_rows, ocl, rcl = [], [], [], []
    for k, p in RU.items():
        pid, mode, h, orc = k.split(":")[:4]
        if mode != "rolling":
            continue
        t = load(p)
        rb = pd.DataFrame(t["robust_selection"])
        for _, r in rb.iterrows():
            rob.append({"pid": pid, "h": h, "trace": p, **r.to_dict()})
        wf = pd.DataFrame(t["walk_forward"])
        if len(wf):
            wf_rows.append({"pid": pid, "h": h, "trace": p, "n_oos": len(wf), "mean_oos": wf.chosen_score.mean(),
                            "p10_oos": wf.chosen_score.quantile(0.1),
                            "oos_shortfall": float(wf.chosen_missed_target.astype(float).mean()) if wf.chosen_missed_target.notna().all() else np.nan,
                            "mean_oracle_gap": (wf.oracle_score - wf.chosen_score).mean() if wf.oracle_score.notna().any() else np.nan,
                            "chosen_counts": wf.chosen.value_counts().to_dict()})
        R = df_rows(t)
        o = R[R.hindsight]
        if len(o):
            G = pd.DataFrame([grouped(w) for w in o.avg_weights]).fillna(0)
            for c in G.columns:
                ocl.append({"pid": pid, "h": h, "class": c, "p10": G[c].quantile(0.1), "median": G[c].median(),
                            "p90": G[c].quantile(0.9), "share_windows_gt0": float((G[c] > 0.01).mean()), "n": len(G), "trace": p})
        choice = t["summary"]["robust_choice"]
        ex = R[(~R.hindsight) & (R.strategy == choice)]
        Wm = pd.DataFrame(list(ex.avg_weights)).fillna(0).mean()
        g = grouped(Wm.to_dict())
        rcl.append({"pid": pid, "h": h, "robust_choice": choice, **{f"w_{a}": round(x, 4) for a, x in Wm.items() if x > 0.001},
                    **{f"class_{c}": round(x, 4) for c, x in g.items()}, "trace": p})
    rob = pd.DataFrame(rob)
    rob.to_csv(K.OUT / "robust_summary.csv", index=False)
    pd.DataFrame(wf_rows).to_csv(K.OUT / "walkforward_summary.csv", index=False)
    pd.DataFrame(ocl).to_csv(K.OUT / "oracle_classes.csv", index=False)
    pd.DataFrame(rcl).to_csv(K.OUT / "robust_classes.csv", index=False)
    # 3 cross-era rule: eligible (breach <= 0.25) in BOTH eras, maximise the worst p10
    ce = []
    for pocket, h in (("etudes", "10"), ("retraite", "16")):
        for var in ("", "_libre", "_volonte"):
            a = rob[(rob.pid == f"p14_{pocket}_usd{var}") & (rob.h == h)].set_index("strategy")
            b = rob[(rob.pid == f"p14_{pocket}_cad{var}") & (rob.h == h)].set_index("strategy")
            if a.empty or b.empty:
                continue
            j = a[["score_p10", "breach_rate", "max_drawdown_worst", "score_median"]].join(
                b[["score_p10", "breach_rate", "max_drawdown_worst", "score_median"]], lsuffix="_usd", rsuffix="_cad", how="inner")
            j["eligible_both"] = (j.breach_rate_usd <= 0.25) & (j.breach_rate_cad <= 0.25)
            j["worst_p10"] = j[["score_p10_usd", "score_p10_cad"]].min(axis=1)
            j = j.sort_values(["eligible_both", "worst_p10"], ascending=[False, False])
            j["rank"] = range(1, len(j) + 1)
            j.insert(0, "variant", f"{pocket}{var or '_base'}")
            ce.append(j.reset_index())
    if ce:
        pd.concat(ce).to_csv(K.OUT / "cross_era.csv", index=False)
    # 7 energy cap effect: base vs libre, same strategy, same window (rolling)
    eff = []
    for pocket, h in (("etudes", "10"), ("retraite", "16")):
        for era in ("usd", "cad"):
            pb, pl = get(f"p14_{pocket}_{era}", "rolling", h), get(f"p14_{pocket}_{era}_libre", "rolling", h)
            if not (pb and pl):
                continue
            B, L = df_rows(load(pb)), df_rows(load(pl))
            B, L = B[~B.hindsight], L[~L.hindsight]
            m = B.merge(L, on=["window", "strategy"], suffixes=("_cap", "_libre"))
            for s, g in m.groupby("strategy"):
                d = g.ann_real_return_cap - g.ann_real_return_libre
                dd = g.max_drawdown_cap - g.max_drawdown_libre
                eff.append({"pocket": pocket, "era": era, "strategy": s, "n": len(g), "real_diff_median": d.median(),
                            "real_diff_p10": d.quantile(0.1), "real_diff_min": d.min(), "maxdd_diff_median": dd.median(),
                            "maxdd_diff_max": dd.max(), "p10_cap": g.ann_real_return_cap.quantile(0.1),
                            "p10_libre": g.ann_real_return_libre.quantile(0.1)})
    pd.DataFrame(eff).to_csv(K.OUT / "energy_cap_effect.csv", index=False)
    # 8 reverse engineering: oracle energy weight (libre, no cap) vs start-of-window signals
    rev = []
    for pocket, h in (("etudes", "10"), ("retraite", "16")):
        for era, cur, st in (("usd", "USD", "1926-07"), ("cad", "CAD", "1971-02")):
            pl = next((v for kk, v in RU.items() if kk.startswith(f"p14_{pocket}_{era}_libre:non_overlapping:{h}:1")), None)
            pr = get(f"p14_{pocket}_{era}", "rolling", h)
            for lab, path in (("libre_nonoverlap", pl), ("cap_rolling", pr)):
                if not path:
                    continue
                R = df_rows(load(path))
                o = R[R.hindsight].copy()
                if o.empty:
                    continue
                X = load_returns(["US_IND_ENRGY", "US_MKT"], st, "2026-09", cur)
                infl = load_inflation(cur)
                sig = []
                for _, r in o.iterrows():
                    s0 = pd.Timestamp(r.start)
                    past = X.loc[:s0 - pd.offsets.MonthEnd(1)].tail(12)
                    if len(past) < 12:
                        sig.append((np.nan,) * 3)
                        continue
                    rel = (1 + past.US_IND_ENRGY).prod() - (1 + past.US_MKT).prod()
                    w = (1 + X.loc[:s0 - pd.offsets.MonthEnd(1), "US_IND_ENRGY"]).cumprod()
                    ddn = float(w.iloc[-1] / w.max() - 1)
                    inf12 = float((1 + infl.loc[:s0 - pd.offsets.MonthEnd(1)].tail(12)).prod() - 1)
                    sig.append((rel, ddn, inf12))
                o[["sig_energy_rel12m", "sig_energy_dd", "sig_infl12m"]] = sig
                o["oracle_energy"] = [grouped(w).get("energie_directe", 0.0) for w in o.avg_weights]
                o["oracle_equity"] = [sum(v for a, v in w.items() if cls(a) in ("fnb_actions", "energie_directe", "actions_us_hors_energie")) for w in o.avg_weights]
                for y in ("oracle_energy", "oracle_equity"):
                    for x in ("sig_energy_rel12m", "sig_energy_dd", "sig_infl12m"):
                        q = o[[x, y]].dropna()
                        if len(q) >= 4 and q[y].nunique() > 1:
                            rho, pv = spearmanr(q[x], q[y])
                        else:
                            rho, pv = np.nan, np.nan
                        rev.append({"pocket": pocket, "era": era, "run": lab, "y": y, "x": x, "n": len(q), "rho": rho, "p": pv,
                                    "y_mean": q[y].mean() if len(q) else np.nan, "share_y_gt_1pct": float((q[y] > 0.01).mean()) if len(q) else np.nan})
    pd.DataFrame(rev).to_csv(K.OUT / "reverse_signals.csv", index=False)
    print("ok", len(rob), len(wf_rows), len(ocl), len(eff), len(rev))


if __name__ == "__main__":
    main()
