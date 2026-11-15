"""HMM gaussien multivarié minimal (numpy seulement) : EM de Baum-Welch avec mise à l'échelle, BIC, chaîne simulée.

Volontairement petit (K <= 3 états, quelques séries) : il sert à découper l'historique en régimes persistants, puis
le générateur rééchantillonne des mois **historiques** dans chaque régime (approche semi-paramétrique). Les lois
gaussiennes ne servent donc qu'à classer les mois, pas à produire les rendements simulés.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

_REG = 1e-4  # régularisation de la diagonale des covariances (données standardisées)


@dataclass
class HMMParams:
    initial_distribution: np.ndarray  # π, (K,)
    transition_matrix: np.ndarray  # A, (K, K)
    means: np.ndarray  # (K, d)
    covariances: np.ndarray  # (K, d, d)

    @property
    def k(self) -> int:
        return len(self.initial_distribution)

    def n_params(self) -> int:
        k, n_features = self.means.shape
        return (k - 1) + k * (k - 1) + k * n_features + k * n_features * (n_features + 1) // 2

    def stationary(self) -> np.ndarray:
        if self.k == 1:
            return np.ones(1)
        eigenvalues, eigenvectors = np.linalg.eig(self.transition_matrix.T)
        stationary = np.real(eigenvectors[:, np.argmin(np.abs(eigenvalues - 1.0))])
        return np.abs(stationary) / np.abs(stationary).sum()


@dataclass
class HMMFit:
    params: HMMParams
    loglik: float
    bic: float
    n_iter: int
    converged: bool
    gamma: np.ndarray  # (T, K) probabilités lissées des régimes
    filtered_last: np.ndarray  # (K,) probabilité filtrée du dernier mois (sans information future)


@dataclass(frozen=True)
class EMSettings:
    """Réglages de l'EM : départs, itérations au plus, tolérance relative sur la log-vraisemblance."""

    n_init: int = 3
    max_iter: int = 200
    tol: float = 1e-6


_DEFAULT_EM = EMSettings()


def log_emissions(features: np.ndarray, means: np.ndarray, covariances: np.ndarray) -> np.ndarray:
    n_months, n_features = features.shape
    out = np.empty((n_months, len(means)))
    for k in range(len(means)):
        cholesky_factor = np.linalg.cholesky(covariances[k])
        whitened = np.linalg.solve(cholesky_factor, (features - means[k]).T)
        logdet = 2.0 * np.log(np.diag(cholesky_factor)).sum()
        out[:, k] = -0.5 * (n_features * math.log(2 * math.pi) + logdet + (whitened * whitened).sum(axis=0))
    return out


def forward_backward(log_b: np.ndarray, initial: np.ndarray, transition: np.ndarray):
    """Renvoie (loglik, gamma (T,K), xi_sum (K,K), filtré du dernier mois)."""
    n_months, n_states = log_b.shape
    shift = log_b.max(axis=1, keepdims=True)
    emission = np.exp(log_b - shift)  # b_t(j), à un facteur exp(shift_t) près
    alpha = np.empty((n_months, n_states))
    scale = np.empty(n_months)  # c_t
    unscaled = initial * emission[0]
    scale[0] = unscaled.sum()
    alpha[0] = unscaled / scale[0]
    for t in range(1, n_months):
        unscaled = (alpha[t - 1] @ transition) * emission[t]
        scale[t] = unscaled.sum()
        alpha[t] = unscaled / scale[t]
    beta = np.empty((n_months, n_states))
    beta[-1] = 1.0
    for t in range(n_months - 2, -1, -1):
        beta[t] = (transition @ (emission[t + 1] * beta[t + 1])) / scale[t + 1]
    gamma = alpha * beta
    gamma /= gamma.sum(axis=1, keepdims=True)
    # xi_t(i,j) = alpha_t(i) A(i,j) b_{t+1}(j) beta_{t+1}(j) / c_{t+1}
    weighted = emission[1:] * beta[1:] / scale[1:, None]
    xi_sum = transition * (alpha[:-1].T @ weighted)
    loglik = float(np.log(scale).sum() + shift.sum())
    return loglik, gamma, xi_sum, alpha[-1].copy()


def _m_step(features: np.ndarray, gamma: np.ndarray, xi_sum: np.ndarray) -> HMMParams:
    _, n_features = features.shape
    n_states = gamma.shape[1]
    weights = gamma.sum(axis=0) + 1e-12
    means = (gamma.T @ features) / weights[:, None]
    covariances = np.empty((n_states, n_features, n_features))
    for k in range(n_states):
        diff = features - means[k]
        covariances[k] = (gamma[:, k, None] * diff).T @ diff / weights[k] + _REG * np.eye(n_features)
    transition = xi_sum + 1e-12
    transition /= transition.sum(axis=1, keepdims=True)
    return HMMParams(gamma[0] + 1e-12, transition, means, covariances)


def _init_params(features: np.ndarray, n_states: int, rng: np.random.Generator, how: str) -> HMMParams:
    n_months, _ = features.shape
    if n_states == 1 or how == "vol":
        # États ordonnés par l'amplitude du facteur commun (moyenne des colonnes), lissée sur 6 mois.
        factor = np.abs(features.mean(axis=1))
        smooth = np.convolve(factor, np.ones(6) / 6, mode="same")
        edges = np.quantile(smooth, np.linspace(0, 1, n_states + 1)[1:-1]) if n_states > 1 else []
        labels = np.searchsorted(edges, smooth) if n_states > 1 else np.zeros(n_months, dtype=int)
    else:
        labels = rng.integers(0, n_states, size=n_months)
        # quelques segments contigus pour amorcer la persistance
        segment = max(n_months // (4 * n_states), 1)
        labels = np.repeat(labels[::segment], segment)[:n_months]
        if len(labels) < n_months:
            labels = np.pad(labels, (0, n_months - len(labels)), mode="edge")
    gamma = np.full((n_months, n_states), 1e-3)
    gamma[np.arange(n_months), labels] = 1.0
    gamma /= gamma.sum(axis=1, keepdims=True)
    xi_sum = np.full((n_states, n_states), 1.0) + np.eye(n_states) * 9.0 * n_months / n_states
    return _m_step(features, gamma, xi_sum)


def _starting_points(
    features: np.ndarray, n_states: int, rng: np.random.Generator, n_init: int, warm_start: HMMParams | None
) -> list[HMMParams]:
    """Départ chaud éventuel, découpage par volatilité, puis départs aléatoires ; un seul départ si K = 1."""
    starts: list[HMMParams] = []
    if warm_start is not None and warm_start.k == n_states:
        starts.append(warm_start)
    starts.append(_init_params(features, n_states, rng, "vol"))
    while len(starts) < max(n_init, 1) + (1 if warm_start is not None else 0):
        starts.append(_init_params(features, n_states, rng, "random"))
    if n_states == 1:
        starts = starts[:1]
    return starts


def _em(features: np.ndarray, params: HMMParams, settings: EMSettings) -> HMMFit:
    """EM de Baum-Welch depuis ``params``, jusqu'à convergence ou ``max_iter`` itérations."""
    n_months = features.shape[0]
    previous = -np.inf
    converged = False
    iteration = 0
    for iteration in range(1, settings.max_iter + 1):  # noqa: B007 - iteration sert après la boucle (n_iter)
        log_b = log_emissions(features, params.means, params.covariances)
        loglik, gamma, xi_sum, _ = forward_backward(log_b, params.initial_distribution, params.transition_matrix)
        params = _m_step(features, gamma, xi_sum)
        if abs(loglik - previous) < settings.tol * max(1.0, abs(loglik)):
            converged = True
            break
        previous = loglik
    log_b = log_emissions(features, params.means, params.covariances)
    loglik, gamma, _, last = forward_backward(log_b, params.initial_distribution, params.transition_matrix)
    bic = -2 * loglik + params.n_params() * math.log(n_months)
    return HMMFit(params, loglik, bic, iteration, converged, gamma, last)


def fit_hmm(
    features: np.ndarray,
    n_states: int,
    rng: np.random.Generator,
    settings: EMSettings = _DEFAULT_EM,
    *,
    warm_start: HMMParams | None = None,
) -> HMMFit:
    """Ajuste un HMM gaussien à ``features`` (T, d), standardisé par l'appelant. Garde la meilleure vraisemblance
    parmi ``settings.n_init`` départs (le premier : découpage par volatilité ; les autres : aléatoires, graine
    ``rng``)."""
    best: HMMFit | None = None
    for params in _starting_points(features, n_states, rng, settings.n_init, warm_start):
        fit = _em(features, params, settings)
        if best is None or fit.loglik > best.loglik:
            best = fit
    assert best is not None
    return _order_states(best)


def _order_states(fit: HMMFit) -> HMMFit:
    """Ordonne les états par variance moyenne croissante (état 0 = le plus calme) pour des étiquettes stables."""
    order = np.argsort([np.trace(covariance) for covariance in fit.params.covariances])
    unordered = fit.params
    params = HMMParams(
        unordered.initial_distribution[order],
        unordered.transition_matrix[np.ix_(order, order)],
        unordered.means[order],
        unordered.covariances[order],
    )
    return HMMFit(params, fit.loglik, fit.bic, fit.n_iter, fit.converged, fit.gamma[:, order], fit.filtered_last[order])


def simulate_chain(transition: np.ndarray, init: np.ndarray, n_paths: int, n_months: int, rng: np.random.Generator):
    """Chaîne de régimes ``(n_paths, n_months)`` (vectorisée sur les trajectoires)."""
    n_states = len(init)
    states = np.empty((n_paths, n_months), dtype=np.int8)
    if n_states == 1:
        states[:] = 0
        return states
    cum_transition = np.cumsum(transition, axis=1)
    cum_transition[:, -1] = 1.0
    cum_init = np.cumsum(init)
    cum_init[-1] = 1.0
    uniforms = rng.random((n_paths, n_months))
    states[:, 0] = np.searchsorted(cum_init, uniforms[:, 0], side="right")
    for t in range(1, n_months):
        rows = cum_transition[states[:, t - 1]]
        states[:, t] = (uniforms[:, t, None] >= rows).sum(axis=1)
    return states
