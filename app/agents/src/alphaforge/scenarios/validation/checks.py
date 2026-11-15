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


def _look_ahead_check(pool: Pool, mixes: list[str], cut: str, label: str) -> dict:
    """Ajuste ``label`` sur ``pool``, puis sur une copie dont les mois > ``cut`` sont du bruit, et compare."""
    model_id, params = MODEL_SPECS[label]
    params = {**params, "n_init": 2} if label.startswith("hmm") else params
    clean_fit = fit(pool, model_id, fitted_through=cut, seed=7, params=params)
    corrupted = pool._subset(np.arange(pool.n))
    after = np.asarray(corrupted.dates > pd.Timestamp(cut).to_period("M").to_timestamp(how="end"))
    corrupted.returns[after] = np.random.default_rng(1).normal(0.0, 0.3, size=corrupted.returns[after].shape)
    corrupted.inflation[after] = 0.2
    corrupted_fit = fit(corrupted, model_id, fitted_through=cut, seed=7, params=params)
    clean_indices = clean_fit.simulate_indices(300, 120, rng_for(1, "la"))
    corrupted_indices = corrupted_fit.simulate_indices(300, 120, rng_for(1, "la"))
    clean_metrics = simulate_metrics(clean_fit, mixes, [1, 5, 10], 300, rng_for(2, "la"))["nominal"]
    corrupted_metrics = simulate_metrics(corrupted_fit, mixes, [1, 5, 10], 300, rng_for(2, "la"))["nominal"]
    same_info = json.dumps(clean_fit.info, sort_keys=True, default=str) == json.dumps(
        corrupted_fit.info, sort_keys=True, default=str
    )
    return {
        "model": label,
        "n_future_months_corrupted": int(after.sum()),
        "same_fit_info": same_info,
        "same_indices": bool(np.array_equal(clean_indices, corrupted_indices)),
        "same_metrics": bool(np.array_equal(clean_metrics, corrupted_metrics)),
        "max_index_le_cut": bool(clean_indices.max() < clean_fit.pool.n),
        "passed": bool(
            same_info
            and np.array_equal(clean_indices, corrupted_indices)
            and np.array_equal(clean_metrics, corrupted_metrics)
        ),
    }


def look_ahead_real(pools: dict[str, Pool], cuts=("1999-12", "2012-12")) -> list[dict]:
    """Corrompt les mois > cut et vérifie que ajustement, indices et métriques sont identiques."""
    out = []
    for family in ("CAD77", "USD1926"):
        pool = pools[family]
        mixes = list(_mixes_for(family).values())[:3]
        for cut in cuts:
            for label in ("sbb", "sbb_ca", "hmm_rs", "hmm_rs_ca"):
                out.append({"family": family, "cut": cut, **_look_ahead_check(pool, mixes, cut, label)})
    return out


def rising_rates(scores: pd.DataFrame) -> pd.DataFrame:
    """Fenêtres réalisées entièrement dans la hausse des taux : USD1926 et USD1953 origines >= 1965-12, fin <= 1981-12 ;
    CAD71 origines >= 1975-12, fin <= 1981-12. Mélanges obligataires."""
    bond_mixes = scores[scores["mix"].isin(["eq00_fi100", "eq30_fi70", "eq40_fi60"])].copy()
    origin_year = bond_mixes["origin"].str[:4].astype(int)
    end_year = origin_year + bond_mixes["H"]
    usd = bond_mixes["family"].isin(["USD1926", "USD1953"]) & (origin_year >= 1965)
    rising = (usd | ((bond_mixes["family"] == "CAD71") & (origin_year >= 1975))) & (end_year <= 1981)
    groups = bond_mixes[rising].groupby(["family", "mix", "model", "H"])
    out = groups.agg(
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
    episode = scores[
        scores["origin"].isin(["2020-12", "2021-12"])
        & scores["H"].isin([1, 3])
        & scores["mix"].isin(["eq00_fi100", "eq40_fi60", "eq70_fi30"])
    ]
    columns = [
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
    return episode[columns].sort_values(["family", "origin", "H", "mix", "model"]).reset_index(drop=True)


def _regime_split(pool: Pool, seed: int) -> dict:
    """Ajustement sur toute la fenêtre : régimes retenus et part de leur masse lissée avant et après 1953-04."""
    fitted = fit(pool, "hmm_rs", None, seed=seed, params=HMM_PARAMS)
    gamma = fitted.hmm.gamma
    before = np.asarray(pool.dates < pd.Timestamp("1953-04-30"))
    info = {k: fitted.info[k] for k in ("k", "bic", "expected_duration_months", "regime_share_months")}
    info["regime_monthly_vol"] = fitted.info["regime_monthly_vol"]
    if before.any():
        info["share_of_regime_mass_before_1953_04"] = np.round(gamma[before].sum(0) / gamma.sum(0), 4).tolist()
        info["regime_mix_before_1953_04"] = np.round(gamma[before].mean(0), 4).tolist()
        info["regime_mix_from_1953_04"] = np.round(gamma[~before].mean(0), 4).tolist()
        info["n_months_before_1953_04"] = int(before.sum())
    info["n_months"] = int(pool.n)
    info["window"] = f"{pool.window_start}..{pool.fitted_through}"
    return info


def _em_stability(pool: Pool, seed: int) -> list[dict]:
    """Même pool, autres départs de l'EM (n_init 3 du run small, graines 1 et 2)."""
    rows = []
    for n_init in (3, 6):
        for start_seed in (1, 2, seed):
            fitted = fit(pool, "hmm_rs", None, seed=start_seed, params={**HMM_PARAMS, "n_init": n_init})
            rows.append(
                {
                    "n_init": n_init,
                    "seed": start_seed,
                    "k": fitted.info["k"],
                    "bic": fitted.info["bic"],
                    "expected_duration_months": fitted.info["expected_duration_months"],
                    "bonds_vol_by_regime": fitted.info["regime_monthly_vol"]["BONDS"],
                }
            )
    return rows


def hmm_usd1926(pools: dict[str, Pool], seed: int) -> dict:
    """Ajustement sur toute la fenêtre USD1926 : part de la masse lissée de chaque régime avant et après 1953-04."""
    out = {family: _regime_split(pools[family], seed) for family in ("USD1926", "USD1953")}
    # Stabilité de l'EM : même pool, autres départs (n_init 3 du run small, graines 1 et 2).
    out["USD1926_em_stability"] = _em_stability(pools["USD1926"], seed)
    return out


def _large_drawdown_windows(dates: pd.DatetimeIndex, log_returns: np.ndarray, horizon: int) -> dict:
    """Fenêtres glissantes de H ans dont la perte max. dépasse 20 % : fréquence, pire perte, années de début."""
    outcomes = rolling_outcomes(log_returns, horizon)
    hit = outcomes["mdd"] > 0.20
    starts = dates[: len(outcomes["mdd"])][hit]
    years = sorted({date.year for date in starts})
    return {
        "n_windows": int(len(outcomes["mdd"])),
        "freq_mdd_gt_20": float(hit.mean()),
        "max_mdd": float(outcomes["mdd"].max()),
        "start_years_of_windows_mdd_gt_20": _ranges(years),
    }


def historical_bond_mdd(pools: dict[str, Pool]) -> pd.DataFrame:
    """Repères historiques : fréquence des fenêtres glissantes de 5 ans avec perte max. > 20 %, par mélange, et
    dates de début des fenêtres concernées."""
    rows = []
    for family in ("CAD77", "CAD71", "USD1926"):
        pool = pools[family]
        mixes = _mixes_for(family)
        log_returns = hist_log_returns(pool, weight_matrix(pool, list(mixes.values())))["nominal"]
        for j, label in enumerate(mixes):
            for horizon in (3, 5):
                windows = _large_drawdown_windows(pool.dates, log_returns[:, j], horizon)
                rows.append({"family": family, "mix": label, "H": horizon, **windows})
    return pd.DataFrame(rows)


def _ranges(years: list[int]) -> str:
    """Années consécutives regroupées : ``[1974, 1975, 1980]`` donne ``"1974-1975,1980"``."""
    if not years:
        return ""
    spans, first, last = [], years[0], years[0]
    for year in years[1:]:
        if year == last + 1:
            last = year
        else:
            spans.append(f"{first}-{last}" if first != last else str(first))
            first = last = year
    spans.append(f"{first}-{last}" if first != last else str(first))
    return ",".join(spans)


def _equity_bond_line(table: pd.DataFrame) -> pd.DataFrame:
    """Lignes P(perte max. > x) nominales des mélanges actions/obligations purs, actions CAD77 réparties 50/50."""
    table = table[(table["basis"] == "nominal") & table["metric"].str.startswith("p_mdd_gt_")]
    weights = table["mix_id"].map(parse_mix_id)
    table = table.assign(
        ca=weights.map(lambda mix: mix.get("CA_EQ", 0)),
        us=weights.map(lambda mix: mix.get("US_MKT", 0)),
        bd=weights.map(lambda mix: mix.get("BONDS", 0)),
        rest=weights.map(lambda mix: mix.get("CASH", 0) + mix.get("GOLD", 0) + mix.get("CRYPTO", 0)),
    )
    table = table[(table["rest"] == 0) & ~table["mix_id"].str.contains("-cr")]
    table["eq"] = (table["ca"] + table["us"]).round(2)
    return table[(table["family"] != "CAD77") | ((table["ca"] - table["us"]).abs() < 1e-9)]


def monotonicity_reference(ref_table: Path) -> pd.DataFrame:
    """Dans la table du run de référence : pour chaque (modèle, famille, H, seuil), P(perte max. > x) le long de la
    ligne actions/obligations (cash et or nuls, actions CAD77 réparties 50/50). Renvoie les violations de monotonie
    (une valeur qui baisse quand la part d'actions augmente), avec la part d'actions du minimum."""
    table = pd.read_parquet(
        ref_table, columns=["model_id", "family", "mix_id", "horizon_years", "basis", "metric", "value"]
    )
    rows = []
    line = _equity_bond_line(table)
    for (model_id, family, horizon, metric), unsorted in line.groupby(
        ["model_id", "family", "horizon_years", "metric"]
    ):
        group = unsorted.sort_values("eq")
        values = group["value"].to_numpy()
        equity_shares = group["eq"].to_numpy()
        drops = np.flatnonzero(np.diff(values) < -0.005)
        rows.append(
            {
                "model_id": model_id,
                "family": family,
                "H": int(horizon),
                "metric": metric,
                "equity_shares": ",".join(f"{share:.2f}" for share in equity_shares),
                "values": ",".join(f"{x:.3f}" for x in values),
                "monotone_increasing": bool(len(drops) == 0),
                "argmin_equity_share": float(equity_shares[int(np.argmin(values))]),
            }
        )
    return pd.DataFrame(rows)


def sensitivity_duplicates(ref_dir: Path) -> dict:
    path = ref_dir / "sensitivity_block_length.csv"
    if not path.exists():
        return {}
    sensitivity = pd.read_csv(path)
    key = ["pool", "mean_block", "mix_id", "horizon_years", "basis", "metric"]
    duplicated = sensitivity.duplicated(key, keep=False)
    return {
        "rows": int(len(sensitivity)),
        "duplicated_rows": int(duplicated.sum()),
        "duplicated_mix_ids": sorted(sensitivity.loc[duplicated, "mix_id"].unique().tolist()),
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
