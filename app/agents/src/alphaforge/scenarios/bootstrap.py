"""Bootstrap stationnaire (Politis et Romano, 1994) et longueur moyenne de bloc automatique (Politis et White, 2004,
avec la correction de Patton, Politis et White, 2009).

Le bootstrap tire des **mois entiers** (toutes les colonnes ensemble) : la corrélation entre actifs d'un même mois
est donc conservée telle quelle, et la dépendance temporelle l'est à l'intérieur des blocs (longueur géométrique de
moyenne ``L``). Le panneau est traité comme circulaire (le mois qui suit le dernier est le premier).
"""

from __future__ import annotations

import math

import numpy as np


def stationary_indices(n_hist: int, n_paths: int, n_months: int, mean_block: float, rng: np.random.Generator):
    """Indices ``(n_paths, n_months)`` dans ``[0, n_hist)`` tirés par bootstrap stationnaire, entièrement vectorisé.

    À chaque mois, un nouveau bloc commence avec la probabilité ``p = 1 / mean_block`` (toujours au mois 0), à une
    position uniforme ; sinon on prend le mois suivant de l'historique (circulaire).
    """
    if n_hist < 2:
        raise ValueError("historique trop court")
    restart_probability = 1.0 / max(float(mean_block), 1.0)
    new_block = rng.random((n_paths, n_months)) < restart_probability
    new_block[:, 0] = True
    starts = rng.integers(0, n_hist, size=(n_paths, n_months))
    months = np.arange(n_months)
    last_start = np.maximum.accumulate(np.where(new_block, months, 0), axis=1)
    origin = np.take_along_axis(starts, last_start, axis=1)
    return ((origin + (months - last_start)) % n_hist).astype(np.int32)


def _flat_top(x: np.ndarray) -> np.ndarray:
    magnitude = np.abs(x)
    return np.where(magnitude <= 0.5, 1.0, np.where(magnitude <= 1.0, 2.0 * (1.0 - magnitude), 0.0))


# c de Politis et White : une autocorrélation est significative au-delà de c·sqrt(log10(n)/n).
_SIGNIFICANCE_FACTOR = 2.0


def _cutoff_lag(acov: np.ndarray, n: int, k_n: int, m_max: int) -> int:
    """Étape (1) : plus petit décalage ``m`` suivi de ``K_N`` autocorrélations consécutives non significatives."""
    rho = acov / acov[0]
    threshold = _SIGNIFICANCE_FACTOR * math.sqrt(math.log10(n) / n)
    insignificant = np.abs(rho[1:]) < threshold
    for lag in range(m_max + 1):
        if insignificant[lag : lag + k_n].all():
            return lag
    # Aucune coupure trouvée : on prend le plus grand décalage significatif (repli de PPW 2009).
    significant = np.flatnonzero(~insignificant[:m_max])
    return int(significant.max()) + 1 if significant.size else 1


def _kernel_block_length(acov: np.ndarray, big_m: int, n: int) -> float | None:
    """Étapes (3)-(4) : ``b`` par le noyau plat de largeur ``M`` ; ``None`` si ``G`` est nul ou ``D`` <= 0."""
    k = np.arange(-big_m, big_m + 1)
    kernel = _flat_top(k / big_m)  # λ(k/M)
    autocov = acov[np.abs(k)]  # γ(k)
    g_hat = float(np.sum(kernel * np.abs(k) * autocov))
    d_sb = 2.0 * float(np.sum(kernel * autocov)) ** 2
    if d_sb <= 0 or g_hat == 0:
        return None
    return (2.0 * g_hat**2 / d_sb) ** (1.0 / 3.0) * n ** (1.0 / 3.0)


def politis_white(x: np.ndarray) -> float:
    """Longueur moyenne de bloc optimale du bootstrap stationnaire pour une série (Politis et White 2004 / PPW 2009).

    Étapes : (1) plus petit décalage ``m`` après lequel ``K_N`` autocorrélations consécutives sont non
    significatives (seuil ``2·sqrt(log10(n)/n)``) ; (2) ``M = 2m`` ; (3) noyau plat ``λ`` ; (4)
    ``b = (2·G² / D)^(1/3) · n^(1/3)`` avec ``G = Σ λ(k/M)|k|γ(k)`` et ``D = 2·(Σ λ(k/M)γ(k))²``.
    Bornée à ``[1, b_max]`` avec ``b_max = ceil(min(3·sqrt(n), n/3))``.
    """
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12:
        raise ValueError("série trop courte pour Politis-White")
    centered = x - x.mean()
    k_n = max(5, int(math.ceil(math.sqrt(math.log10(n)))))
    m_max = int(math.ceil(math.sqrt(n))) + k_n
    b_max = math.ceil(min(3.0 * math.sqrt(n), n / 3.0))
    variance = float(centered @ centered) / n
    if variance <= 0:
        return 1.0
    acov = np.array([float(centered[: n - k] @ centered[k:]) / n for k in range(m_max + k_n + 1)])
    big_m = min(2 * max(_cutoff_lag(acov, n, k_n, m_max), 1), m_max)
    block_length = _kernel_block_length(acov, big_m, n)
    if block_length is None:
        return 1.0
    return float(min(max(block_length, 1.0), b_max))


def auto_block_length(returns: np.ndarray, columns: list[int], rule: str = "max") -> tuple[float, list[float]]:
    """Longueur commune pour le bootstrap joint : Politis-White sur chaque colonne retenue, puis agrégée
    (``max`` par défaut, pour ne casser la dépendance d'aucune des séries retenues ; ou ``median``)."""
    values = [politis_white(returns[:, j]) for j in columns]
    if rule == "max":
        return float(max(values)), values
    if rule == "median":
        return float(np.median(values)), values
    raise ValueError(f"règle inconnue {rule!r}")
