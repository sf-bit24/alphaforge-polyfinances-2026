"""D5 (Amira, momentum top-3 contre base diversifiée) : tableau comparatif des candidats sur les 6 runs FNB.

Lecture seule : results/croisement_analysis/will_vs_cap.json (contrôles moteur actuel, limite 0,40) et
concordance.json (détention mois par mois sur une longue fenêtre). Aucun nouveau run moteur.
Écrit results/decisions_analysis/d5_amira.json. SIMULATION UNIQUEMENT, pas un conseil.
"""
from __future__ import annotations

import json
from pathlib import Path

BT = Path(__file__).resolve().parents[2]
CA = BT / "results" / "croisement_analysis"
OUT = BT / "results" / "decisions_analysis" / "d5_amira.json"
CANDS = ["Mom_etf_top3", "Mom_etf_top3_core50", "Trend10_E80", "E80_us50_g10_t0", "E70_us50_g10_t0",
         "E80_us70_g10_t0", "E90_us70_g10_t0", "E80_us50_g0_t0", "RP_invvol_36m"]


def main() -> None:
    wc = json.loads((CA / "will_vs_cap.json").read_text())["results"]["amira"]["controle_0.40_moteur_actuel"]
    con = json.loads((CA / "concordance.json").read_text())["results"]["amira_holdings"]
    per_run = wc["per_run"]
    best = {run: max((r["score_p10"] for r in v["table"] if r["eligible"]), default=None) for run, v in per_run.items()}
    table = {}
    for s in CANDS:
        rows = {}
        for run, v in per_run.items():
            r = next((x for x in v["table"] if x["strategy"] == s), None)
            if r is None:
                continue
            rows[run] = {"p10": r["score_p10"], "median": r["score_median"], "maxdd_worst": r["max_drawdown_worst"],
                         "breach_rate": r["breach_rate"], "eligible": r["eligible"],
                         "regret_pt": None if best[run] is None else round(100 * (best[run] - r["score_p10"]), 2)}
        el = [x for x in rows.values()]
        table[s] = {
            "per_run": rows,
            "eligible_all_runs": all(x["eligible"] for x in el) and len(el) == len(per_run),
            "n_runs_ineligible": sum(not x["eligible"] for x in el),
            "p10_min": round(min(x["p10"] for x in el), 4),
            "regret_max_pt": max(x["regret_pt"] for x in el),
            "maxdd_worst_all_runs": round(max(x["maxdd_worst"] for x in el), 4),
            "breach_rate_max": round(max(x["breach_rate"] for x in el), 3),
        }
    holdings = {}
    for k, v in con.items():
        holdings[k] = {kk: v.get(kk) for kk in ["period", "share_months_0_equity", "share_months_ge_3_groups",
                                                "share_months_gold_ge_1_3", "share_months_cash_ge_1_3",
                                                "effective_n_assets_median", "turnover_ann", "mean_weights_by_group",
                                                "y2022_mean_weights"]}
    # Same minimax-regret rule, restricted to the 3 CAD runs (Amira's currency; no 1929-32 in the sample)
    cad_runs = [r for r in per_run if r.startswith("amira_etf|")]
    strats = {x["strategy"] for r in cad_runs for x in per_run[r]["table"]}
    cad_rank = []
    for s in strats:
        rows = [next((x for x in per_run[r]["table"] if x["strategy"] == s), None) for r in cad_runs]
        if any(x is None or not x["eligible"] for x in rows):
            continue
        reg = [100 * (best[r] - x["score_p10"]) for r, x in zip(cad_runs, rows)]
        cad_rank.append({"strategy": s, "regret_max_pt": round(max(reg), 2),
                         "p10_by_run_pct": [round(100 * x["score_p10"], 2) for x in rows],
                         "maxdd_worst": round(max(x["max_drawdown_worst"] for x in rows), 3)})
    cad_rank.sort(key=lambda d: d["regret_max_pt"])
    out = {"inputs": [str(CA / "will_vs_cap.json"), str(CA / "concordance.json")],
           "runs": list(per_run.keys()), "best_eligible_p10_per_run": best,
           "retained_by_minimax_regret": wc.get("retained_minimax_regret"), "candidates": table, "holdings": holdings,
           "minimax_regret_cad_runs_only": {"runs": cad_runs, "top10": cad_rank[:10],
                                            "Mom_etf_top3": next(d for d in cad_rank if d["strategy"] == "Mom_etf_top3"),
                                            "Trend10_E80": next(d for d in cad_rank if d["strategy"] == "Trend10_E80")}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    for s, t in table.items():
        print(f"{s:22s} elig_all={t['eligible_all_runs']!s:5s} n_inelig={t['n_runs_ineligible']} p10_min={t['p10_min']:.4f} "
              f"regret_max={t['regret_max_pt']} maxdd={t['maxdd_worst_all_runs']} breach_max={t['breach_rate_max']}")
        for run, r in t["per_run"].items():
            print(f"    {run:40s} p10={r['p10']:.4f} med={r['median']:.4f} mdd={r['maxdd_worst']:.3f} br={r['breach_rate']:.3f} el={r['eligible']}")
    for k, h in holdings.items():
        print(k, {kk: h[kk] for kk in ['share_months_0_equity', 'share_months_ge_3_groups', 'share_months_gold_ge_1_3', 'turnover_ann', 'effective_n_assets_median']})


if __name__ == "__main__":
    main()
