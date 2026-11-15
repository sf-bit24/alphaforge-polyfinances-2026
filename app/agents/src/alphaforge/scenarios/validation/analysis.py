"""Agrégation des scores walk-forward : couverture, PIT/KS sur sous-ensembles non chevauchants, CRPS et score de
Brier avec intervalles par bootstrap par blocs sur les origines.

Dépendance entre observations : avec des origines espacées de 12 mois, deux fenêtres de H ans se chevauchent sur
H − 1 ans. Deux traitements, toujours indiqués dans les sorties :

- **KS / PIT** : test sur des sous-ensembles d'origines espacées de H ans (aucun chevauchement) ; on donne la
  p-valeur du sous-ensemble de décalage 0 et la plus petite p-valeur parmi les H décalages (non corrigée) ;
- **moyennes** (couverture, CRPS, Brier) : estimation sur toutes les origines, intervalle à 90 % par bootstrap par
  blocs mobiles circulaire sur la suite des origines, blocs de ``max(2, H)`` origines ; les mélanges d'une même
  origine sont rééchantillonnés ensemble (dépendance entre mélanges conservée).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..models import rng_for
from .scoring import block_ci, ks_uniform, moving_block_bootstrap
from .walkforward import LOSS_EVENTS, MDD_EVENTS

EVENTS = [f"loss_gt_{x:02d}" for x in LOSS_EVENTS] + [f"mdd_gt_{x:02d}" for x in MDD_EVENTS]
CASH_MIX = "eq00_cs100"


def _block(H: int) -> int:
    return max(2, int(H))


def _ks_nonoverlap(df: pd.DataFrame, col: str, H: int) -> dict:
    origins = sorted(df["origin"].unique())
    pvals, d0, p0, n0 = [], np.nan, np.nan, 0
    for off in range(H):
        sub = set(origins[off::H])
        d, p, n = ks_uniform(df.loc[df["origin"].isin(sub), col].to_numpy())
        if off == 0:
            d0, p0, n0 = d, p, n
        if np.isfinite(p):
            pvals.append(p)
    return {
        f"ks_{col}_D": d0,
        f"ks_{col}_p": p0,
        f"ks_{col}_n": n0,
        f"ks_{col}_pmin_offsets": float(min(pvals)) if pvals else np.nan,
    }


def per_mix_summary(scores: pd.DataFrame, n_boot: int, seed: int) -> pd.DataFrame:
    """Une ligne par (famille, modèle, mélange, H)."""
    out = []
    hist = scores[scores["model"] == "hist_emp"].set_index(["family", "mix", "H", "origin"])
    for (fam, model, mix, H), g in scores.groupby(["family", "model", "mix", "H"], sort=True):
        g = g.sort_values("origin")
        rng = rng_for(seed, "agg", fam, model, mix, int(H))
        rec = {"family": fam, "model": model, "mix": mix, "mix_id": g["mix_id"].iloc[0], "H": int(H)}
        rec["n_origins"] = len(g)
        rec["n_nonoverlap"] = int(np.ceil(len(g) / H))
        rec["first_origin"], rec["last_origin"] = g["origin"].iloc[0], g["origin"].iloc[-1]
        for col in ("in80_ret", "in90_ret", "in80_mdd", "in90_mdd", "exc_mdd_q90", "below_ret_q10"):
            m, lo, hi = block_ci(g[col].to_numpy(), _block(H), n_boot, rng)
            rec[col], rec[col + "_lo"], rec[col + "_hi"] = m, lo, hi
        for col in ("crps_ret", "crps_mdd", "pin_ret_q05", "pin_mdd_q90"):
            rec[col] = float(g[col].mean())
        # score de compétence CRPS contre hist_emp, sur les origines communes
        key = [(fam, mix, H, o) for o in g["origin"]]
        common = hist.index.intersection(pd.MultiIndex.from_tuples(key))
        if len(common) >= 3 and model != "hist_emp":
            gm = g.set_index("origin").loc[[k[3] for k in common]]
            hm = hist.loc[common]
            for col in ("crps_ret", "crps_mdd"):
                a, b = gm[col].to_numpy(), hm[col].to_numpy()
                idx = moving_block_bootstrap(len(a), _block(H), n_boot, rng)
                ratio = a[idx].mean(axis=1) / np.maximum(b[idx].mean(axis=1), 1e-12)
                rec[col + "_skill"] = float(1.0 - a.mean() / max(b.mean(), 1e-12))
                rec[col + "_skill_lo"] = float(1.0 - np.quantile(ratio, 0.95))
                rec[col + "_skill_hi"] = float(1.0 - np.quantile(ratio, 0.05))
        for ev in EVENTS:
            p, o = g["p_" + ev].to_numpy(), g["o_" + ev].to_numpy()
            rec["brier_" + ev] = float(np.mean((p - o) ** 2))
            rec["pbar_" + ev] = float(p.mean())
            rec["obar_" + ev] = float(o.mean())
        if model != "stress_2022":
            rec.update(_ks_nonoverlap(g, "pit_ret", int(H)))
            rec.update(_ks_nonoverlap(g, "pit_mdd", int(H)))
        out.append(rec)
    return pd.DataFrame(out)


def pooled_summary(scores: pd.DataFrame, n_boot: int, seed: int) -> pd.DataFrame:
    """Une ligne par (famille, modèle, H), moyennes sur les mélanges non triviaux.

    - rendement : les 6 mélanges (le cash teste l'hypothèse de niveau des taux) ;
    - perte maximale et événements : sans le cash (perte maximale nominale toujours nulle, triviale).
    Bootstrap : blocs d'origines, tous les mélanges d'une origine ensemble.
    """
    out = []
    hist = scores[scores["model"] == "hist_emp"]
    for (fam, model, H), g in scores.groupby(["family", "model", "H"], sort=True):
        rng = rng_for(seed, "pooled", fam, model, int(H))
        origins = sorted(g["origin"].unique())
        o_pos = {o: i for i, o in enumerate(origins)}
        idx = moving_block_bootstrap(len(origins), _block(H), n_boot, rng)

        def stat(col, frame, idx=idx, o_pos=o_pos, origins=origins):
            # matrice origines × mélanges -> moyenne par origine, puis bootstrap sur les origines
            per_o = frame.groupby("origin")[col].mean().reindex(origins).to_numpy()
            ok = np.isfinite(per_o)
            m = float(np.nanmean(per_o)) if ok.any() else np.nan
            boots = np.nanmean(per_o[idx], axis=1)
            return m, float(np.nanquantile(boots, 0.05)), float(np.nanquantile(boots, 0.95)), per_o

        rec = {"family": fam, "model": model, "H": int(H), "n_origins": len(origins)}
        rec["n_nonoverlap"] = int(np.ceil(len(origins) / H))
        nc = g[g["mix"] != CASH_MIX].assign(
            in80_ret_nc=lambda d: d["in80_ret"], below_ret_q10_nc=lambda d: d["below_ret_q10"]
        )
        for col, frame in (
            ("in80_ret", g),
            ("in90_ret", g),
            ("below_ret_q10", g),
            ("in80_mdd", nc),
            ("in90_mdd", nc),
            ("exc_mdd_q90", nc),
            ("in80_ret_nc", nc),
            ("below_ret_q10_nc", nc),
        ):
            m, lo, hi, _ = stat(col, frame)
            rec[col], rec[col + "_lo"], rec[col + "_hi"] = m, lo, hi
        # Brier moyen sur événements × mélanges non triviaux
        nc = nc.copy()
        nc["brier_all"] = np.mean([(nc["p_" + e] - nc["o_" + e]) ** 2 for e in EVENTS], axis=0)
        nc["brier_mdd20"] = (nc["p_mdd_gt_20"] - nc["o_mdd_gt_20"]) ** 2
        for col in ("brier_all", "brier_mdd20", "crps_ret", "crps_mdd"):
            m, lo, hi, _ = stat(col, nc if col != "crps_ret" else g)
            rec[col], rec[col + "_lo"], rec[col + "_hi"] = m, lo, hi
        # compétences contre hist_emp (origines communes, même bootstrap)
        if model != "hist_emp":
            hg = hist[(hist["family"] == fam) & (hist["H"] == H)]
            for col, frame_m, frame_h in (
                ("crps_ret", g, hg),
                ("crps_mdd", g[g["mix"] != CASH_MIX], hg[hg["mix"] != CASH_MIX]),
            ):
                a = frame_m.groupby("origin")[col].mean().reindex(origins).to_numpy()
                b = frame_h.groupby("origin")[col].mean().reindex(origins).to_numpy()
                ok = np.isfinite(a) & np.isfinite(b)
                if ok.sum() >= 3:
                    a2, b2 = a[ok], b[ok]
                    idx2 = moving_block_bootstrap(len(a2), _block(H), n_boot, rng)
                    ratio = a2[idx2].mean(axis=1) / b2[idx2].mean(axis=1)
                    rec[col + "_skill"] = float(1 - a2.mean() / b2.mean())
                    rec[col + "_skill_lo"] = float(1 - np.quantile(ratio, 0.95))
                    rec[col + "_skill_hi"] = float(1 - np.quantile(ratio, 0.05))
                    rec[col + "_skill_n"] = int(ok.sum())
            hb = hg[hg["mix"] != CASH_MIX].copy()
            if len(hb):
                hb["brier_all"] = np.mean([(hb["p_" + e] - hb["o_" + e]) ** 2 for e in EVENTS], axis=0)
                a = nc.groupby("origin")["brier_all"].mean().reindex(origins).to_numpy()
                b = hb.groupby("origin")["brier_all"].mean().reindex(origins).to_numpy()
                ok = np.isfinite(a) & np.isfinite(b)
                if ok.sum() >= 3:
                    rec["brier_skill"] = float(1 - a[ok].mean() / b[ok].mean())
        out.append(rec)
    return pd.DataFrame(out)


def reliability(scores: pd.DataFrame, bins=(0.0, 0.02, 0.10, 0.25, 0.50, 0.75, 1.0001)) -> pd.DataFrame:
    """Diagramme de fiabilité (tableau) par (famille, modèle, type d'événement), mélanges non triviaux, tous H."""
    rows = []
    nc = scores[(scores["mix"] != CASH_MIX) & (scores["model"] != "stress_2022")]
    for (fam, model), g in nc.groupby(["family", "model"]):
        for kind, evs in (
            ("loss", [e for e in EVENTS if e.startswith("loss")]),
            ("mdd", [e for e in EVENTS if e.startswith("mdd")]),
        ):
            p = np.concatenate([g["p_" + e].to_numpy() for e in evs])
            o = np.concatenate([g["o_" + e].to_numpy() for e in evs])
            b = np.digitize(p, bins) - 1
            for k in range(len(bins) - 1):
                m = b == k
                if m.sum() == 0:
                    continue
                rows.append(
                    {
                        "family": fam,
                        "model": model,
                        "events": kind,
                        "bin": f"[{bins[k]:.2f},{min(bins[k + 1], 1):.2f})",
                        "n": int(m.sum()),
                        "mean_forecast": float(p[m].mean()),
                        "observed_freq": float(o[m].mean()),
                    }
                )
    return pd.DataFrame(rows)


def pit_histogram(scores: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    """Histogramme PIT (descriptif, toutes origines, observations dépendantes) par (famille, modèle, H, variable)."""
    rows = []
    sc = scores[scores["model"] != "stress_2022"]
    for (fam, model, H), g in sc.groupby(["family", "model", "H"]):
        for var, frame in (("ret", g), ("mdd", g[g["mix"] != CASH_MIX])):
            u = frame["pit_" + var].to_numpy()
            counts, _ = np.histogram(u, bins=np.linspace(0, 1, n_bins + 1))
            rows.append(
                {"family": fam, "model": model, "H": int(H), "var": var, "n": int(len(u))}
                | {f"b{k}": int(c) for k, c in enumerate(counts)}
            )
    return pd.DataFrame(rows)


def ks_summary(per_mix: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """Nombre de mélanges (hors cash) dont le PIT est rejeté par KS au seuil ``alpha`` (sous-ensemble non chevauchant
    de décalage 0), par famille, modèle et H. Puissance faible quand n est petit (H = 10 : 3 à 7 fenêtres)."""
    pm = per_mix[(per_mix["mix"] != CASH_MIX) & (per_mix["model"] != "stress_2022")]
    rows = []
    for (fam, model, H), g in pm.groupby(["family", "model", "H"]):
        rows.append(
            {
                "family": fam,
                "model": model,
                "H": int(H),
                "n_mixes": len(g),
                "n_indep": int(g["ks_pit_ret_n"].median()),
                "rejects_ret": int((g["ks_pit_ret_p"] < alpha).sum()),
                "rejects_mdd": int((g["ks_pit_mdd_p"] < alpha).sum()),
            }
        )
    return pd.DataFrame(rows)
