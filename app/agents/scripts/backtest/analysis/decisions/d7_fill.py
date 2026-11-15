"""D7 (Mateo, plancher d'actions réparti sur les secteurs) : effet d'une règle de remplissage « au prorata de la
cible, cœur large par défaut » comparée à la projection euclidienne actuelle de engine.constraints.

Pourquoi : `ConstraintSet.project` minimise ||w - w0||² ; la projection sur un plancher de groupe
(Σ_{i∈G} w_i ≥ m) ajoute alors le MÊME montant à chaque membre admissible du groupe, y compris aux actifs que la
stratégie avait mis à 0 (les 11 secteurs exclus de `risk_parity_iv36`). Variante testée ici (RUNTIME, le fichier
engine/constraints.py n'est PAS modifié) : moindres carrés pondérés min Σ (w_i - w0_i)² / s_i avec
s_i = max(w0_i, ε_i), ε_i = 1e-3 pour les actifs tagués `broad_market`, 1e-6 sinon. Une contrainte de plancher
est alors comblée au prorata des poids que la stratégie a choisis (et sur le cœur large si la cible n'a aucune
action) ; les actifs exclus par la stratégie ne reçoivent quasiment rien.

Runs sans ORACLE, roulant 10 ans, stratégies `risk_parity_iv36` et `min_variance_60`, trois ères ESG de Mateo.
Écrit results/decisions_analysis/d7_fill.json (+ traces results/dec_mateo_*_{euclid,prorata}/).
SIMULATION UNIQUEMENT, pas un conseil.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from alphaforge.finance.backtest.paths import DEFAULT_DATA_DIR

HERE = Path(__file__).resolve().parent
BT = HERE.parents[1]
sys.path.insert(0, str(BT / "analysis" / "mateo"))
import common  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.optimize import minimize  # noqa: E402

import alphaforge.finance.backtest.constraints as C  # noqa: E402
from alphaforge.finance.backtest.data import load_assets  # noqa: E402

OUT = BT / "results" / "decisions_analysis" / "d7_fill.json"
_orig_project = C.ConstraintSet.project


def project_prorata(self, w0):
    w0 = np.nan_to_num(np.asarray(w0, float))
    if self.is_feasible(w0, tol=1e-9):
        return w0
    cat = load_assets()
    broad = np.array(["broad_market" in cat.at[a, "tag_list"] for a in self.assets])
    s = np.maximum(w0, np.where(broad, 1e-3, 1e-6))
    f = lambda w: 0.5 * np.sum((w - w0) ** 2 / s)  # noqa: E731
    g = lambda w: (w - w0) / s  # noqa: E731
    start = np.clip(w0, self.lb, self.ub)
    start = start / start.sum() if start.sum() > 0 else self.feasible_point()
    res = minimize(f, start, jac=g, bounds=self.bounds(), constraints=self.scipy_constraints(), method="SLSQP",
                   options={"ftol": 1e-14, "maxiter": 1000})
    w = res.x
    if not self.is_feasible(w, tol=1e-5):
        return _orig_project(self, w0)
    w = np.clip(w, self.lb, self.ub)
    return w / w.sum()


def summarize(rows: pd.DataFrame, universe: list[str], s: str) -> dict:
    d = rows[rows["strategy"] == s]
    sectors = [a for a in universe if a.startswith("US_IND_")]
    eq = [a for a in universe if a in ("CA_EQ", "US_MKT", "US_MKT_XEN")] + sectors
    return {"n_windows": int(len(d)),
            "p10_real": round(float(np.quantile(d["ann_real_return"], 0.10)), 4),
            "median_real": round(float(d["ann_real_return"].median()), 4),
            "worst_maxdd": round(float(d["max_drawdown"].max()), 3),
            "breach_rate": round(float((d["n_breaches"] > 0).mean()), 3),
            "equity_mean": round(float(np.mean([sum(w.get(a, 0) for a in eq) for w in d["avg_weights"]])), 3),
            "sector_proxies_mean": round(float(np.mean([sum(w.get(a, 0) for a in sectors) for w in d["avg_weights"]])), 3),
            "core_us_mkt_xen_mean": round(float(np.mean([w.get("US_MKT_XEN", 0) for w in d["avg_weights"]])), 3),
            "ca_eq_mean": round(float(np.mean([w.get("CA_EQ", 0) for w in d["avg_weights"]])), 3),
            "gold_mean": round(float(np.mean([w.get("GOLD", 0) for w in d["avg_weights"]])), 3)}


def active_share_equal_sector_fill(date: str = "2026-09-30") -> dict:
    """Equity pocket produced by the equal fill in USD 1926+ (≈0.084 core + 11 × 0.029 sectors, reports/mateo.md §4)
    against the cap-weighted ex-energy market at `date` (KF look-through shares)."""
    lt = pd.read_parquet(DEFAULT_DATA_DIR / "lookthrough_us_mkt.parquet").set_index("date")
    row = lt.loc[pd.Timestamp(date)]
    sec = [c for c in lt.columns if c.startswith("US_IND_") and c != "US_IND_ENRGY"]
    cap = row[sec] / row[sec].sum()  # ex-energy cap weights
    pocket = pd.Series(0.029, index=sec)
    core = 0.084
    tot = core + pocket.sum()
    ew = (core * cap + pocket) / tot  # look-through of the pocket: core is cap-weighted
    act = 0.5 * float((ew - cap).abs().sum())
    return {"date": date, "pocket_total": round(tot, 3), "active_share_vs_cap_ex_energy": round(act, 3),
            "buseq_cap": round(float(cap["US_IND_BUSEQ"]), 3), "buseq_in_pocket": round(float(ew["US_IND_BUSEQ"]), 3),
            "utils_cap": round(float(cap["US_IND_UTILS"]), 3), "utils_in_pocket": round(float(ew["US_IND_UTILS"]), 3),
            "telcm_cap": round(float(cap["US_IND_TELCM"]), 3), "telcm_in_pocket": round(float(ew["US_IND_TELCM"]), 3)}


def main() -> None:
    out = {"disclaimer": "SIMULATION ONLY", "method": __doc__.split("\n\n")[1], "runs": {},
           "active_share": active_share_equal_sector_fill()}
    print(out["active_share"], flush=True)
    for prof_id in ["mateo_usd_long_esg", "mateo_usd_gold_esg", "mateo_cad_esg"]:
        base = common.load_profile(prof_id)
        for rule in ["euclid", "prorata"]:
            C.ConstraintSet.project = _orig_project if rule == "euclid" else project_prorata
            p = copy.deepcopy(base)
            p["id"] = f"dec_{prof_id}_{rule}"
            p["strategies"] = [s for s in p["strategies"] if s["name"] in ("risk_parity_iv36", "min_variance_60")]
            r = common.run_profile(p, "rolling", 10, None, None, 12, False, verbose=False)
            for s in ["risk_parity_iv36", "min_variance_60"]:
                rec = summarize(r["rows"], p["universe"], s)
                rec["trace"] = str(r["trace_path"])
                out["runs"].setdefault(prof_id, {}).setdefault(s, {})[rule] = rec
                print(prof_id, rule, s, rec, flush=True)
    C.ConstraintSet.project = _orig_project
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
