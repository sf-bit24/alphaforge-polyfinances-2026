"""Règles de score et statistiques de validation (numpy seulement, pas de scipy).

Toutes les fonctions sont pures et déterministes (l'aléa éventuel passe par un ``np.random.Generator``).

- ``crps_samples`` : CRPS d'une distribution prédictive empirique (échantillon), formule exacte sur l'échantillon
  trié : ``CRPS = E|X - y| - ½ E|X - X'|``.
- ``pit`` : transformée intégrale de probabilité randomisée (les atomes, par exemple une perte maximale nulle,
  reçoivent un PIT uniforme sur leur saut) ; uniforme sous calibration parfaite.
- ``pinball`` : perte quantile pour un niveau ``tau``.
- ``ks_uniform`` : statistique de Kolmogorov-Smirnov contre U(0, 1) et p-valeur asymptotique (série de Kolmogorov,
  correction de Stephens pour petits n). Hypothèse : observations indépendantes ; l'appelant ne lui passe que des
  sous-ensembles de fenêtres **non chevauchantes**.
- ``moving_block_bootstrap`` : indices d'un bootstrap par blocs mobiles circulaire sur la suite des origines
  (les fenêtres de H ans espacées de 12 mois se chevauchent : un bloc de H origines garde cette dépendance).
"""

from __future__ import annotations

import math

import numpy as np


def crps_samples(samples: np.ndarray, y: float) -> float:
    """CRPS exact de la loi empirique de ``samples`` (1-D) pour l'observation ``y``."""
    x = np.sort(np.asarray(samples, dtype=np.float64))
    n = len(x)
    if n == 0:
        return float("nan")
    term1 = float(np.mean(np.abs(x - y)))
    # E|X - X'| = (2 / n²) Σ_i (2i - n - 1) x_(i), i = 1..n
    i = np.arange(1, n + 1)
    term2 = float(2.0 * np.sum((2 * i - n - 1) * x) / (n * n))
    return term1 - 0.5 * term2


def pit(samples: np.ndarray, y: float, uniform: float) -> float:
    """PIT randomisé : ``(#{X < y} + u · #{X = y}) / n``, où ``u`` (``uniform``) ~ U(0, 1) est fourni par
    l'appelant."""
    x = np.asarray(samples)
    n = len(x)
    below = float(np.count_nonzero(x < y))
    ties = float(np.count_nonzero(x == y))
    return (below + uniform * ties) / n


def pinball(q_pred: float, y: float, tau: float) -> float:
    """Perte quantile (pinball) du quantile prédit ``q_pred`` au niveau ``tau``."""
    error = y - q_pred
    return float(max(tau * error, (tau - 1.0) * error))


def _kolmogorov_sf(lam: float) -> float:
    if lam <= 0:
        return 1.0
    total = 0.0
    for k in range(1, 101):
        term = 2.0 * (-1) ** (k - 1) * math.exp(-2.0 * k * k * lam * lam)
        total += term
        if abs(term) < 1e-12:
            break
    return float(min(max(total, 0.0), 1.0))


def ks_uniform(pit_values: np.ndarray) -> tuple[float, float, int]:
    """(D, p-valeur asymptotique, n) du test KS de ``pit_values`` contre U(0, 1). ``nan`` si n < 3."""
    values = np.sort(np.asarray(pit_values, dtype=np.float64)[np.isfinite(pit_values)])
    n = len(values)
    if n < 3:
        return float("nan"), float("nan"), n
    i = np.arange(1, n + 1)
    statistic = float(max(np.max(i / n - values), np.max(values - (i - 1) / n)))
    sqrt_n = math.sqrt(n)
    return statistic, _kolmogorov_sf((sqrt_n + 0.12 + 0.11 / sqrt_n) * statistic), n


def moving_block_bootstrap(n: int, block: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Indices ``(n_boot, n)`` d'un bootstrap par blocs mobiles circulaire (blocs de longueur ``block``)."""
    block = int(max(1, min(block, n)))
    n_blocks = int(math.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    indices = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return indices.reshape(n_boot, -1)[:, :n]


def block_ci(
    values: np.ndarray, block: int, n_boot: int, rng: np.random.Generator, level: float = 0.90
) -> tuple[float, float, float]:
    """Moyenne et intervalle bootstrap par blocs (percentile) de la moyenne de ``values`` (1-D, ordre des
    origines). Les ``nan`` sont ignorés dans chaque réplication."""
    array = np.asarray(values, dtype=np.float64)
    finite = np.isfinite(array)
    if finite.sum() == 0:
        return float("nan"), float("nan"), float("nan")
    array = array[finite]
    indices = moving_block_bootstrap(len(array), block, n_boot, rng)
    means = array[indices].mean(axis=1)
    alpha = (1.0 - level) / 2.0
    return float(array.mean()), float(np.quantile(means, alpha)), float(np.quantile(means, 1.0 - alpha))


def realized_outcome(log_returns: np.ndarray) -> tuple[float, float, float]:
    """Pour des log-rendements mensuels réalisés ``log_returns`` (1-D, 12·H mois) : (rendement annualisé, perte
    maximale depuis un sommet capital initial compris, log-richesse finale).
    Même définition que ``engine.metrics_from_paths``."""
    cum = np.cumsum(log_returns)
    peak = np.maximum.accumulate(np.maximum(cum, 0.0))
    mdd = float(-np.expm1(-np.max(peak - cum)))
    years = len(log_returns) / 12.0
    return float(np.expm1(cum[-1] / years)), mdd, float(cum[-1])


def path_outcomes(
    log_returns: np.ndarray, indices: np.ndarray, horizons: list[int]
) -> dict[int, dict[str, np.ndarray]]:
    """Échantillons simulés par horizon : rendement annualisé, perte maximale, log-richesse finale.

    ``log_returns`` (T, M) log-rendements mensuels des mélanges ; ``indices`` (N, T_sim) indices de mois. Renvoie,
    pour chaque H, des tableaux (N, M)."""
    cum = np.cumsum(log_returns[indices], axis=1)  # (N, T, M)
    drawdown = np.maximum.accumulate(np.maximum(cum, 0.0), axis=1) - cum
    np.maximum.accumulate(drawdown, axis=1, out=drawdown)
    out = {}
    for horizon in horizons:
        month = 12 * horizon - 1
        out[horizon] = {
            "ret": np.expm1(cum[:, month, :] / horizon),
            "mdd": -np.expm1(-drawdown[:, month, :]),
            "logw": cum[:, month, :].copy(),
        }
    return out


def rolling_outcomes(log_returns: np.ndarray, horizon: int) -> dict[str, np.ndarray]:
    """Résultats de toutes les fenêtres glissantes de 12·H mois de ``log_returns`` (1-D) : base empirique naïve."""
    n = 12 * horizon
    n_months = len(log_returns)
    if n_months < n:
        return {"ret": np.empty(0), "mdd": np.empty(0), "logw": np.empty(0)}
    windows = np.lib.stride_tricks.sliding_window_view(log_returns, n)  # (T-n+1, n)
    cum = np.cumsum(windows, axis=1)
    peak = np.maximum.accumulate(np.maximum(cum, 0.0), axis=1)
    mdd = -np.expm1(-np.max(peak - cum, axis=1))
    return {"ret": np.expm1(cum[:, -1] / horizon), "mdd": mdd, "logw": cum[:, -1].copy()}
