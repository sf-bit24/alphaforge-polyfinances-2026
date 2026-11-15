"""Générateurs de scénarios. Chacun a un ``model_id``, s'ajuste sur un pool par ``fit(pool, fitted_through=...)``
et produit des **indices de mois historiques** ; les rendements simulés sont donc toujours des mois observés
(toutes les colonnes ensemble), jamais des tirages d'une loi paramétrique.

Règle anti look-ahead : ``fit`` tronque le pool à ``fitted_through`` **avant** tout calcul (longueur de bloc,
standardisation, EM du HMM, choix de K). L'objet ajusté ne garde que le pool tronqué.

Modèles :

- ``sbb`` : bootstrap stationnaire joint, longueur moyenne de bloc automatique (Politis-White), bornée ;
- ``iid`` : bootstrap de mois indépendants (bloc de 1), référence naïve sans dépendance temporelle ;
- ``hmm_rs`` : régimes cachés (HMM gaussien, K choisi par BIC parmi ``k_candidates``) ; on simule la chaîne de
  régimes puis on tire, pour chaque mois simulé, un mois historique avec une probabilité proportionnelle à sa
  probabilité lissée d'appartenir au régime simulé.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .bootstrap import auto_block_length, politis_white, stationary_indices
from .data import Pool
from .hmm import HMMFit, fit_hmm, simulate_chain

MODEL_IDS = ("sbb", "iid", "hmm_rs", "sbb_ca", "iid_ca", "hmm_rs_ca", "hmm_rs_fl")


def rng_for(seed: int, *parts: str | int) -> np.random.Generator:
    """Générateur déterministe pour (graine, étiquettes). Les chaînes passent par crc32 (stable entre exécutions,
    contrairement à ``hash()``)."""
    keys = [int(seed)] + [zlib.crc32(p.encode()) if isinstance(p, str) else int(p) for p in parts]
    return np.random.default_rng(np.random.SeedSequence(keys))


@dataclass
class Fitted:
    model_id: str
    pool: Pool
    info: dict[str, Any]
    mean_block: float = 1.0
    hmm: HMMFit | None = None
    hmm_init: str = "stationary"
    _cdfs: list[np.ndarray] = field(default_factory=list)

    @property
    def fitted_through(self) -> str:
        return self.pool.fitted_through

    def simulate_indices(self, n_paths: int, n_months: int, rng: np.random.Generator) -> np.ndarray:
        n = self.pool.n
        if self.hmm is None:
            return stationary_indices(n, n_paths, n_months, self.mean_block, rng)
        assert self.hmm is not None
        p = self.hmm.params
        init = p.stationary() if self.hmm_init == "stationary" else self.hmm.filtered_last
        states = simulate_chain(p.A, init, n_paths, n_months, rng)
        u = rng.random((n_paths, n_months))
        idx = np.empty((n_paths, n_months), dtype=np.int32)
        for k, cdf in enumerate(self._cdfs):
            mask = states == k
            idx[mask] = np.minimum(np.searchsorted(cdf, u[mask], side="right"), n - 1)
        return idx

    def pseudo_history(self, rng: np.random.Generator) -> Pool:
        """Pseudo-historique de même longueur tiré du modèle ajusté (bootstrap fondé sur le modèle)."""
        idx = self.simulate_indices(1, self.pool.n, rng)[0]
        return self.pool.take(idx, name_suffix="*")


def excess_returns(pool: Pool) -> np.ndarray:
    """Rendements en excès du cash (colonne CASH inchangée). Sert au choix de la longueur de bloc et aux variables
    du HMM : ces quantités ne dépendent alors pas du niveau des taux, ni donc de l'ancrage ``_ca``."""
    if "CASH" not in pool.blocks:
        return pool.R
    j = pool.blocks.index("CASH")
    X = pool.R - pool.R[:, [j]]
    X[:, j] = pool.R[:, j]
    return X


class Model:
    """Base commune. ``anchor_months`` > 0 active l'ancrage du niveau des taux (``Pool.anchor_cash``) ; le
    ``model_id`` reçoit alors le suffixe ``_ca`` (par exemple ``sbb_ca``)."""

    base_id = "base"
    anchor_months = 0

    @property
    def model_id(self) -> str:
        return self.base_id + ("_ca" if self.anchor_months else "")

    def fit(self, pool: Pool, fitted_through: str | None = None, *, rng: np.random.Generator | None = None) -> Fitted:
        """Tronque à ``fitted_through``, applique l'ancrage éventuel (sur la fenêtre tronquée), puis ajuste."""
        pool = pool.truncate(fitted_through)
        extra: dict[str, Any] = {}
        if self.anchor_months:
            pool, extra = pool.anchor_cash(self.anchor_months)
        fitted = self._fit(pool, rng or np.random.default_rng(0))
        fitted.info.update(extra)
        return fitted

    def _fit(self, pool: Pool, rng: np.random.Generator) -> Fitted:
        raise NotImplementedError

    def refit(self, fitted: Fitted, pool: Pool, rng: np.random.Generator) -> Fitted:
        """Réajustement sur un pseudo-historique (bootstrap externe), déjà ancré s'il y a lieu ; ajustement complet."""
        return self._fit(pool, rng)


class StationaryBootstrap(Model):
    base_id = "sbb"

    def __init__(
        self,
        block_length: float | str = "auto",
        *,
        rule: str = "max",
        include_squared: bool = True,
        exclude_blocks: tuple[str, ...] = ("CASH",),
        min_block: float = 1.0,
        max_block: float = 24.0,
        anchor_months: int = 0,
    ):
        self.anchor_months = int(anchor_months)
        self.block_length = block_length
        self.rule = rule
        self.include_squared = include_squared
        self.exclude_blocks = tuple(exclude_blocks)
        self.min_block = float(min_block)
        self.max_block = float(max_block)

    def choose_block(self, pool: Pool) -> tuple[float, dict[str, Any]]:
        if self.block_length != "auto":
            value = float(self.block_length)
            return value, {"block_rule": "fixed", "mean_block": value}
        cols = [j for j, b in enumerate(pool.blocks) if b not in self.exclude_blocks]
        X = excess_returns(pool)
        _, per_level = auto_block_length(X, cols, "max")
        per_sq = [politis_white(X[:, j] ** 2) for j in cols] if self.include_squared else []
        values = per_level + per_sq
        raw = float(max(values)) if self.rule == "max" else float(np.median(values))
        value = float(min(max(raw, self.min_block), self.max_block))
        detail = {
            "block_rule": f"politis_white_{self.rule}_excess" + ("_with_squared" if self.include_squared else ""),
            "block_raw": round(raw, 3),
            "block_bounds": [self.min_block, self.max_block],
            "mean_block": round(value, 3),
            "pw_levels": {pool.blocks[j]: round(v, 3) for j, v in zip(cols, per_level, strict=True)},
        }
        if per_sq:
            detail["pw_squared"] = {pool.blocks[j]: round(v, 3) for j, v in zip(cols, per_sq, strict=True)}
        return value, detail

    def _fit(self, pool: Pool, rng: np.random.Generator) -> Fitted:
        value, detail = self.choose_block(pool)
        info = {"model_id": self.model_id, "pool": pool.name, "fitted_through": pool.fitted_through, **detail}
        return Fitted(self.model_id, pool, info, mean_block=value)


class IIDBootstrap(StationaryBootstrap):
    base_id = "iid"

    def __init__(self, anchor_months: int = 0):
        super().__init__(block_length=1.0, anchor_months=anchor_months)


class RegimeBootstrap(Model):
    base_id = "hmm_rs"

    @property
    def model_id(self) -> str:
        """``hmm_rs``, ``hmm_rs_ca`` ; ``hmm_rs_fl`` si la chaîne démarre dans le régime filtré du dernier mois."""
        if self.initial_state == "filtered_last":
            return self.base_id + "_fl" + ("_ca" if self.anchor_months else "")
        return self.base_id + ("_ca" if self.anchor_months else "")

    def __init__(
        self,
        k_candidates: tuple[int, ...] = (1, 2, 3),
        *,
        exclude_blocks: tuple[str, ...] = ("CASH",),
        n_init: int = 4,
        max_iter: int = 300,
        tol: float = 1e-7,
        initial_state: str = "stationary",
        refit_n_init: int = 1,
        refit_max_iter: int = 100,
        anchor_months: int = 0,
    ):
        self.anchor_months = int(anchor_months)
        self.k_candidates = tuple(k_candidates)
        self.exclude_blocks = tuple(exclude_blocks)
        self.n_init = n_init
        self.max_iter = max_iter
        self.tol = tol
        if initial_state not in ("stationary", "filtered_last"):
            raise ValueError("initial_state doit valoir 'stationary' ou 'filtered_last'")
        self.initial_state = initial_state
        self.refit_n_init = refit_n_init
        self.refit_max_iter = refit_max_iter

    def _features(self, pool: Pool) -> tuple[np.ndarray, list[str]]:
        cols = [j for j, b in enumerate(pool.blocks) if b not in self.exclude_blocks]
        X = excess_returns(pool)[:, cols]
        mu, sd = X.mean(axis=0), X.std(axis=0)
        sd[sd == 0] = 1.0
        return (X - mu) / sd, [pool.blocks[j] for j in cols]

    def _finish(self, pool: Pool, fit: HMMFit, info: dict[str, Any]) -> Fitted:
        gamma = fit.gamma
        cdfs = []
        for k in range(gamma.shape[1]):
            w = gamma[:, k] / gamma[:, k].sum()
            cdf = np.cumsum(w)
            cdf[-1] = 1.0
            cdfs.append(cdf)
        p = fit.params
        info = {
            **info,
            "k": p.k,
            "loglik": round(fit.loglik, 3),
            "converged": fit.converged,
            "n_iter": fit.n_iter,
            "initial_state": self.initial_state,
            "transition": np.round(p.A, 4).tolist(),
            "stationary": np.round(p.stationary(), 4).tolist(),
            "expected_duration_months": [
                round(float(1.0 / (1.0 - p.A[k, k])), 2) if p.A[k, k] < 1.0 - 1e-9 else None for k in range(p.k)
            ],
            "regime_monthly_vol": _regime_vol(pool, gamma),
            "regime_share_months": np.round(gamma.mean(axis=0), 4).tolist(),
        }
        return Fitted(self.model_id, pool, info, hmm=fit, hmm_init=self.initial_state, _cdfs=cdfs)

    def _fit(self, pool: Pool, rng: np.random.Generator) -> Fitted:
        X, names = self._features(pool)
        fits = {}
        # Un générateur dédié par K, dérivé d'une seule graine tirée de ``rng`` : les départs de K = 2 ou 3 ne
        # dépendent ni des tirages faits pour les autres K, ni de la liste ``k_candidates``.
        root = int(rng.integers(0, 2**63 - 1))
        for K in self.k_candidates:
            rng_k = np.random.default_rng(np.random.SeedSequence(root, spawn_key=(int(K),)))
            fits[K] = fit_hmm(X, K, rng_k, n_init=self.n_init, max_iter=self.max_iter, tol=self.tol)
        best_k = min(fits, key=lambda k: fits[k].bic)
        info = {
            "model_id": self.model_id,
            "pool": pool.name,
            "fitted_through": pool.fitted_through,
            "features": names,
            "k_selection": "bic",
            "bic": {str(k): round(f.bic, 2) for k, f in fits.items()},
        }
        return self._finish(pool, fits[best_k], info)

    def refit(self, fitted: Fitted, pool: Pool, rng: np.random.Generator) -> Fitted:
        """Bootstrap externe : K fixé à celui de l'ajustement principal, départ chaud + ``refit_n_init`` départs."""
        assert fitted.hmm is not None
        X, names = self._features(pool)
        fit = fit_hmm(
            X,
            fitted.hmm.params.k,
            rng,
            n_init=self.refit_n_init,
            max_iter=self.refit_max_iter,
            tol=1e-6,
            warm_start=fitted.hmm.params,
        )
        info = {"model_id": self.model_id, "pool": pool.name, "features": names, "k_selection": "fixed_from_main"}
        return self._finish(pool, fit, info)


def _regime_vol(pool: Pool, gamma: np.ndarray) -> dict[str, list[float]]:
    out = {}
    for j, b in enumerate(pool.blocks):
        vols = []
        for k in range(gamma.shape[1]):
            w = gamma[:, k] / gamma[:, k].sum()
            m = float(w @ pool.R[:, j])
            vols.append(round(float(np.sqrt(w @ (pool.R[:, j] - m) ** 2)), 5))
        out[b] = vols
    return out


def make_model(model_id: str, params: dict[str, Any] | None = None) -> Model:
    """``sbb``, ``iid``, ``hmm_rs`` ; suffixe ``_ca`` = même modèle avec ancrage du niveau des taux (12 mois par
    défaut, ``anchor_months`` dans ``params`` pour changer)."""
    params = dict(params or {})
    base = model_id[:-3] if model_id.endswith("_ca") else model_id
    if base == "hmm_rs_fl":
        base = "hmm_rs"
        params["initial_state"] = "filtered_last"
    if model_id.endswith("_ca"):
        params["anchor_months"] = int(params.get("anchor_months") or 12)
    else:
        params.pop("anchor_months", None)
    for key in ("exclude_blocks", "k_candidates"):
        if key in params:
            params[key] = tuple(params[key])
    if base == "sbb":
        model: Model = StationaryBootstrap(**params)
    elif base == "iid":
        model = IIDBootstrap(anchor_months=params.get("anchor_months", 0))
    elif base == "hmm_rs":
        model = RegimeBootstrap(**params)
    else:
        raise ValueError(f"model_id inconnu : {model_id!r} (attendu : {MODEL_IDS}, suffixe _ca possible)")
    return model


def fit(
    pool: Pool,
    model_id: str = "sbb",
    fitted_through: str | None = None,
    *,
    seed: int = 0,
    params: dict[str, Any] | None = None,
) -> Fitted:
    """Point d'entrée walk-forward : ajuste ``model_id`` sur les mois <= ``fitted_through`` seulement."""
    model = make_model(model_id, params)
    return model.fit(pool, fitted_through, rng=rng_for(seed, pool.name, model_id, "fit", fitted_through or "all"))
