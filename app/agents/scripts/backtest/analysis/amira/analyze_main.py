"""Reverse engineering of Amira's engine traces: per-window table (ORACLE vs best ex-ante vs robust choice),
oracle-weight stability, regime / start-of-window signal associations.

    uv run --group finance python -I analysis/amira/analyze_main.py <trace.json> [<trace.json> ...]
Writes results/amira_analysis/<run_id>_analysis.json. SIMULATION ONLY; ORACLE = hindsight, non investable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amira_common import BT, RESULTS, SECTORS, rel, write_json  # noqa: E402
from signals import at_window_starts, monthly_signals  # noqa: E402
from alphaforge.finance.backtest.data import load_lookthrough  # noqa: E402

GROUPS = {
    "equity_broad": ["US_MKT", "CA_EQ"],
    "sectors_nontech": [s for s in SECTORS if s != "US_IND_BUSEQ"],
    "buseq": ["US_IND_BUSEQ"],
    "bonds_short": ["UST_2Y", "UST_5Y"],
    "bonds_long": ["UST_10Y", "UST_20Y", "CA_GOV_10Y"],
    "credit": ["CORP_AAA", "CORP_BAA"],
    "gold": ["GOLD"],
    "cash": ["UST_TBILL", "CA_TBILL"],
}
SIGNALS = ["tbill", "long_rate", "slope", "d_long_rate_12m", "infl_us_12m", "real_tbill", "mkt_12m",
           "mkt_above_ma10", "tech_rel_36m", "buseq_share", "cape", "ca_long_rate", "infl_ca_12m", "usdcad_12m"]
CRISES = {"1929": "1929-09", "1973-74": "1973-01", "2000-02": "2000-03", "2008": "2007-10", "2022": "2021-12"}


def grouped(w: dict, buseq_share: float) -> dict:
    g = {k: float(sum(w.get(a, 0.0) for a in v)) for k, v in GROUPS.items()}
    g["equity_total"] = g["equity_broad"] + g["sectors_nontech"] + g["buseq"]
    g["tech_lookthrough"] = float(w.get("US_MKT", 0.0) * buseq_share + w.get("US_IND_BUSEQ", 0.0))
    g["bonds_total"] = g["bonds_short"] + g["bonds_long"] + g["credit"]
    return g


def analyse(path: Path) -> dict:
    tr = json.loads(path.read_text())
    rows = pd.DataFrame(tr["results"])
    lt = load_lookthrough()["US_IND_BUSEQ"]
    orc = {o["window"]: o for o in tr["oracle"]}
    ex = rows[~rows["hindsight"]]
    robust = tr["summary"]["robust_choice"]
    sig = at_window_starts(tr["windows"], monthly_signals())
    per = []
    for wlab in tr["windows"]:
        r = ex[ex["window"] == wlab].set_index("strategy")
        best = r["score"].idxmax()
        o = orc.get(wlab)
        start = pd.Timestamp(wlab.split("..")[0] + "-01") - pd.offsets.MonthEnd(1)
        bs = float(lt.loc[:start].iloc[-1]) if len(lt.loc[:start]) else float(lt.iloc[0])
        rec = {"window": wlab, "best_ex_ante": best, "best_ex_ante_real": float(r.at[best, "ann_real_return"]),
               "best_ex_ante_maxdd": float(r.at[best, "max_drawdown"]),
               "robust": robust, "robust_real": float(r.at[robust, "ann_real_return"]),
               "robust_vol": float(r.at[robust, "volatility"]), "robust_maxdd": float(r.at[robust, "max_drawdown"]),
               "robust_recovery_m": r.at[robust, "recovery_months"], "robust_cvar5": float(r.at[robust, "cvar_5"]),
               "robust_missed": bool(r.at[robust, "missed_target"]), "buseq_share_start": bs}
        if o:
            m = o["metrics"]
            w = o["weights"]
            top = sorted(w.items(), key=lambda kv: -kv[1])[:4]
            rec.update({"oracle_real": m["ann_real_return"], "oracle_vol": m["volatility"], "oracle_maxdd": m["max_drawdown"],
                        "oracle_recovery_m": m["recovery_months"], "oracle_cvar5": m["cvar_5"],
                        "oracle_risk_limits_met": o["risk_limits_met"],
                        "oracle_top": "; ".join(f"{a} {x:.2f}" for a, x in top if x > 0.005),
                        "gap_oracle_minus_robust": m["ann_real_return"] - float(r.at[robust, "ann_real_return"]),
                        **{f"o_{k}": v for k, v in grouped(w, bs).items()}, "_w": w})
        per.append(rec)
    per = pd.DataFrame(per).set_index("window")
    out = {"trace": rel(path), "run_id": tr["run_id"], "profile": tr["profile"]["id"], "mode": tr["profile"]["mode"],
           "horizon": tr["profile"]["horizon_years"], "n_windows": len(tr["windows"]),
           "data_info": tr["data_info"], "summary": tr["summary"],
           "robust_selection": tr["robust_selection"], "walk_forward": tr["walk_forward"]}
    out["per_window"] = per.drop(columns=["_w"], errors="ignore").reset_index().to_dict(orient="records")
    out["best_ex_ante_counts"] = per["best_ex_ante"].value_counts().to_dict()
    if "_w" in per:
        W = pd.DataFrame(list(per["_w"]), index=per.index).fillna(0.0)
        out["oracle_weight_stability"] = pd.DataFrame({
            "mean": W.mean(), "std": W.std(), "min": W.min(), "max": W.max(),
            "share_windows_gt_5pct": (W > 0.05).mean()}).sort_values("mean", ascending=False).reset_index() \
            .rename(columns={"index": "asset"}).to_dict(orient="records")
        G = per[[c for c in per.columns if c.startswith("o_")]]
        out["oracle_group_stability"] = pd.DataFrame({"mean": G.mean(), "std": G.std(), "min": G.min(),
                                                      "max": G.max()}).reset_index() \
            .rename(columns={"index": "group"}).to_dict(orient="records")
        # associations with start-of-window signals
        S = sig.reindex(per.index)
        targets = {"o_equity_total": G["o_equity_total"], "o_tech_lookthrough": G["o_tech_lookthrough"],
                   "o_bonds_long": G["o_bonds_long"], "o_gold": G["o_gold"], "o_bonds_total": G["o_bonds_total"],
                   "oracle_real": per["oracle_real"], "robust_real": per["robust_real"],
                   "gap_oracle_minus_robust": per["gap_oracle_minus_robust"]}
        # strategy-difference targets: does momentum / trend / tech tilt win more after some signal?
        piv = ex.pivot(index="window", columns="strategy", values="ann_real_return").reindex(per.index)
        for a, b in (("Mom_all_top4", "S_core_E80_T30"), ("Trend10_core", "S_core_E80_T30"),
                     ("S_core_E80_T30", "S_core_E80_T20"), ("S_mkt80_bonds20", "S_core_E80_T30")):
            if a in piv and b in piv:
                targets[f"diff_{a}_minus_{b}"] = piv[a] - piv[b]
        n = len(per)
        step = int(tr["profile"]["step_months"]) if tr["profile"]["mode"] == "rolling" else int(tr["profile"]["horizon_years"] * 12)
        n_phase = max(1, int(round(tr["profile"]["horizon_years"] * 12 / step)))
        assoc = []
        for tn, t in targets.items():
            if t.std() == 0 or t.isna().all():
                continue
            for sn in SIGNALS:
                x = S[sn]
                m = x.notna() & t.notna()
                if m.sum() < 6 or x[m].std() == 0:
                    continue
                rho = float(pd.Series(x[m]).rank().corr(pd.Series(t[m]).rank()))
                signs = []
                for ph in range(n_phase):
                    idx = [i for i in range(n) if i % n_phase == ph and m.iloc[i]]
                    if len(idx) >= 4:
                        rr = pd.Series(x.iloc[idx]).rank().corr(pd.Series(t.iloc[idx]).rank())
                        if np.isfinite(rr):
                            signs.append(np.sign(rr) == np.sign(rho))
                tercile = pd.qcut(x[m], 3, labels=["low", "mid", "high"], duplicates="drop") if x[m].nunique() > 3 else None
                by_t = t[m].groupby(tercile).mean().to_dict() if tercile is not None else {}
                assoc.append({"target": tn, "signal": sn, "spearman": rho, "n": int(m.sum()),
                              "n_eff_approx": round(m.sum() * step / (tr["profile"]["horizon_years"] * 12), 1),
                              "phase_subsets": len(signs), "phase_sign_agree": float(np.mean(signs)) if signs else None,
                              "target_mean_by_signal_tercile": {str(k): float(v) for k, v in by_t.items()},
                              "tercile_edges": [float(v) for v in x[m].quantile([0, 1 / 3, 2 / 3, 1]).values]})
        out["associations"] = sorted(assoc, key=lambda d: -abs(d["spearman"]))
        # crisis regimes: windows whose start precedes the crisis date by 0-36 months
        cr = {}
        for cname, cd in CRISES.items():
            c = pd.Timestamp(cd + "-01")
            st = pd.to_datetime([wl.split("..")[0] + "-01" for wl in per.index])
            mask = (st <= c) & (st > c - pd.DateOffset(months=36))
            if mask.any():
                sub = per[mask]
                cr[cname] = {"windows": list(sub.index), "o_equity_total": float(sub["o_equity_total"].mean()),
                             "o_tech_lookthrough": float(sub["o_tech_lookthrough"].mean()),
                             "o_bonds_total": float(sub["o_bonds_total"].mean()), "o_gold": float(sub["o_gold"].mean()),
                             "oracle_real": float(sub["oracle_real"].mean()), "robust_real": float(sub["robust_real"].mean()),
                             "best_ex_ante": sub["best_ex_ante"].value_counts().to_dict()}
        cr["_all_windows"] = {"o_equity_total": float(per["o_equity_total"].mean()),
                              "o_tech_lookthrough": float(per["o_tech_lookthrough"].mean()),
                              "o_bonds_total": float(per["o_bonds_total"].mean()), "o_gold": float(per["o_gold"].mean()),
                              "oracle_real": float(per["oracle_real"].mean()), "robust_real": float(per["robust_real"].mean())}
        out["crisis_windows"] = cr
    out["signals_at_start"] = sig.reset_index().to_dict(orient="records")
    dest = RESULTS / "amira_analysis" / f"{tr['profile']['id']}__{tr['run_id']}_analysis.json"
    p = write_json(out, dest, [rel(path)])
    print(p)
    return out


if __name__ == "__main__":
    for a in sys.argv[1:]:
        analyse(Path(a).resolve())
