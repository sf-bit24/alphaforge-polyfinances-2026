"""D7 bis : la règle inter-ères de Mateo (violations ≤ 25 % dans chaque ère, maximiser le pire p10) avec
(a) la projection actuelle, (b) le remplissage au prorata (d7_fill.project_prorata) et (c) prorata + plafond de
groupe « proxys sectoriels US ≤ 10 % » (statut « actions US : limité »). Roulant 10 ans, sans ORACLE, stratégies
risk_parity_iv36, min_variance_60, mean_var_60_ra10, static_eq40, static_eq60.
Écrit results/decisions_analysis/d7b_sector_cap.json. SIMULATION UNIQUEMENT. Le moteur n'est pas modifié.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import d7_fill as F  # noqa: E402  (imports analysis/mateo/common -> data_ext + look-through wrapper)

C, common = F.C, F.common
OUT = BT / "results" / "decisions_analysis" / "d7b_sector_cap.json"
STRATS = ["risk_parity_iv36", "min_variance_60", "mean_var_60_ra10", "static_eq40", "static_eq60"]
SECTOR_CAP = 0.10


def main() -> None:
    out = {"disclaimer": "SIMULATION ONLY", "sector_cap": SECTOR_CAP, "variants": {}}
    for variant in ["euclid", "prorata", "prorata_cap10"]:
        C.ConstraintSet.project = F._orig_project if variant == "euclid" else F.project_prorata
        for prof_id in ["mateo_usd_long_esg", "mateo_usd_gold_esg", "mateo_cad_esg"]:
            p = copy.deepcopy(common.load_profile(prof_id))
            p["id"] = f"dec_{prof_id}_{variant}_x"
            p["strategies"] = [s for s in p["strategies"] if s["name"] in STRATS]
            if variant == "prorata_cap10":
                p["constraints"]["groups"] = list(p["constraints"]["groups"]) + [
                    {"name": "sector_proxies_cap", "classes": ["sector_us"], "max": SECTOR_CAP}]
            r = common.run_profile(p, "rolling", 10, None, None, 12, False, verbose=False)
            for s in STRATS:
                rec = F.summarize(r["rows"], p["universe"], s)
                rec["trace"] = str(r["trace_path"])
                out["variants"].setdefault(variant, {}).setdefault(s, {})[prof_id] = rec
                print(variant, prof_id, s, {k: rec[k] for k in ["p10_real", "breach_rate", "sector_proxies_mean",
                                                                 "core_us_mkt_xen_mean", "worst_maxdd"]}, flush=True)
    C.ConstraintSet.project = F._orig_project
    # inter-era rule
    for variant, by_s in out["variants"].items():
        rank = []
        for s, by_era in by_s.items():
            ok = all(v["breach_rate"] <= 0.25 for v in by_era.values())
            rank.append({"strategy": s, "eligible_all_eras": ok, "worst_p10": min(v["p10_real"] for v in by_era.values()),
                         "max_breach": max(v["breach_rate"] for v in by_era.values()),
                         "sector_proxies_usd_long": by_era["mateo_usd_long_esg"]["sector_proxies_mean"]})
        rank.sort(key=lambda d: (not d["eligible_all_eras"], -d["worst_p10"]))
        out.setdefault("inter_era", {})[variant] = rank
        print(variant, "->", [(d["strategy"], d["worst_p10"], d["eligible_all_eras"]) for d in rank[:3]], flush=True)
    OUT.write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
