"""Print markdown tables for the report from results/amira_analysis/*_analysis.json (no new computation).

    uv run --group finance python -I analysis/amira/tables.py <analysis.json> [...] [--per-window] [--assoc N]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


def pct(x, d=1):
    return "" if x is None or (isinstance(x, float) and pd.isna(x)) else f"{100 * x:.{d}f}"


def md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def main(paths, per_window=False, n_assoc=12, top=8):
    for p in paths:
        d = json.loads(Path(p).read_text())["result"]
        print(f"\n### {d['profile']} — {d['mode']} h{d['horizon']} ({d['n_windows']} fenêtres) — trace `{d['trace']}`\n")
        info = d["data_info"]
        print(f"Période effective {info['effective'][0]} → {info['effective'][1]}, actif limitant début : "
              f"{info['limiting_start_asset']}.\n")
        rs = pd.DataFrame(d["robust_selection"]).set_index("strategy")
        t = rs.head(top).copy()
        keep = [s for s in ("S_core_E80_T30", "S_mkt80_bonds20", "Mom_all_top4", "Trend10_core", "Trend10_E80",
                            "E80_us50_g10_t0", "E80_us100_g0_t0", "MinVar_60m") if s in rs.index and s not in t.index]
        t = pd.concat([t, rs.loc[keep]])
        tab = pd.DataFrame({"stratégie": t.index, "rang": t["rank"].astype(int),
                            "réel p10 %": t["score_p10"].map(pct), "réel médian %": t["score_median"].map(pct),
                            "réel pire %": t["score_worst"].map(pct), "maxDD pire %": t["max_drawdown_worst"].map(pct),
                            "taux dépass. DD": t["breach_rate"].map(lambda x: f"{x:.2f}"),
                            "P(réel<0)": t["shortfall_prob"].map(lambda x: f"{x:.2f}")})
        print(md(tab))
        s = d["summary"]["walk_forward"]
        wf = pd.DataFrame(d["walk_forward"])
        print(f"\nChoix robuste : **{d['summary']['robust_choice']}**. Walk-forward : {s['n_oos_windows']} fenêtres hors "
              f"échantillon, score moyen {pct(s['mean_oos_score'], 2)} %, p10 {pct(s['p10_oos_score'], 2)} %, "
              f"écart moyen ORACLE − choisi {pct(s['mean_oracle_gap'], 2)} pt"
              + (f" ; choix successifs : {wf['chosen'].value_counts().to_dict()}" if len(wf) else "") + ".")
        if "oracle_group_stability" in d:
            g = pd.DataFrame(d["oracle_group_stability"]).set_index("group")
            print("\nPoids ORACLE par groupe (moyenne / min / max en %) : " + " ; ".join(
                f"{k[2:]} {pct(g.at[k, 'mean'], 0)} [{pct(g.at[k, 'min'], 0)}–{pct(g.at[k, 'max'], 0)}]"
                for k in g.index if g.at[k, "max"] > 0.005))
            w = pd.DataFrame(d["oracle_weight_stability"]).set_index("asset")
            w = w[w["mean"] > 0.01]
            print("\nActifs ORACLE (poids moyen % ; part des fenêtres > 5 %) : " + " ; ".join(
                f"{a} {pct(w.at[a, 'mean'], 0)} ({w.at[a, 'share_windows_gt_5pct']:.2f})" for a in w.index))
            print("\nMeilleure stratégie ex-ante par fenêtre (comptes) : " + str(d["best_ex_ante_counts"]))
        if per_window:
            pw = pd.DataFrame(d["per_window"])
            cols = {"window": "fenêtre", "oracle_top": "ORACLE (poids principaux)",
                    "oracle_real": "ORACLE réel %", "oracle_maxdd": "ORACLE maxDD %",
                    "best_ex_ante": "meilleure ex-ante", "best_ex_ante_real": "son réel %",
                    "robust_real": "choix robuste réel %", "robust_vol": "vol %", "robust_maxdd": "maxDD %",
                    "robust_recovery_m": "recouvr. (mois)", "robust_cvar5": "CVaR5 %",
                    "gap_oracle_minus_robust": "écart ORACLE pt"}
            pw = pw[[c for c in cols if c in pw]].copy()
            for c in pw.columns:
                if c not in ("window", "oracle_top", "best_ex_ante", "robust_recovery_m"):
                    pw[c] = pw[c].map(pct)
            pw["robust_recovery_m"] = pw["robust_recovery_m"].map(lambda x: "non récupéré" if pd.isna(x) else int(x))
            print()
            print(md(pw.rename(columns=cols)))
        if n_assoc and d.get("associations"):
            a = pd.DataFrame(d["associations"])
            a = a[a["target"].str.startswith(("o_", "diff_", "oracle_real", "robust_real"))].head(n_assoc)
            tab = pd.DataFrame({"cible": a["target"], "signal en début de fenêtre": a["signal"],
                                "Spearman": a["spearman"].map(lambda x: f"{x:+.2f}"), "n": a["n"],
                                "n effectif ≈": a["n_eff_approx"],
                                "accord de signe sous-échant.": a["phase_sign_agree"].map(
                                    lambda x: "—" if x is None or pd.isna(x) else f"{x:.2f}"),
                                "moyenne cible par tercile (bas/moy/haut)": a["target_mean_by_signal_tercile"].map(
                                    lambda m: " / ".join(f"{v:.3f}" for v in m.values()))})
            print()
            print(md(tab))
        if d.get("crisis_windows"):
            print("\nFenêtres commençant 0–36 mois avant une crise :")
            for k, v in d["crisis_windows"].items():
                print(f"- {k}: " + ", ".join(f"{kk}={vv:.3f}" if isinstance(vv, float) else f"{kk}={vv}"
                                             for kk, vv in v.items() if kk != "windows"))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = 12
    for a in sys.argv[1:]:
        if a.startswith("--assoc="):
            n = int(a.split("=")[1])
    main(args, per_window="--per-window" in sys.argv, n_assoc=n)
