"""Validation statistique des stratégies testées : Sharpe, PSR, DSR, PBO (CSCV). Numpy/scipy seulement.

Références (formules reprises de mémoire, à relire avant citation dans la doc) :
- Bailey D. H. & López de Prado M. (2012), « The Sharpe Ratio Efficient Frontier », J. of Risk — PSR [non vérifié].
- Bailey D. H. & López de Prado M. (2014), « The Deflated Sharpe Ratio », J. of Portfolio Management [non vérifié].
- Bailey D. H., Borwein J., López de Prado M. & Zhu Q. J. (2016), « The Probability of Backtest Overfitting »,
  J. of Computational Finance — CSCV [non vérifié].

Conventions : rendements **mensuels** simples ; PSR et DSR utilisent le Sharpe **par période** (non annualisé) et
le nombre d'observations ; ``kurt`` est la kurtosis brute (3 pour une loi normale).
"""

from __future__ import annotations

import math
from itertools import combinations

import numpy as np
from scipy import stats

EULER_GAMMA = 0.5772156649015329


def sharpe_ratio(r, periods: int = 12) -> float:
    """Sharpe annualisé (×√periods) de rendements en excès ; ``periods=1`` donne le Sharpe par période."""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < 2:
        return float("nan")
    sd = r.std(ddof=1)
    if sd <= 0:
        return float("nan")
    return float(r.mean() / sd * math.sqrt(periods))


def moments(r) -> tuple[int, float, float]:
    """(n, asymétrie, kurtosis brute) des rendements."""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < 3 or r.std() == 0:
        return int(r.size), 0.0, 3.0
    return int(r.size), float(stats.skew(r)), float(stats.kurtosis(r, fisher=False))


def probabilistic_sharpe(sr: float, sr_benchmark: float, n_obs: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    """PSR = Φ((SR − SR*)·√(n−1) / √(1 − γ3·SR + (γ4−1)/4·SR²)), Sharpe par période [non vérifié]."""
    if n_obs < 2 or not math.isfinite(sr):
        return float("nan")
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    if denom <= 0:
        return float("nan")
    return float(stats.norm.cdf((sr - sr_benchmark) * math.sqrt(n_obs - 1) / math.sqrt(denom)))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """E[max des Sharpe de N essais sans compétence] ≈ √V·((1−γ)Φ⁻¹(1−1/N) + γΦ⁻¹(1−1/(N·e))) [non vérifié].
    0 pour un seul essai ; γ = constante d'Euler-Mascheroni."""
    if n_trials <= 1 or var_sr <= 0:
        return 0.0
    n = float(n_trials)
    return float(
        math.sqrt(var_sr)
        * ((1 - EULER_GAMMA) * stats.norm.ppf(1 - 1 / n) + EULER_GAMMA * stats.norm.ppf(1 - 1 / (n * math.e)))
    )


def deflated_sharpe(  # noqa: PLR0913 - signature publique gelée : overlays/gate.py passe les six par position
    sr: float, n_trials: int, n_obs: int, skew: float = 0.0, kurt: float = 3.0, var_trials_sr: float = 0.0
) -> float:
    """DSR = PSR(SR* = E[max SR] des N essais) ; Sharpe et variance des Sharpe des essais par période."""
    return probabilistic_sharpe(sr, expected_max_sharpe(n_trials, var_trials_sr), n_obs, skew, kurt)


def _block_sharpe(x: np.ndarray) -> np.ndarray:
    sd = x.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(sd > 0, x.mean(axis=0) / sd, 0.0)


def pbo_cscv(perf_matrix: np.ndarray, S: int = 16) -> float:  # noqa: N803 - paramètre public gelé (tests : S=…)
    """Probabilité de sur-ajustement par validation croisée combinatoire symétrique (CSCV) [non vérifié].

    ``perf_matrix`` : T × N (rendements par période de N stratégies). Les T lignes sont coupées en S blocs
    contigus (S pair, réduit si T est trop court ; les dernières lignes au-delà d'un multiple de S sont ignorées).
    Pour chaque choix de S/2 blocs en échantillon : la meilleure stratégie en échantillon (Sharpe) est classée hors
    échantillon, ω = rang/(N+1), λ = logit(ω) ; PBO = part des λ ≤ 0. Retourne NaN si N < 2 ou T < 4.
    """
    m = np.asarray(perf_matrix, dtype=float)
    if m.ndim != 2 or m.shape[1] < 2 or m.shape[0] < 4:
        return float("nan")
    n_rows, n_strategies = m.shape
    n_blocks = int(min(S, n_rows // 2))
    n_blocks -= n_blocks % 2
    if n_blocks < 2:
        return float("nan")
    m = m[: (n_rows // n_blocks) * n_blocks]
    blocks = np.array_split(np.arange(m.shape[0]), n_blocks)
    lambdas = []
    for is_idx in combinations(range(n_blocks), n_blocks // 2):
        oos_idx = [b for b in range(n_blocks) if b not in is_idx]
        is_rows = np.concatenate([blocks[b] for b in is_idx])
        oos_rows = np.concatenate([blocks[b] for b in oos_idx])
        sr_is, sr_oos = _block_sharpe(m[is_rows]), _block_sharpe(m[oos_rows])
        best = int(np.argmax(sr_is))
        rank = float(stats.rankdata(sr_oos)[best])  # 1 = pire … N = meilleur
        omega = rank / (n_strategies + 1)
        lambdas.append(math.log(omega / (1 - omega)))
    return float(np.mean(np.asarray(lambdas) <= 0))
