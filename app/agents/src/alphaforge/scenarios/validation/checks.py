"""Contrôles ciblés demandés par l'auteur des modèles (volet B) :

(i)   risque obligataire en période de hausse des taux (1965-1981 USD, 1975-1981 CAD71) et en 2021-2023 ;
(ii)  sensibilité à la borne de 24 mois de la longueur moyenne de bloc (lu dans les scores walk-forward) ;
(iii) HMM USD1926 : part des régimes avant / après 1953-04 (fin des obligations du taux long de Shiller) ;
(iv)  sbb contre sbb_ca (lu dans les scores) ;
(v)   monotonie de P(perte max. > x) selon la part d'actions dans le run de référence, et repères historiques
      (100 % obligations contre 40/60) ;
plus un contrôle anti look-ahead sur les **vraies** données (mois postérieurs remplacés par du bruit).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..data import Pool
from ..engine import hist_log_returns, simulate_metrics, weight_matrix
from ..models import fit, rng_for
from ..schema import METRICS, parse_mix_id
from .scoring import rolling_outcomes
from .walkforward import HMM_PARAMS, MODEL_SPECS, _mixes_for


def look_ahead_real(pools: dict[str, Pool], cuts=("1999-12", "2012-12")) -> list[dict]:
    """Corrompt les mois > cut et vérifie que ajustement, indices et métriques sont identiques."""
    out = []
    for fam in ("CAD77", "USD1926"):
        pool = pools[fam]
        mixes = list(_mixes_for(fam).values())[:3]
        for cut in cuts:
            for label in ("sbb", "sbb_ca", "hmm_rs", "hmm_rs_ca"):
                model_id, params = MODEL_SPECS[label]
                params = {**params, "n_init": 2} if label.startswith("hmm") else params
                f1 = fit(pool, model_id, fitted_through=cut, seed=7, params=params)
                bad = pool._subset(np.arange(pool.n))
                after = np.asarray(bad.dates > pd.Timestamp(cut).to_period("M").to_timestamp(how="end"))
                bad.R[after] = np.random.default_rng(1).normal(0.0, 0.3, size=bad.R[after].shape)
                bad.infl[after] = 0.2
                f2 = fit(bad, model_id, fitted_through=cut, seed=7, params=params)
                i1 = f1.simulate_indices(300, 120, rng_for(1, "la"))
                i2 = f2.simulate_indices(300, 120, rng_for(1, "la"))
                m1 = simulate_metrics(f1, mixes, [1, 5, 10], 300, rng_for(2, "la"))["nominal"]
                m2 = simulate_metrics(f2, mixes, [1, 5, 10], 300, rng_for(2, "la"))["nominal"]
                same_info = json.dumps(f1.info, sort_keys=True, default=str) == json.dumps(
                    f2.info, sort_keys=True, default=str
                )
                out.append(
                    {
                        "family": fam,
                        "cut": cut,
                        "model": label,
                        "n_future_months_corrupted": int(after.sum()),
                        "same_fit_info": same_info,
                        "same_indices": bool(np.array_equal(i1, i2)),
                        "same_metrics": bool(np.array_equal(m1, m2)),
                        "max_index_le_cut": bool(i1.max() < f1.pool.n),
                        "passed": bool(same_info and np.array_equal(i1, i2) and np.array_equal(m1, m2)),
                    }
                )
    return out


def rising_rates(scores: pd.DataFrame) -> pd.DataFrame:
    """Fenêtres réalisées entièrement dans la hausse des taux : USD1926 et USD1953 origines >= 1965-12, fin <= 1981-12 ;
    CAD71 origines >= 1975-12, fin <= 1981-12. Mélanges obligataires."""
    s = scores[scores["mix"].isin(["eq00_fi100", "eq30_fi70", "eq40_fi60"])].copy()
    y0 = s["origin"].str[:4].astype(int)
    end = y0 + s["H"]
    usd = s["family"].isin(["USD1926", "USD1953"]) & (y0 >= 1965)
    sel = (usd | ((s["family"] == "CAD71") & (y0 >= 1975))) & (end <= 1981)
    s = s[sel]
    g = s.groupby(["family", "mix", "model", "H"])
    out = g.agg(
        n=("origin", "size"),
        origins=("origin", lambda x: f"{x.min()}..{x.max()}"),
        mean_pit_ret=("pit_ret", "mean"),
        mean_pit_mdd=("pit_mdd", "mean"),
        cov80_ret=("in80_ret", "mean"),
        below_q10_ret=("below_ret_q10", "mean"),
        exc_q90_mdd=("exc_mdd_q90", "mean"),
        mean_y_ret=("y_ret", "mean"),
        mean_q10_ret=("ret_q10", "mean"),
        mean_y_mdd=("y_mdd", "mean"),
        mean_q90_mdd=("mdd_q90", "mean"),
    )
    return out.reset_index()


def recent_episode(scores: pd.DataFrame) -> pd.DataFrame:
    """2021-2023 : origines 2020-12 (H = 1, 3) et 2021-12 (H = 1, 3), mélanges obligataires et 70/30."""
    s = scores[
        scores["origin"].isin(["2020-12", "2021-12"])
        & scores["H"].isin([1, 3])
        & scores["mix"].isin(["eq00_fi100", "eq40_fi60", "eq70_fi30"])
    ]
    cols = [
        "family",
        "model",
        "origin",
        "H",
        "mix",
        "y_ret",
        "ret_q05",
        "ret_q10",
        "pit_ret",
        "y_mdd",
        "mdd_q90",
        "mdd_q95",
        "pit_mdd",
        "p_mdd_gt_10",
        "p_mdd_gt_20",
        "p_loss_gt_10",
    ]
    return s[cols].sort_values(["family", "origin", "H", "mix", "model"]).reset_index(drop=True)


def hmm_usd1926(pools: dict[str, Pool], seed: int) -> dict:
    """Ajustement sur toute la fenêtre USD1926 : part de la masse lissée de chaque régime avant et après 1953-04."""
    out = {}
    for fam in ("USD1926", "USD1953"):
        pool = pools[fam]
        f = fit(pool, "hmm_rs", None, seed=seed, params=HMM_PARAMS)
        g = f.hmm.gamma
        pre = np.asarray(pool.dates < pd.Timestamp("1953-04-30"))
        info = {k: f.info[k] for k in ("k", "bic", "expected_duration_months", "regime_share_months")}
        info["regime_monthly_vol"] = f.info["regime_monthly_vol"]
        if pre.any():
            info["share_of_regime_mass_before_1953_04"] = np.round(g[pre].sum(0) / g.sum(0), 4).tolist()
            info["regime_mix_before_1953_04"] = np.round(g[pre].mean(0), 4).tolist()
            info["regime_mix_from_1953_04"] = np.round(g[~pre].mean(0), 4).tolist()
            info["n_months_before_1953_04"] = int(pre.sum())
        info["n_months"] = int(pool.n)
        info["window"] = f"{pool.window_start}..{pool.fitted_through}"
        out[fam] = info
    # Stabilité de l'EM : même pool, autres départs (n_init 3 du run small, graines 1 et 2).
    stab = []
    for n_init in (3, 6):
        for sd in (1, 2, seed):
            f = fit(pools["USD1926"], "hmm_rs", None, seed=sd, params={**HMM_PARAMS, "n_init": n_init})
            stab.append(
                {
                    "n_init": n_init,
                    "seed": sd,
                    "k": f.info["k"],
                    "bic": f.info["bic"],
                    "expected_duration_months": f.info["expected_duration_months"],
                    "bonds_vol_by_regime": f.info["regime_monthly_vol"]["BONDS"],
                }
            )
    out["USD1926_em_stability"] = stab
    return out


def historical_bond_mdd(pools: dict[str, Pool]) -> pd.DataFrame:
    """Repères historiques : fréquence des fenêtres glissantes de 5 ans avec perte max. > 20 %, par mélange, et
    dates de début des fenêtres concernées."""
    rows = []
    for fam in ("CAD77", "CAD71", "USD1926"):
        pool = pools[fam]
        mixes = _mixes_for(fam)
        W = weight_matrix(pool, list(mixes.values()))
        lr = hist_log_returns(pool, W)["nominal"]
        for m, lab in enumerate(mixes):
            for H in (3, 5):
                ro = rolling_outcomes(lr[:, m], H)
                hit = ro["mdd"] > 0.20
                starts = pool.dates[: len(ro["mdd"])][hit]
                years = sorted({d.year for d in starts})
                rows.append(
                    {
                        "family": fam,
                        "mix": lab,
                        "H": H,
                        "n_windows": int(len(ro["mdd"])),
                        "freq_mdd_gt_20": float(hit.mean()),
                        "max_mdd": float(ro["mdd"].max()),
                        "start_years_of_windows_mdd_gt_20": _ranges(years),
                    }
                )
    return pd.DataFrame(rows)


def _ranges(years: list[int]) -> str:
    if not years:
        return ""
    out, a, b = [], years[0], years[0]
    for y in years[1:]:
        if y == b + 1:
            b = y
        else:
            out.append(f"{a}-{b}" if a != b else str(a))
            a = b = y
    out.append(f"{a}-{b}" if a != b else str(a))
    return ",".join(out)


def monotonicity_reference(ref_table: Path) -> pd.DataFrame:
    """Dans la table du run de référence : pour chaque (modèle, famille, H, seuil), P(perte max. > x) le long de la
    ligne actions/obligations (cash et or nuls, actions CAD77 réparties 50/50). Renvoie les violations de monotonie
    (une valeur qui baisse quand la part d'actions augmente), avec la part d'actions du minimum."""
    t = pd.read_parquet(
        ref_table, columns=["model_id", "family", "mix_id", "horizon_years", "basis", "metric", "value"]
    )
    t = t[(t["basis"] == "nominal") & t["metric"].str.startswith("p_mdd_gt_")]
    w = t["mix_id"].map(parse_mix_id)
    t = t.assign(
        ca=w.map(lambda d: d.get("CA_EQ", 0)),
        us=w.map(lambda d: d.get("US_MKT", 0)),
        bd=w.map(lambda d: d.get("BONDS", 0)),
        rest=w.map(lambda d: d.get("CASH", 0) + d.get("GOLD", 0) + d.get("CRYPTO", 0)),
    )
    t = t[(t["rest"] == 0) & ~t["mix_id"].str.contains("-cr")]
    t["eq"] = (t["ca"] + t["us"]).round(2)
    line = t[(t["family"] != "CAD77") | ((t["ca"] - t["us"]).abs() < 1e-9)]
    rows = []
    for (mid, fam, H, metric), g in line.groupby(["model_id", "family", "horizon_years", "metric"]):
        g = g.sort_values("eq")
        v = g["value"].to_numpy()
        eqs = g["eq"].to_numpy()
        drops = np.flatnonzero(np.diff(v) < -0.005)
        rows.append(
            {
                "model_id": mid,
                "family": fam,
                "H": int(H),
                "metric": metric,
                "equity_shares": ",".join(f"{e:.2f}" for e in eqs),
                "values": ",".join(f"{x:.3f}" for x in v),
                "monotone_increasing": bool(len(drops) == 0),
                "argmin_equity_share": float(eqs[int(np.argmin(v))]),
            }
        )
    return pd.DataFrame(rows)


def sensitivity_duplicates(ref_dir: Path) -> dict:
    p = ref_dir / "sensitivity_block_length.csv"
    if not p.exists():
        return {}
    s = pd.read_csv(p)
    key = ["pool", "mean_block", "mix_id", "horizon_years", "basis", "metric"]
    dup = s.duplicated(key, keep=False)
    return {
        "rows": int(len(s)),
        "duplicated_rows": int(dup.sum()),
        "duplicated_mix_ids": sorted(s.loc[dup, "mix_id"].unique().tolist()),
    }


__all__ = [
    "METRICS",
    "hmm_usd1926",
    "historical_bond_mdd",
    "look_ahead_real",
    "monotonicity_reference",
    "recent_episode",
    "rising_rates",
    "sensitivity_duplicates",
]
