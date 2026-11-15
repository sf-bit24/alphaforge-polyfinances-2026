"""D5 bis : réconciliation avec le rapport A (D4) — Amira sous max_drawdown 0,30 (défaut de A) et 0,40 (confirmé).

Lecture seule des traces moteur du croisement (mêmes univers, stratégies, fenêtres ; seule la limite de baisse change) :
  0,40 : results/croisement_runs/amira_etf/…, amira_etf_long_usd/…   (moteur actuel)
  0,30 : results/croisement_runs/x_amira_etf_w30/…, x_amira_etf_long_usd_w30/…
Règle de choix identique au rapport Amira : par run, éligible si breach_rate ≤ 0,10 ; puis minimax du regret
(regret = meilleur p10 éligible du run − p10 de la stratégie), (i) sur les 6 runs, (ii) sur les 3 runs CAD.
« Cœur statique diversifié » = stratégies `static` du profil (E{actions}_us{part US}_g{or}_t{tech}) ; elles ont toutes
or ≤ 10 % et sont projetées sur tech look-through ≤ 30 % et secteurs ≤ 30 % (contraintes du profil). L'univers FNB
n'a ni titre ni crypto : les plafonds 3 % titre / 3 % crypto ne lient pas ici.
Écrit results/decisions_analysis/d5b_amira_w30.json. SIMULATION UNIQUEMENT, pas un conseil.
"""
from __future__ import annotations

import json
from pathlib import Path

BT = Path(__file__).resolve().parents[2]
CR = BT / "results" / "croisement_runs"
OUT = BT / "results" / "decisions_analysis" / "d5b_amira_w30.json"
RUNS = {"0.40": {"amira_etf": "amira_etf", "amira_etf_long_usd": "amira_etf_long_usd"},
        "0.30": {"amira_etf": "x_amira_etf_w30", "amira_etf_long_usd": "x_amira_etf_long_usd_w30"}}
KEYS = [("non_overlapping", "h15"), ("rolling", "h15"), ("rolling", "h20")]
MAX_BREACH = 0.10
FOCUS = ["E80_us50_g10_t0", "E70_us50_g10_t0", "E70_us70_g10_t0", "E90_us50_g10_t0", "Mom_etf_top3",
         "Mom_etf_top3_core50", "Trend10_E80", "RP_invvol_36m", "E80_us100_g0_t0", "E70_us100_g0_t0"]


def load(limit: str) -> dict:
    out = {}
    for base, folder in RUNS[limit].items():
        for mode, h in KEYS:
            f = sorted((CR / folder).glob(f"*_{mode}_{h}.json"))[-1]
            t = json.loads(f.read_text())
            statics = {s["name"] for s in t["profile"]["strategies"] if s["type"] == "static"}
            weights = {s["name"]: s["params"]["weights"] for s in t["profile"]["strategies"] if s["type"] == "static"}
            rows = {r["strategy"]: r for r in t["robust_selection"]}
            out[f"{base}|{mode}|{h}"] = {"trace": str(f.relative_to(BT)), "rows": rows, "statics": statics,
                                         "weights": weights, "limit": t["profile"]["risk_limits"]["max_drawdown"]}
    return out


def eligible(r: dict) -> bool:
    return r["breach_rate"] <= MAX_BREACH + 1e-12


def minimax(runs: dict, keys: list[str], only_static: bool = False) -> list[dict]:
    best = {k: max(r["score_p10"] for r in runs[k]["rows"].values() if eligible(r)) for k in keys}
    names = set.intersection(*[set(runs[k]["rows"]) for k in keys])
    res = []
    for s in names:
        if only_static and not all(s in runs[k]["statics"] for k in keys):
            continue
        rr = [runs[k]["rows"][s] for k in keys]
        if not all(eligible(r) for r in rr):
            continue
        reg = [100 * (best[k] - r["score_p10"]) for k, r in zip(keys, rr)]
        res.append({"strategy": s, "regret_max_pt": round(max(reg), 2),
                    "p10_by_run_pct": [round(100 * r["score_p10"], 2) for r in rr],
                    "median_by_run_pct": [round(100 * r["score_median"], 2) for r in rr],
                    "maxdd_worst": round(max(r["max_drawdown_worst"] for r in rr), 3)})
    return sorted(res, key=lambda d: d["regret_max_pt"])


def main() -> None:
    out = {"rule": f"per run eligible if breach_rate <= {MAX_BREACH}; minimax regret of p10 real", "limits": {}}
    for limit in ["0.30", "0.40"]:
        runs = load(limit)
        cad = [k for k in runs if k.startswith("amira_etf|")]
        allk = list(runs)
        focus = {}
        for s in FOCUS:
            focus[s] = {k: ({"p10": v["rows"][s]["score_p10"], "median": v["rows"][s]["score_median"],
                             "maxdd_worst": v["rows"][s]["max_drawdown_worst"], "breach_rate": v["rows"][s]["breach_rate"],
                             "eligible": eligible(v["rows"][s])} if s in v["rows"] else "absent of universe")
                        for k, v in runs.items()}
        w = runs[cad[0]]["weights"]
        eq = {s: round(sum(x for a, x in ws.items() if a in ("US_MKT", "CA_EQ", "US_IND_BUSEQ")), 2) for s, ws in w.items()}
        out["limits"][limit] = {
            "traces": {k: v["trace"] for k, v in runs.items()},
            "focus": focus,
            "minimax_6_runs": minimax(runs, allk)[:5],
            "minimax_6_runs_static_only": minimax(runs, allk, only_static=True)[:5],
            "minimax_cad_runs": minimax(runs, cad)[:8],
            "minimax_cad_runs_static_only": [dict(d, equity_weight=eq.get(d["strategy"]), weights=w.get(d["strategy"]))
                                             for d in minimax(runs, cad, only_static=True)[:6]],
            "n_static_eligible_all_cad_runs": len(minimax(runs, cad, only_static=True)),
            "n_static_eligible_all_6_runs": len(minimax(runs, allk, only_static=True)),
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    for limit, d in out["limits"].items():
        print("==== limit", limit)
        for s in ["E80_us50_g10_t0", "E70_us50_g10_t0", "Mom_etf_top3", "Trend10_E80", "Mom_etf_top3_core50"]:
            print(" ", s, {k.split('|', 1)[1] if k.startswith('amira_etf|') else 'USD|' + k.split('|', 1)[1]:
                           (v if isinstance(v, str) else (round(v['p10'], 4), round(v['maxdd_worst'], 3), round(v['breach_rate'], 3), v['eligible']))
                           for k, v in d["focus"][s].items()})
        print("  minimax 6 runs:", [(x["strategy"], x["regret_max_pt"]) for x in d["minimax_6_runs"]])
        print("  minimax 6 runs static:", d["n_static_eligible_all_6_runs"])
        print("  minimax CAD:", [(x["strategy"], x["regret_max_pt"], x["maxdd_worst"]) for x in d["minimax_cad_runs"]])
        print("  minimax CAD static:", [(x["strategy"], x["regret_max_pt"], x["p10_by_run_pct"], x["maxdd_worst"], x["equity_weight"]) for x in d["minimax_cad_runs_static_only"]])
        print("  traces:", d["traces"])


if __name__ == "__main__":
    main()
