"""Simulation vectorisée des résultats de portefeuille et métriques du schéma.

Hypothèses de calcul : rebalancement **mensuel** vers les poids cibles, sans frais ni impôts, sans flux. Avec des
poids fixes rebalancés chaque mois, le rendement du portefeuille au mois t vaut exactement ``w · r_t`` ; on calcule
donc une fois les rendements historiques de chaque mélange, puis on les rééchantillonne par les indices du générateur.

Toutes les trajectoires durent ``12 · max(horizons)`` mois ; l'horizon H lit les ``12·H`` premiers mois des mêmes
trajectoires (métriques cohérentes entre horizons).
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .data import Pool
from .models import Fitted, Model, rng_for
from .schema import COLUMN_NAMES, LOSS_THRESHOLDS, MDD_THRESHOLDS, METRICS, RET_QUANTILES, parse_mix_id

BASES = ("nominal", "real")


def weight_matrix(pool: Pool, mixes: Sequence[str]) -> np.ndarray:
    """Matrice ``(n_blocs, n_mélanges)`` ; erreur si un mélange utilise un bloc absent du pool."""
    W = np.zeros((len(pool.blocks), len(mixes)))
    for m, mid in enumerate(mixes):
        weights = parse_mix_id(mid)
        for block, w in weights.items():
            if w == 0:
                continue
            if block not in pool.blocks:
                raise ValueError(f"{mid} utilise {block}, absent du pool {pool.name}")
            W[pool.blocks.index(block), m] = w
    return W


def hist_log_returns(pool: Pool, W: np.ndarray) -> dict[str, np.ndarray]:
    """Log-rendements mensuels historiques de chaque mélange, nominaux et réels (déflatés par l'IPC du pool)."""
    port = pool.R @ W
    if (port <= -1).any():
        raise ValueError("rendement de portefeuille <= -100 %")
    lr = np.log1p(port)
    return {"nominal": lr, "real": lr - np.log1p(pool.infl)[:, None]}


def metrics_from_paths(
    lr_hist: np.ndarray, idx: np.ndarray, horizons: Sequence[int], mem_budget_mb: float = 512.0
) -> np.ndarray:
    """Métriques ``(n_metrics, n_horizons, n_mixes)`` (ordre de ``schema.METRICS``) pour une base.

    ``lr_hist`` : (T_hist, M) log-rendements ; ``idx`` : (N, T_sim) indices de mois.
    """
    n_paths, t_sim = idx.shape
    horizons = list(horizons)
    if 12 * max(horizons) > t_sim:
        raise ValueError("trajectoires trop courtes pour l'horizon demandé")
    n_mix = lr_hist.shape[1]
    out = np.empty((len(METRICS), len(horizons), n_mix))
    per_mix_bytes = n_paths * t_sim * 8 * 2
    chunk = max(1, int(mem_budget_mb * 1e6 // per_mix_bytes))
    loss_log = np.log1p(-np.array(LOSS_THRESHOLDS) / 100.0)
    mdd_log = -np.log1p(-np.array(MDD_THRESHOLDS) / 100.0)
    q = np.array(RET_QUANTILES) / 100.0
    year_ends = np.arange(12, t_sim + 1, 12) - 1
    for start in range(0, n_mix, chunk):
        sl = slice(start, min(start + chunk, n_mix))
        cum = lr_hist[:, sl][idx]  # (N, T, Mc)
        np.cumsum(cum, axis=1, out=cum)
        dd = np.maximum.accumulate(np.maximum(cum, 0.0), axis=1)
        dd -= cum  # log(pic / richesse) >= 0
        np.maximum.accumulate(dd, axis=1, out=dd)  # perte maximale en log jusqu'au mois t
        annual = np.diff(cum[:, year_ends, :], axis=1, prepend=0.0)  # log-rendements par année civile simulée
        for h_i, H in enumerate(horizons):
            m = 12 * H - 1
            log_w = cum[:, m, :]
            mdd = dd[:, m, :]
            row = 0
            ret = np.expm1(np.quantile(log_w, q, axis=0) / H)
            out[row : row + len(q), h_i, sl] = ret
            row += len(q)
            out[row, h_i, sl] = np.exp(np.quantile(log_w, 0.10, axis=0))
            row += 1
            out[row : row + 2, h_i, sl] = -np.expm1(-np.quantile(mdd, [0.5, 0.9], axis=0))
            row += 2
            a = np.expm1(annual[:, :H, :]).reshape(n_paths * H, -1)
            k = max(1, math.ceil(0.05 * a.shape[0]))
            tail = np.partition(a, k - 1, axis=0)[:k]
            out[row, h_i, sl] = -tail.mean(axis=0)
            row += 1
            for x in loss_log:
                out[row, h_i, sl] = (log_w < x).mean(axis=0)
                row += 1
            for x in mdd_log:
                out[row, h_i, sl] = (mdd > x).mean(axis=0)
                row += 1
        del cum, dd
    return out


def simulate_metrics(
    fitted: Fitted, mixes: Sequence[str], horizons: Sequence[int], n_paths: int, rng: np.random.Generator, **kw
) -> dict[str, np.ndarray]:
    """Simule ``n_paths`` trajectoires du modèle ajusté et renvoie les métriques par base."""
    W = weight_matrix(fitted.pool, mixes)
    lr = hist_log_returns(fitted.pool, W)
    idx = fitted.simulate_indices(n_paths, 12 * max(horizons), rng)
    return {basis: metrics_from_paths(lr[basis], idx, horizons, **kw) for basis in BASES}


@dataclass
class PoolResult:
    model_id: str
    pool: Pool
    mixes: list[str]
    horizons: list[int]
    point: dict[str, np.ndarray]
    ci_lo: dict[str, np.ndarray]
    ci_hi: dict[str, np.ndarray]
    n_paths: int
    n_boot: int
    fit_info: dict[str, Any]
    boot_info: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)


def run_pool(
    model: Model,
    pool: Pool,
    mixes: Sequence[str],
    horizons: Sequence[int],
    *,
    seed: int,
    n_paths: int,
    n_boot: int,
    n_paths_boot: int,
    fitted_through: str | None = None,
    ci_level: float = 0.90,
    mem_budget_mb: float = 512.0,
) -> PoolResult:
    """Ajuste, simule (estimation ponctuelle) puis bootstrap externe des paramètres (intervalles à ``ci_level``).

    Bootstrap externe fondé sur le modèle : pour b = 1..B, pseudo-historique de même longueur tiré du modèle ajusté,
    réajustement (longueur de bloc, ou HMM à K fixé), puis ``n_paths_boot`` trajectoires. L'intervalle est formé
    des quantiles (1-ci)/2 et (1+ci)/2 des B valeurs. Il traduit l'incertitude d'estimation **dans** le modèle,
    pas l'incertitude sur le choix du modèle.
    """
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    fitted = model.fit(pool, fitted_through, rng=rng_for(seed, pool.name, model.model_id, "fit"))
    timings["fit_s"] = round(time.perf_counter() - t0, 3)
    t0 = time.perf_counter()
    point = simulate_metrics(
        fitted, mixes, horizons, n_paths, rng_for(seed, pool.name, model.model_id, "sim"), mem_budget_mb=mem_budget_mb
    )
    timings["simulate_s"] = round(time.perf_counter() - t0, 3)
    t0 = time.perf_counter()
    boots: dict[str, list[np.ndarray]] = {b: [] for b in BASES}
    boot_summ: list[Any] = []
    for b in range(n_boot):
        rng_b = rng_for(seed, pool.name, model.model_id, "boot", b)
        pseudo = fitted.pseudo_history(rng_b)
        refit = model.refit(fitted, pseudo, rng_b)
        vals = simulate_metrics(refit, mixes, horizons, n_paths_boot, rng_b, mem_budget_mb=mem_budget_mb)
        for basis in BASES:
            boots[basis].append(vals[basis])
        boot_summ.append(refit.mean_block if refit.hmm is None else refit.hmm.params.k)
    timings["bootstrap_s"] = round(time.perf_counter() - t0, 3)
    alpha = (1.0 - ci_level) / 2.0
    ci_lo, ci_hi = {}, {}
    for basis in BASES:
        if n_boot >= 2:
            stack = np.stack(boots[basis])
            ci_lo[basis] = np.quantile(stack, alpha, axis=0)
            ci_hi[basis] = np.quantile(stack, 1.0 - alpha, axis=0)
        else:
            ci_lo[basis] = np.full_like(point[basis], np.nan)
            ci_hi[basis] = np.full_like(point[basis], np.nan)
    boot_info: dict[str, Any] = {"n_boot": n_boot, "n_paths_boot": n_paths_boot, "ci_level": ci_level}
    if not model.model_id.startswith("hmm_rs") and boot_summ:
        arr = np.array(boot_summ, dtype=float)
        boot_info["mean_block_boot"] = {
            "min": round(float(arr.min()), 3),
            "median": round(float(np.median(arr)), 3),
            "max": round(float(arr.max()), 3),
        }
    return PoolResult(
        model.model_id,
        fitted.pool,
        list(mixes),
        list(horizons),
        point,
        ci_lo,
        ci_hi,
        n_paths,
        n_boot,
        fitted.info,
        boot_info,
        timings,
    )


def to_rows(res: PoolResult, *, seed: int, code_sha: str, schema_version: str) -> dict[str, list]:
    """Table longue (colonnes du schéma) sous forme de dictionnaire de listes."""
    cols: dict[str, list] = {k: [] for k in _ROW_KEYS}
    pool = res.pool
    for basis in BASES:
        for m_i, mid in enumerate(res.mixes):
            for h_i, H in enumerate(res.horizons):
                for k, metric in enumerate(METRICS):
                    cols["schema_version"].append(schema_version)
                    cols["model_id"].append(res.model_id)
                    cols["family"].append(pool.family)
                    cols["currency"].append(pool.currency)
                    cols["mix_id"].append(mid)
                    cols["horizon_years"].append(int(H))
                    cols["basis"].append(basis)
                    cols["metric"].append(metric)
                    cols["value"].append(float(res.point[basis][k, h_i, m_i]))
                    cols["ci_lo"].append(float(res.ci_lo[basis][k, h_i, m_i]))
                    cols["ci_hi"].append(float(res.ci_hi[basis][k, h_i, m_i]))
                    cols["n_paths"].append(int(res.n_paths))
                    cols["n_boot"].append(int(res.n_boot))
                    cols["seed"].append(int(seed))
                    cols["fitted_through"].append(pool.fitted_through)
                    cols["window_start"].append(pool.window_start)
                    cols["n_hist_months"].append(int(pool.n))
                    cols["hypothese"].append(bool(pool.hypothese))
                    cols["data_sha256"].append(pool.data_sha256)
                    cols["code_sha"].append(code_sha)
    return cols


_ROW_KEYS = COLUMN_NAMES


def historical_reference(pool: Pool, mixes: Sequence[str], horizons: Sequence[int]) -> list[dict[str, Any]]:
    """Repères historiques (non simulés) par mélange : 2022 seul, pire 12 mois, perte max. de la fenêtre, pire
    rendement annualisé sur H ans glissants. Sert de contrôle (« 2022 seulement ») à côté des distributions."""
    W = weight_matrix(pool, mixes)
    lr = hist_log_returns(pool, W)
    dates = pool.dates
    rows: list[dict[str, Any]] = []
    in22 = np.asarray(dates.year == 2022)
    for basis in BASES:
        x = lr[basis]
        cum = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(x, axis=0)])
        peak = np.maximum.accumulate(cum, axis=0)
        mdd_full = -np.expm1(-(peak - cum).max(axis=0))
        roll12 = cum[12:] - cum[:-12]
        worst12 = np.expm1(roll12.min(axis=0))
        worst12_end = [dates[int(i) + 11].strftime("%Y-%m") for i in roll12.argmin(axis=0)]
        if in22.sum() == 12:
            c22 = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(x[in22], axis=0)])
            ret22 = np.expm1(c22[-1])
            mdd22 = -np.expm1(-(np.maximum.accumulate(c22, axis=0) - c22).max(axis=0))
        else:
            ret22 = mdd22 = np.full(x.shape[1], np.nan)
        for m_i, mid in enumerate(mixes):
            base = {"family": pool.family, "pool": pool.name, "mix_id": mid, "basis": basis}
            rows.append({**base, "metric": "ret_2022", "value": float(ret22[m_i]), "period": "2022-01..2022-12"})
            rows.append({**base, "metric": "mdd_2022", "value": float(mdd22[m_i]), "period": "2022-01..2022-12"})
            rows.append({**base, "metric": "worst_12m", "value": float(worst12[m_i]), "period": worst12_end[m_i]})
            rows.append(
                {
                    **base,
                    "metric": "mdd_full_window",
                    "value": float(mdd_full[m_i]),
                    "period": f"{pool.window_start}..{pool.fitted_through}",
                }
            )
            for H in horizons:
                n = 12 * H
                if pool.n < n:
                    continue
                roll = cum[n:, m_i] - cum[:-n, m_i]
                rows.append(
                    {
                        **base,
                        "metric": f"worst_ret_ann_{H}y",
                        "value": float(np.expm1(roll.min() / H)),
                        "period": f"{len(roll)} fenêtres glissantes",
                    }
                )
    return rows
