"""Simulation vectorisée des résultats de portefeuille et métriques du schéma.

Hypothèses de calcul : rebalancement **mensuel** vers les poids cibles, sans frais ni impôts, sans flux. Avec des
poids fixes rebalancés chaque mois, le rendement du portefeuille au mois t vaut exactement ``w · r_t`` ; on calcule
donc une fois les rendements historiques de chaque mélange, puis on les rééchantillonne par les indices du générateur.

Toutes les trajectoires durent ``12 · max(horizons)`` mois ; l'horizon H lit les ``12·H`` premiers mois des mêmes
trajectoires (métriques cohérentes entre horizons).
"""

from __future__ import annotations

import itertools
import math
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .data import Pool
from .models import Fitted, Model, rng_for
from .schema import COLUMN_NAMES, LOSS_THRESHOLDS, MDD_THRESHOLDS, METRICS, RET_QUANTILES, parse_mix_id

BASES = ("nominal", "real")
# Seuils des métriques, en log-richesse : perte cumulée > x % et perte maximale > x %.
_RET_LEVELS = np.array(RET_QUANTILES) / 100.0
_LOSS_LOG_THRESHOLDS = np.log1p(-np.array(LOSS_THRESHOLDS) / 100.0)
_MDD_LOG_THRESHOLDS = -np.log1p(-np.array(MDD_THRESHOLDS) / 100.0)


def weight_matrix(pool: Pool, mixes: Sequence[str]) -> np.ndarray:
    """Matrice ``(n_blocs, n_mélanges)`` ; erreur si un mélange utilise un bloc absent du pool."""
    weights = np.zeros((len(pool.blocks), len(mixes)))
    for m_i, mix in enumerate(mixes):
        for block, weight in parse_mix_id(mix).items():
            if weight == 0:
                continue
            if block not in pool.blocks:
                raise ValueError(f"{mix} utilise {block}, absent du pool {pool.name}")
            weights[pool.blocks.index(block), m_i] = weight
    return weights


def hist_log_returns(pool: Pool, weights: np.ndarray) -> dict[str, np.ndarray]:
    """Log-rendements mensuels historiques de chaque mélange, nominaux et réels (déflatés par l'IPC du pool)."""
    portfolio = pool.returns @ weights
    if (portfolio <= -1).any():
        raise ValueError("rendement de portefeuille <= -100 %")
    log_returns = np.log1p(portfolio)
    return {"nominal": log_returns, "real": log_returns - np.log1p(pool.inflation)[:, None]}


def _horizon_metrics(cum: np.ndarray, drawdown: np.ndarray, annual: np.ndarray, horizon: int) -> np.ndarray:
    """Métriques ``(n_metrics, n_mélanges)`` d'un horizon, dans l'ordre de ``schema.METRICS``."""
    n_paths = cum.shape[0]
    month = 12 * horizon - 1
    log_w = cum[:, month, :]
    mdd = drawdown[:, month, :]
    out = np.empty((len(METRICS), cum.shape[2]))
    row = 0
    out[row : row + len(_RET_LEVELS)] = np.expm1(np.quantile(log_w, _RET_LEVELS, axis=0) / horizon)
    row += len(_RET_LEVELS)
    out[row] = np.exp(np.quantile(log_w, 0.10, axis=0))
    row += 1
    out[row : row + 2] = -np.expm1(-np.quantile(mdd, [0.5, 0.9], axis=0))
    row += 2
    annual_returns = np.expm1(annual[:, :horizon, :]).reshape(n_paths * horizon, -1)
    k = max(1, math.ceil(0.05 * annual_returns.shape[0]))
    tail = np.partition(annual_returns, k - 1, axis=0)[:k]
    out[row] = -tail.mean(axis=0)
    row += 1
    for x in _LOSS_LOG_THRESHOLDS:
        out[row] = (log_w < x).mean(axis=0)
        row += 1
    for x in _MDD_LOG_THRESHOLDS:
        out[row] = (mdd > x).mean(axis=0)
        row += 1
    return out


def _chunk_metrics(
    log_returns: np.ndarray, indices: np.ndarray, horizons: list[int], year_ends: np.ndarray
) -> np.ndarray:
    """Métriques ``(n_metrics, n_horizons, n_mélanges)`` d'un groupe de mélanges (colonnes de ``log_returns``)."""
    cum = log_returns[indices]  # (N, T, Mc)
    np.cumsum(cum, axis=1, out=cum)
    drawdown = np.maximum.accumulate(np.maximum(cum, 0.0), axis=1)
    drawdown -= cum  # log(pic / richesse) >= 0
    np.maximum.accumulate(drawdown, axis=1, out=drawdown)  # perte maximale en log jusqu'au mois t
    annual = np.diff(cum[:, year_ends, :], axis=1, prepend=0.0)  # log-rendements par année civile simulée
    return np.stack([_horizon_metrics(cum, drawdown, annual, horizon) for horizon in horizons], axis=1)


def metrics_from_paths(
    log_returns: np.ndarray, indices: np.ndarray, horizons: Sequence[int], mem_budget_mb: float = 512.0
) -> np.ndarray:
    """Métriques ``(n_metrics, n_horizons, n_mixes)`` (ordre de ``schema.METRICS``) pour une base.

    ``log_returns`` : (T_hist, M) log-rendements ; ``indices`` : (N, T_sim) indices de mois.
    """
    n_paths, t_sim = indices.shape
    horizons = list(horizons)
    if 12 * max(horizons) > t_sim:
        raise ValueError("trajectoires trop courtes pour l'horizon demandé")
    n_mix = log_returns.shape[1]
    out = np.empty((len(METRICS), len(horizons), n_mix))
    per_mix_bytes = n_paths * t_sim * 8 * 2
    chunk = max(1, int(mem_budget_mb * 1e6 // per_mix_bytes))
    year_ends = np.arange(12, t_sim + 1, 12) - 1
    for start in range(0, n_mix, chunk):
        columns = slice(start, min(start + chunk, n_mix))
        out[:, :, columns] = _chunk_metrics(log_returns[:, columns], indices, horizons, year_ends)
    return out


def simulate_metrics(
    fitted: Fitted, mixes: Sequence[str], horizons: Sequence[int], n_paths: int, rng: np.random.Generator, **kwargs
) -> dict[str, np.ndarray]:
    """Simule ``n_paths`` trajectoires du modèle ajusté et renvoie les métriques par base."""
    weights = weight_matrix(fitted.pool, mixes)
    log_returns = hist_log_returns(fitted.pool, weights)
    indices = fitted.simulate_indices(n_paths, 12 * max(horizons), rng)
    return {basis: metrics_from_paths(log_returns[basis], indices, horizons, **kwargs) for basis in BASES}


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


@dataclass(frozen=True)
class SimulationConfig:
    """Paramètres de ``run_pool`` : graine, trajectoires de l'estimation ponctuelle et du bootstrap externe, dernier
    mois d'ajustement, niveau des intervalles et budget mémoire (section ``simulation`` des configurations)."""

    seed: int
    n_paths: int
    n_boot: int
    n_paths_boot: int
    fitted_through: str | None = None
    ci_level: float = 0.90
    mem_budget_mb: float = 512.0


@contextmanager
def _timed(timings: dict[str, float], key: str) -> Iterator[None]:
    """Range sous ``key`` la durée du bloc, en secondes arrondies au millième."""
    started = time.perf_counter()
    yield
    timings[key] = round(time.perf_counter() - started, 3)


def _intervals(
    point: dict[str, np.ndarray], replicates: dict[str, list[np.ndarray]], n_boot: int, ci_level: float
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Quantiles (1-ci)/2 et (1+ci)/2 des réplications, par base ; NaN avec moins de deux réplications."""
    alpha = (1.0 - ci_level) / 2.0
    ci_lo, ci_hi = {}, {}
    for basis in BASES:
        if n_boot >= 2:
            stack = np.stack(replicates[basis])
            ci_lo[basis] = np.quantile(stack, alpha, axis=0)
            ci_hi[basis] = np.quantile(stack, 1.0 - alpha, axis=0)
        else:
            ci_lo[basis] = np.full_like(point[basis], np.nan)
            ci_hi[basis] = np.full_like(point[basis], np.nan)
    return ci_lo, ci_hi


def _boot_info(model_id: str, refit_summary: list[Any], config: SimulationConfig) -> dict[str, Any]:
    """Réglages du bootstrap externe et, hors HMM, l'étendue des longueurs de bloc réajustées."""
    boot_info: dict[str, Any] = {
        "n_boot": config.n_boot,
        "n_paths_boot": config.n_paths_boot,
        "ci_level": config.ci_level,
    }
    if not model_id.startswith("hmm_rs") and refit_summary:
        blocks = np.array(refit_summary, dtype=float)
        boot_info["mean_block_boot"] = {
            "min": round(float(blocks.min()), 3),
            "median": round(float(np.median(blocks)), 3),
            "max": round(float(blocks.max()), 3),
        }
    return boot_info


def run_pool(
    model: Model, pool: Pool, mixes: Sequence[str], horizons: Sequence[int], config: SimulationConfig
) -> PoolResult:
    """Ajuste, simule (estimation ponctuelle) puis bootstrap externe des paramètres (intervalles à ``ci_level``).

    Bootstrap externe fondé sur le modèle : pour b = 1..B, pseudo-historique de même longueur tiré du modèle ajusté,
    réajustement (longueur de bloc, ou HMM à K fixé), puis ``n_paths_boot`` trajectoires. L'intervalle est formé
    des quantiles (1-ci)/2 et (1+ci)/2 des B valeurs. Il traduit l'incertitude d'estimation **dans** le modèle,
    pas l'incertitude sur le choix du modèle.
    """
    timings: dict[str, float] = {}
    with _timed(timings, "fit_s"):
        rng = rng_for(config.seed, pool.name, model.model_id, "fit")
        fitted = model.fit(pool, config.fitted_through, rng=rng)
    with _timed(timings, "simulate_s"):
        rng = rng_for(config.seed, pool.name, model.model_id, "sim")
        point = simulate_metrics(fitted, mixes, horizons, config.n_paths, rng, mem_budget_mb=config.mem_budget_mb)
    replicates: dict[str, list[np.ndarray]] = {basis: [] for basis in BASES}
    refit_summary: list[Any] = []
    with _timed(timings, "bootstrap_s"):
        for replicate in range(config.n_boot):
            rng = rng_for(config.seed, pool.name, model.model_id, "boot", replicate)
            pseudo = fitted.pseudo_history(rng)
            refit = model.refit(fitted, pseudo, rng)
            values = simulate_metrics(
                refit, mixes, horizons, config.n_paths_boot, rng, mem_budget_mb=config.mem_budget_mb
            )
            for basis in BASES:
                replicates[basis].append(values[basis])
            refit_summary.append(refit.mean_block if refit.hmm is None else refit.hmm.params.k)
    ci_lo, ci_hi = _intervals(point, replicates, config.n_boot, config.ci_level)
    return PoolResult(
        model.model_id,
        fitted.pool,
        list(mixes),
        list(horizons),
        point,
        ci_lo,
        ci_hi,
        config.n_paths,
        config.n_boot,
        fitted.info,
        _boot_info(model.model_id, refit_summary, config),
        timings,
    )


def to_rows(result: PoolResult, *, seed: int, code_sha: str, schema_version: str) -> dict[str, list]:
    """Table longue (colonnes du schéma) sous forme de dictionnaire de listes."""
    columns: dict[str, list] = {k: [] for k in _ROW_KEYS}
    pool = result.pool
    cells = itertools.product(BASES, enumerate(result.mixes), enumerate(result.horizons), enumerate(METRICS))
    for basis, (m_i, mix), (h_i, horizon), (k, metric) in cells:
        columns["schema_version"].append(schema_version)
        columns["model_id"].append(result.model_id)
        columns["family"].append(pool.family)
        columns["currency"].append(pool.currency)
        columns["mix_id"].append(mix)
        columns["horizon_years"].append(int(horizon))
        columns["basis"].append(basis)
        columns["metric"].append(metric)
        columns["value"].append(float(result.point[basis][k, h_i, m_i]))
        columns["ci_lo"].append(float(result.ci_lo[basis][k, h_i, m_i]))
        columns["ci_hi"].append(float(result.ci_hi[basis][k, h_i, m_i]))
        columns["n_paths"].append(int(result.n_paths))
        columns["n_boot"].append(int(result.n_boot))
        columns["seed"].append(int(seed))
        columns["fitted_through"].append(pool.fitted_through)
        columns["window_start"].append(pool.window_start)
        columns["n_hist_months"].append(int(pool.n))
        columns["hypothese"].append(bool(pool.hypothese))
        columns["data_sha256"].append(pool.data_sha256)
        columns["code_sha"].append(code_sha)
    return columns


_ROW_KEYS = COLUMN_NAMES


def _year_2022(log_returns: np.ndarray, in_2022: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rendement et perte max. de l'année civile 2022 par mélange ; NaN si la fenêtre ne la contient pas en entier."""
    if in_2022.sum() != 12:
        missing = np.full(log_returns.shape[1], np.nan)
        return missing, missing
    cum = np.vstack([np.zeros((1, log_returns.shape[1])), np.cumsum(log_returns[in_2022], axis=0)])
    return np.expm1(cum[-1]), -np.expm1(-(np.maximum.accumulate(cum, axis=0) - cum).max(axis=0))


def _worst_rolling_rows(base: dict[str, Any], cum: np.ndarray, horizons: Sequence[int], n_months: int) -> list[dict]:
    """Pire rendement annualisé sur H ans glissants (log-richesse cumulée ``cum`` d'un mélange), si H tient."""
    rows = []
    for horizon in horizons:
        n = 12 * horizon
        if n_months < n:
            continue
        roll = cum[n:] - cum[:-n]
        rows.append(
            {
                **base,
                "metric": f"worst_ret_ann_{horizon}y",
                "value": float(np.expm1(roll.min() / horizon)),
                "period": f"{len(roll)} fenêtres glissantes",
            }
        )
    return rows


def historical_reference(pool: Pool, mixes: Sequence[str], horizons: Sequence[int]) -> list[dict[str, Any]]:
    """Repères historiques (non simulés) par mélange : 2022 seul, pire 12 mois, perte max. de la fenêtre, pire
    rendement annualisé sur H ans glissants. Sert de contrôle (« 2022 seulement ») à côté des distributions."""
    log_returns = hist_log_returns(pool, weight_matrix(pool, mixes))
    dates = pool.dates
    rows: list[dict[str, Any]] = []
    in_2022 = np.asarray(dates.year == 2022)
    for basis in BASES:
        basis_returns = log_returns[basis]
        cum = np.vstack([np.zeros((1, basis_returns.shape[1])), np.cumsum(basis_returns, axis=0)])
        peak = np.maximum.accumulate(cum, axis=0)
        mdd_full = -np.expm1(-(peak - cum).max(axis=0))
        roll12 = cum[12:] - cum[:-12]
        worst12 = np.expm1(roll12.min(axis=0))
        worst12_end = [dates[int(i) + 11].strftime("%Y-%m") for i in roll12.argmin(axis=0)]
        ret22, mdd22 = _year_2022(basis_returns, in_2022)
        for m_i, mix in enumerate(mixes):
            base = {"family": pool.family, "pool": pool.name, "mix_id": mix, "basis": basis}
            rows.append({**base, "metric": "ret_2022", "value": float(ret22[m_i]), "period": "2022-01..2022-12"})
            rows.append({**base, "metric": "mdd_2022", "value": float(mdd22[m_i]), "period": "2022-01..2022-12"})
            rows.append({**base, "metric": "worst_12m", "value": float(worst12[m_i]), "period": worst12_end[m_i]})
            window = f"{pool.window_start}..{pool.fitted_through}"
            rows.append({**base, "metric": "mdd_full_window", "value": float(mdd_full[m_i]), "period": window})
            rows += _worst_rolling_rows(base, cum[:, m_i], horizons, pool.n)
    return rows
