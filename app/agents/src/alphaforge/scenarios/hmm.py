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
    pi: np.ndarray  # (K,)
    A: np.ndarray  # (K, K)
    means: np.ndarray  # (K, d)
    covs: np.ndarray  # (K, d, d)

    @property
    def k(self) -> int:
        return len(self.pi)

    def n_params(self) -> int:
        k, d = self.means.shape
        return (k - 1) + k * (k - 1) + k * d + k * d * (d + 1) // 2

    def stationary(self) -> np.ndarray:
        if self.k == 1:
            return np.ones(1)
        w, v = np.linalg.eig(self.A.T)
        s = np.real(v[:, np.argmin(np.abs(w - 1.0))])
        s = np.abs(s) / np.abs(s).sum()
        return s


@dataclass
class HMMFit:
    params: HMMParams
    loglik: float
    bic: float
    n_iter: int
    converged: bool
    gamma: np.ndarray  # (T, K) probabilités lissées des régimes
    filtered_last: np.ndarray  # (K,) probabilité filtrée du dernier mois (sans information future)


def log_emissions(X: np.ndarray, means: np.ndarray, covs: np.ndarray) -> np.ndarray:
    T, d = X.shape
    out = np.empty((T, len(means)))
    for k in range(len(means)):
        chol = np.linalg.cholesky(covs[k])
        z = np.linalg.solve(chol, (X - means[k]).T)
        logdet = 2.0 * np.log(np.diag(chol)).sum()
        out[:, k] = -0.5 * (d * math.log(2 * math.pi) + logdet + (z * z).sum(axis=0))
    return out


def forward_backward(logb: np.ndarray, pi: np.ndarray, A: np.ndarray):
    """Renvoie (loglik, gamma (T,K), xi_sum (K,K), filtré du dernier mois)."""
    T, K = logb.shape
    shift = logb.max(axis=1, keepdims=True)
    b = np.exp(logb - shift)
    alpha = np.empty((T, K))
    c = np.empty(T)
    a = pi * b[0]
    c[0] = a.sum()
    alpha[0] = a / c[0]
    for t in range(1, T):
        a = (alpha[t - 1] @ A) * b[t]
        c[t] = a.sum()
        alpha[t] = a / c[t]
    beta = np.empty((T, K))
    beta[-1] = 1.0
    for t in range(T - 2, -1, -1):
        beta[t] = (A @ (b[t + 1] * beta[t + 1])) / c[t + 1]
    gamma = alpha * beta
    gamma /= gamma.sum(axis=1, keepdims=True)
    # xi_t(i,j) = alpha_t(i) A(i,j) b_{t+1}(j) beta_{t+1}(j) / c_{t+1}
    w = b[1:] * beta[1:] / c[1:, None]
    xi_sum = A * (alpha[:-1].T @ w)
    loglik = float(np.log(c).sum() + shift.sum())
    return loglik, gamma, xi_sum, alpha[-1].copy()


def _m_step(X: np.ndarray, gamma: np.ndarray, xi_sum: np.ndarray) -> HMMParams:
    T, d = X.shape
    K = gamma.shape[1]
    weights = gamma.sum(axis=0) + 1e-12
    means = (gamma.T @ X) / weights[:, None]
    covs = np.empty((K, d, d))
    for k in range(K):
        diff = X - means[k]
        covs[k] = (gamma[:, k, None] * diff).T @ diff / weights[k] + _REG * np.eye(d)
    A = xi_sum + 1e-12
    A /= A.sum(axis=1, keepdims=True)
    return HMMParams(gamma[0] + 1e-12, A, means, covs)


def _init_params(X: np.ndarray, K: int, rng: np.random.Generator, how: str) -> HMMParams:
    T, d = X.shape
    if K == 1 or how == "vol":
        # États ordonnés par l'amplitude du facteur commun (moyenne des colonnes), lissée sur 6 mois.
        f = np.abs(X.mean(axis=1))
        smooth = np.convolve(f, np.ones(6) / 6, mode="same")
        edges = np.quantile(smooth, np.linspace(0, 1, K + 1)[1:-1]) if K > 1 else []
        labels = np.searchsorted(edges, smooth) if K > 1 else np.zeros(T, dtype=int)
    else:
        labels = rng.integers(0, K, size=T)
        # quelques segments contigus pour amorcer la persistance
        seg = max(T // (4 * K), 1)
        labels = np.repeat(labels[::seg], seg)[:T]
        if len(labels) < T:
            labels = np.pad(labels, (0, T - len(labels)), mode="edge")
    gamma = np.full((T, K), 1e-3)
    gamma[np.arange(T), labels] = 1.0
    gamma /= gamma.sum(axis=1, keepdims=True)
    xi = np.full((K, K), 1.0) + np.eye(K) * 9.0 * T / K
    return _m_step(X, gamma, xi)


def fit_hmm(
    X: np.ndarray,
    K: int,
    rng: np.random.Generator,
    *,
    n_init: int = 3,
    max_iter: int = 200,
    tol: float = 1e-6,
    warm_start: HMMParams | None = None,
) -> HMMFit:
    """Ajuste un HMM gaussien à ``X`` (T, d), standardisé par l'appelant. Garde la meilleure vraisemblance parmi
    ``n_init`` départs (le premier : découpage par volatilité ; les autres : aléatoires, graine ``rng``)."""
    T, d = X.shape
    starts: list[HMMParams] = []
    if warm_start is not None and warm_start.k == K:
        starts.append(warm_start)
    starts.append(_init_params(X, K, rng, "vol"))
    while len(starts) < max(n_init, 1) + (1 if warm_start is not None else 0):
        starts.append(_init_params(X, K, rng, "random"))
    if K == 1:
        starts = starts[:1]
    best: HMMFit | None = None
    for params in starts:
        prev = -np.inf
        converged = False
        it = 0
        for it in range(1, max_iter + 1):  # noqa: B007 - it sert après la boucle (n_iter)
            logb = log_emissions(X, params.means, params.covs)
            ll, gamma, xi_sum, _ = forward_backward(logb, params.pi, params.A)
            params = _m_step(X, gamma, xi_sum)
            if abs(ll - prev) < tol * max(1.0, abs(ll)):
                converged = True
                break
            prev = ll
        logb = log_emissions(X, params.means, params.covs)
        ll, gamma, _, last = forward_backward(logb, params.pi, params.A)
        fit = HMMFit(params, ll, -2 * ll + params.n_params() * math.log(T), it, converged, gamma, last)
        if best is None or fit.loglik > best.loglik:
            best = fit
    assert best is not None
    return _order_states(best)


def _order_states(fit: HMMFit) -> HMMFit:
    """Ordonne les états par variance moyenne croissante (état 0 = le plus calme) pour des étiquettes stables."""
    order = np.argsort([np.trace(c) for c in fit.params.covs])
    p = fit.params
    params = HMMParams(p.pi[order], p.A[np.ix_(order, order)], p.means[order], p.covs[order])
    return HMMFit(params, fit.loglik, fit.bic, fit.n_iter, fit.converged, fit.gamma[:, order], fit.filtered_last[order])


def simulate_chain(A: np.ndarray, init: np.ndarray, n_paths: int, n_months: int, rng: np.random.Generator):
    """Chaîne de régimes ``(n_paths, n_months)`` (vectorisée sur les trajectoires)."""
    K = len(init)
    states = np.empty((n_paths, n_months), dtype=np.int8)
    if K == 1:
        states[:] = 0
        return states
    cum_a = np.cumsum(A, axis=1)
    cum_a[:, -1] = 1.0
    cum_init = np.cumsum(init)
    cum_init[-1] = 1.0
    u = rng.random((n_paths, n_months))
    states[:, 0] = np.searchsorted(cum_init, u[:, 0], side="right")
    for t in range(1, n_months):
        rows = cum_a[states[:, t - 1]]
        states[:, t] = (u[:, t, None] >= rows).sum(axis=1)
    return states
