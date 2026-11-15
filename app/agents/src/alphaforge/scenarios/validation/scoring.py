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


def pit(samples: np.ndarray, y: float, u: float) -> float:
    """PIT randomisé : ``(#{X < y} + u · #{X = y}) / n`` avec ``u`` ~ U(0, 1) fourni par l'appelant."""
    x = np.asarray(samples)
    n = len(x)
    lo = float(np.count_nonzero(x < y))
    eq = float(np.count_nonzero(x == y))
    return (lo + u * eq) / n


def pinball(q_pred: float, y: float, tau: float) -> float:
    """Perte quantile (pinball) du quantile prédit ``q_pred`` au niveau ``tau``."""
    d = y - q_pred
    return float(max(tau * d, (tau - 1.0) * d))


def _kolmogorov_sf(lam: float) -> float:
    if lam <= 0:
        return 1.0
    s = 0.0
    for k in range(1, 101):
        term = 2.0 * (-1) ** (k - 1) * math.exp(-2.0 * k * k * lam * lam)
        s += term
        if abs(term) < 1e-12:
            break
    return float(min(max(s, 0.0), 1.0))


def ks_uniform(u: np.ndarray) -> tuple[float, float, int]:
    """(D, p-valeur asymptotique, n) du test KS de ``u`` contre U(0, 1). ``nan`` si n < 3."""
    u = np.sort(np.asarray(u, dtype=np.float64)[np.isfinite(u)])
    n = len(u)
    if n < 3:
        return float("nan"), float("nan"), n
    i = np.arange(1, n + 1)
    d = float(max(np.max(i / n - u), np.max(u - (i - 1) / n)))
    sn = math.sqrt(n)
    return d, _kolmogorov_sf((sn + 0.12 + 0.11 / sn) * d), n


def moving_block_bootstrap(n: int, block: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Indices ``(n_boot, n)`` d'un bootstrap par blocs mobiles circulaire (blocs de longueur ``block``)."""
    block = int(max(1, min(block, n)))
    n_blocks = int(math.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(n_boot, -1)[:, :n]


def block_ci(
    values: np.ndarray, block: int, n_boot: int, rng: np.random.Generator, level: float = 0.90
) -> tuple[float, float, float]:
    """Moyenne et intervalle bootstrap par blocs (percentile) de la moyenne de ``values`` (1-D, ordre des
    origines). Les ``nan`` sont ignorés dans chaque réplication."""
    v = np.asarray(values, dtype=np.float64)
    ok = np.isfinite(v)
    if ok.sum() == 0:
        return float("nan"), float("nan"), float("nan")
    v = v[ok]
    idx = moving_block_bootstrap(len(v), block, n_boot, rng)
    means = v[idx].mean(axis=1)
    a = (1.0 - level) / 2.0
    return float(v.mean()), float(np.quantile(means, a)), float(np.quantile(means, 1.0 - a))


def realized_outcome(lr: np.ndarray) -> tuple[float, float, float]:
    """Pour des log-rendements mensuels réalisés ``lr`` (1-D, 12·H mois) : (rendement annualisé, perte maximale
    depuis un sommet capital initial compris, log-richesse finale).
    Même définition que ``engine.metrics_from_paths``."""
    cum = np.cumsum(lr)
    peak = np.maximum.accumulate(np.maximum(cum, 0.0))
    mdd = float(-np.expm1(-np.max(peak - cum)))
    h = len(lr) / 12.0
    return float(np.expm1(cum[-1] / h)), mdd, float(cum[-1])


def path_outcomes(lr_hist: np.ndarray, idx: np.ndarray, horizons: list[int]) -> dict[int, dict[str, np.ndarray]]:
    """Échantillons simulés par horizon : rendement annualisé, perte maximale, log-richesse finale.

    ``lr_hist`` (T, M) log-rendements mensuels des mélanges ; ``idx`` (N, T_sim) indices de mois. Renvoie, pour chaque
    H, des tableaux (N, M)."""
    cum = np.cumsum(lr_hist[idx], axis=1)  # (N, T, M)
    dd = np.maximum.accumulate(np.maximum(cum, 0.0), axis=1) - cum
    np.maximum.accumulate(dd, axis=1, out=dd)
    out = {}
    for H in horizons:
        m = 12 * H - 1
        out[H] = {
            "ret": np.expm1(cum[:, m, :] / H),
            "mdd": -np.expm1(-dd[:, m, :]),
            "logw": cum[:, m, :].copy(),
        }
    return out


def rolling_outcomes(lr: np.ndarray, H: int) -> dict[str, np.ndarray]:
    """Résultats de toutes les fenêtres glissantes de 12·H mois de ``lr`` (1-D) : base empirique naïve."""
    n = 12 * H
    T = len(lr)
    if T < n:
        return {"ret": np.empty(0), "mdd": np.empty(0), "logw": np.empty(0)}
    win = np.lib.stride_tricks.sliding_window_view(lr, n)  # (T-n+1, n)
    cum = np.cumsum(win, axis=1)
    peak = np.maximum.accumulate(np.maximum(cum, 0.0), axis=1)
    mdd = -np.expm1(-np.max(peak - cum, axis=1))
    return {"ret": np.expm1(cum[:, -1] / H), "mdd": mdd, "logw": cum[:, -1].copy()}
