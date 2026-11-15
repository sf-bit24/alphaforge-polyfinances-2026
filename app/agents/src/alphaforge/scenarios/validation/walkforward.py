"""Évaluation walk-forward hors échantillon des générateurs de scénarios.

Pour chaque origine T (fin d'année civile), chaque modèle est ajusté par l'API publique
``models.fit(pool, model_id, fitted_through=T)`` : il ne voit que les mois <= T. Sa distribution prédictive du
rendement annualisé, de la perte maximale et de la richesse finale sur H ans (mois T+1 .. T+12·H) est comparée au
résultat réalisé de ces mêmes mois. Les mois postérieurs à T ne servent **qu'**à mesurer le résultat réalisé.

Étiquetage des mélanges : toujours **actions d'abord, revenu fixe ensuite**, par exemple ``eq30_fi70`` = 30 %
actions / 70 % obligations. Pour CAD77, les actions sont réparties 50/50 entre CA_EQ et US_MKT ; pour CAD71 et
USD1926/USD1953, elles sont 100 % US_MKT. ``eq00_cs100`` = 100 % cash (marché monétaire), ``eq00_fi100`` = 100 %
obligations (10 ans).

Repères comparés aux modèles :

- ``hist_emp`` : distribution empirique naïve des fenêtres glissantes de H ans entièrement contenues dans
  l'historique <= T (même pool, même début de fenêtre) ;
- ``stress_2022`` : prévision ponctuelle « 2022 seulement » (rendement de l'année civile 2022 pour tous les
  horizons, perte maximale de 2022). **Ce repère utilise des données de 2022** : pour les origines antérieures à
  2022, c'est un avantage d'information (look-ahead) en sa faveur, assumé parce que c'est le contrôle actuel du
  produit.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..data import Pool, build_pool, load_inputs
from ..engine import hist_log_returns, weight_matrix
from ..models import Fitted, fit, rng_for
from ..schema import mix_id
from .scoring import crps_samples, path_outcomes, pinball, pit, realized_outcome, rolling_outcomes

# Paramètres des modèles : ceux de configs/full.yaml (référence du produit).
SBB_PARAMS = {"rule": "max", "include_squared": True, "exclude_blocks": ["CASH"], "min_block": 1, "max_block": 24}
HMM_PARAMS = {"k_candidates": [1, 2, 3], "exclude_blocks": ["CASH"], "n_init": 6, "initial_state": "stationary"}

# étiquette -> (model_id de l'API, paramètres)
MODEL_SPECS: dict[str, tuple[str, dict[str, Any]]] = {
    "sbb": ("sbb", SBB_PARAMS),
    "iid": ("iid", {}),
    "hmm_rs": ("hmm_rs", HMM_PARAMS),
    "hmm_rs_fl": ("hmm_rs", {**HMM_PARAMS, "initial_state": "filtered_last"}),
    "sbb_ca": ("sbb_ca", SBB_PARAMS),
    "iid_ca": ("iid_ca", {}),
    "hmm_rs_ca": ("hmm_rs_ca", HMM_PARAMS),
    # sensibilité à la borne de la longueur moyenne de bloc (24 mois dans le produit)
    "sbb_L06": ("sbb", {**SBB_PARAMS, "max_block": 6}),
    "sbb_L12": ("sbb", {**SBB_PARAMS, "max_block": 12}),
    "sbb_L48": ("sbb", {**SBB_PARAMS, "max_block": 48}),
    "sbb_L96": ("sbb", {**SBB_PARAMS, "max_block": 96}),
}
CORE_MODELS = ("sbb", "iid", "hmm_rs", "hmm_rs_fl", "sbb_ca", "iid_ca", "hmm_rs_ca")
BLOCK_MODELS = ("sbb_L06", "sbb_L12", "sbb_L48", "sbb_L96")
BASELINES = ("hist_emp", "stress_2022")

LOSS_EVENTS = (0, 10, 20)  # P(perte cumulée à l'horizon > x %)
MDD_EVENTS = (10, 20, 30)  # P(perte maximale sur l'horizon > x %)
RET_Q = (0.05, 0.10, 0.50, 0.90, 0.95)
MDD_Q = (0.05, 0.10, 0.50, 0.90, 0.95)


def _mixes_for(family: str) -> dict[str, str]:
    """Mélanges représentatifs, actions d'abord : ``eqXX_fiYY`` (actions XX %, obligations YY %)."""
    if family == "CAD77":

        def equity_mix(equity_pct):
            return {"CA_EQ": equity_pct / 200.0, "US_MKT": equity_pct / 200.0, "BONDS": (100 - equity_pct) / 100.0}
    else:

        def equity_mix(equity_pct):
            return {"US_MKT": equity_pct / 100.0, "BONDS": (100 - equity_pct) / 100.0}

    out = {f"eq{equity:02d}_fi{100 - equity:02d}": mix_id(equity_mix(equity)) for equity in (0, 30, 40, 70)}
    out["eq100_fi00"] = mix_id(equity_mix(100))
    out["eq00_cs100"] = mix_id({"CASH": 1.0})
    return dict(sorted(out.items(), key=lambda item: (item[0] == "eq00_cs100", item[0])))


# Familles : celles du produit + USD1953 (USD1926 sans les 327 mois d'obligations du taux long de Shiller, lissé),
# pour le contrôle (iii) du HMM.
FAMILY_FIRST_ORIGIN = {"CAD77": "1990-12", "CAD71": "1975-12", "USD1926": "1950-12", "USD1953": "1963-12"}


def make_pools(inputs) -> dict[str, Pool]:
    pools = {family: build_pool(inputs, family) for family in ("CAD77", "CAD71", "USD1926")}
    usd1926 = pools["USD1926"]
    keep = np.flatnonzero(np.asarray(usd1926.dates >= pd.Timestamp("1953-04-30")))
    usd1953 = usd1926._subset(keep)
    usd1953.name = "USD1953"
    pools["USD1953"] = usd1953
    return pools


@dataclass
class WFConfig:
    input_dir: str
    seed: int = 20261114
    n_paths: int = 4000
    horizons: tuple[int, ...] = (1, 3, 5, 10)
    origin_step_years: int = 1
    families: tuple[str, ...] = ("CAD77", "CAD71", "USD1926", "USD1953")
    models: tuple[str, ...] = CORE_MODELS
    block_models_families: tuple[str, ...] = ("CAD77", "USD1926")
    first_origin: dict[str, str] = field(default_factory=lambda: dict(FAMILY_FIRST_ORIGIN))
    max_origins: int | None = None  # pour les tests : limite le nombre d'origines par famille
    workers: int = 1


def origins_for(pool: Pool, first: str, step_years: int, max_h: int) -> list[str]:
    """Origines « YYYY-12 » de ``first`` jusqu'à la dernière qui laisse au moins 12 mois réalisés."""
    last = pool.dates[-1]
    out = []
    for year in range(int(first[:4]), last.year + 1, step_years):
        year_end = pd.Timestamp(f"{year}-12-31")
        if year_end + pd.DateOffset(months=12) <= last + pd.offsets.MonthEnd(0):
            out.append(f"{year}-12")
    return out


_STATE: dict[str, Any] = {}


def _init_worker(input_dir: str) -> None:
    _STATE["pools"] = make_pools(load_inputs(input_dir))


def _stress_2022(pool: Pool, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    log_returns = hist_log_returns(pool, weights)["nominal"]
    in_2022 = np.asarray(pool.dates.year == 2022)
    cum = np.vstack([np.zeros((1, log_returns.shape[1])), np.cumsum(log_returns[in_2022], axis=0)])
    return_2022 = np.expm1(cum[-1])
    mdd_2022 = -np.expm1(-(np.maximum.accumulate(cum, axis=0) - cum).max(axis=0))
    return return_2022, mdd_2022


def _record(
    base: dict, samples: dict[str, np.ndarray], realized: tuple[float, float, float], uniforms: np.ndarray
) -> dict:
    """Scores d'une distribution prédictive (échantillons ``ret``, ``mdd``, ``logw``) contre un résultat réalisé
    (rendement, perte max., log-richesse) ; ``uniforms`` : deux tirages U(0, 1) pour les PIT."""
    ret_s, mdd_s, logw_s = samples["ret"], samples["mdd"], samples["logw"]
    y_ret, y_mdd, y_logw = realized
    ret_q = np.quantile(ret_s, RET_Q)
    mdd_q = np.quantile(mdd_s, MDD_Q)
    record = {
        **base,
        "n_samples": int(len(ret_s)),
        "y_ret": y_ret,
        "y_mdd": y_mdd,
        "pit_ret": pit(ret_s, y_ret, float(uniforms[0])),
        "pit_mdd": pit(mdd_s, y_mdd, float(uniforms[1])),
        "crps_ret": crps_samples(ret_s, y_ret),
        "crps_mdd": crps_samples(mdd_s, y_mdd),
        "pin_ret_q05": pinball(ret_q[0], y_ret, 0.05),
        "pin_ret_q10": pinball(ret_q[1], y_ret, 0.10),
        "pin_mdd_q90": pinball(mdd_q[3], y_mdd, 0.90),
        "in80_ret": float(ret_q[1] <= y_ret <= ret_q[3]),
        "in90_ret": float(ret_q[0] <= y_ret <= ret_q[4]),
        "in80_mdd": float(mdd_q[1] <= y_mdd <= mdd_q[3]),
        "in90_mdd": float(mdd_q[0] <= y_mdd <= mdd_q[4]),
        "exc_mdd_q90": float(y_mdd > mdd_q[3]),
        "below_ret_q10": float(y_ret < ret_q[1]),
    }
    for level, value in zip(RET_Q, ret_q, strict=True):
        record[f"ret_q{int(level * 100):02d}"] = float(value)
    for level, value in zip(MDD_Q, mdd_q, strict=True):
        record[f"mdd_q{int(level * 100):02d}"] = float(value)
    for percent in LOSS_EVENTS:
        threshold = np.log1p(-percent / 100.0)
        record[f"p_loss_gt_{percent:02d}"] = float(np.mean(logw_s < threshold))
        record[f"o_loss_gt_{percent:02d}"] = float(y_logw < threshold)
    for percent in MDD_EVENTS:
        record[f"p_mdd_gt_{percent:02d}"] = float(np.mean(mdd_s > percent / 100.0))
        record[f"o_mdd_gt_{percent:02d}"] = float(y_mdd > percent / 100.0)
    return record


def _point_record(
    base: dict, forecast: tuple[float, float], realized: tuple[float, float, float], horizon: int
) -> dict:
    """Prévision ponctuelle (« 2022 seulement ») : CRPS = erreur absolue, probabilités d'événement 0 ou 1."""
    x_ret, x_mdd = forecast
    y_ret, y_mdd, y_logw = realized
    record = {
        **base,
        "n_samples": 1,
        "y_ret": y_ret,
        "y_mdd": y_mdd,
        "pit_ret": np.nan,
        "pit_mdd": np.nan,
        "crps_ret": abs(x_ret - y_ret),
        "crps_mdd": abs(x_mdd - y_mdd),
        "pin_ret_q05": pinball(x_ret, y_ret, 0.05),
        "pin_ret_q10": pinball(x_ret, y_ret, 0.10),
        "pin_mdd_q90": pinball(x_mdd, y_mdd, 0.90),
        "in80_ret": np.nan,
        "in90_ret": np.nan,
        "in80_mdd": np.nan,
        "in90_mdd": np.nan,
        "exc_mdd_q90": float(y_mdd > x_mdd),
        "below_ret_q10": float(y_ret < x_ret),
    }
    for level in RET_Q:
        record[f"ret_q{int(level * 100):02d}"] = x_ret
    for level in MDD_Q:
        record[f"mdd_q{int(level * 100):02d}"] = x_mdd
    x_logw = horizon * np.log1p(x_ret)  # 2022 répété chaque année : richesse (1 + r_2022)^H
    for percent in LOSS_EVENTS:
        threshold = np.log1p(-percent / 100.0)
        record[f"p_loss_gt_{percent:02d}"] = float(x_logw < threshold)
        record[f"o_loss_gt_{percent:02d}"] = float(y_logw < threshold)
    for percent in MDD_EVENTS:
        record[f"p_mdd_gt_{percent:02d}"] = float(x_mdd > percent / 100.0)
        record[f"o_mdd_gt_{percent:02d}"] = float(y_mdd > percent / 100.0)
    return record


@dataclass(frozen=True)
class _OriginContext:
    """Ce que les modèles d'une même origine T partagent : pool, mélanges, horizons évaluables, résultats réalisés."""

    family: str
    origin: str
    pool: Pool
    labels: list[str]
    mix_ids: list[str]
    weights: np.ndarray
    cut: pd.Timestamp  # dernier jour du mois T
    last_month: int  # indice du mois T dans le pool
    horizons: list[int]
    history: np.ndarray  # log-rendements nominaux des mélanges sur tout le pool
    stress: tuple[np.ndarray, np.ndarray]  # « 2022 seulement » : rendement et perte max. de chaque mélange
    realized: dict[int, list[tuple[float, float, float]]]
    seed: int
    n_paths: int
    pit_rng: np.random.Generator


def _realized_outcomes(
    history: np.ndarray, last_month: int, horizons: list[int]
) -> dict[int, list[tuple[float, float, float]]]:
    """Résultat réalisé de chaque mélange sur les mois T+1 .. T+12·H, les seuls mois postérieurs à T lus."""
    return {
        horizon: [
            realized_outcome(history[last_month + 1 : last_month + 1 + 12 * horizon, j])
            for j in range(history.shape[1])
        ]
        for horizon in horizons
    }


def _fit_checked(context: _OriginContext, label: str) -> Fitted:
    """Ajuste ``label`` sur les mois <= T."""
    model_id, params = MODEL_SPECS[label]
    fitted = fit(context.pool, model_id, fitted_through=context.origin, seed=context.seed, params=params)
    # garde-fous anti look-ahead (re-vérifiés à chaque ajustement)
    assert fitted.fitted_through == context.origin, (fitted.fitted_through, context.origin)
    assert fitted.pool.n == context.last_month + 1 and fitted.pool.dates[-1] == context.cut
    return fitted


def _fit_row(context: _OriginContext, label: str, fitted: Fitted) -> dict:
    info = fitted.info
    return {
        "family": context.family,
        "model": label,
        "origin": context.origin,
        "n_hist": fitted.pool.n,
        "mean_block": info.get("mean_block"),
        "block_raw": info.get("block_raw"),
        "k": info.get("k"),
        "cash_scale": info.get("cash_scale"),
    }


def _simulated_outcomes(context: _OriginContext, label: str, fitted: Fitted) -> dict[int, dict[str, np.ndarray]]:
    """Échantillons simulés par horizon ; aucun indice tiré ne dépasse le mois T."""
    rng = rng_for(context.seed, "wf", context.family, label, context.origin)
    indices = fitted.simulate_indices(context.n_paths, 12 * max(context.horizons), rng)
    assert int(indices.max()) <= context.last_month
    log_returns = hist_log_returns(fitted.pool, context.weights)["nominal"]
    return path_outcomes(log_returns, indices, context.horizons)


def _model_rows(context: _OriginContext, label: str, sims: dict[int, dict[str, np.ndarray]]) -> list[dict]:
    rows = []
    for horizon in context.horizons:
        for j, mix in enumerate(context.labels):
            base = {
                "family": context.family,
                "model": label,
                "origin": context.origin,
                "mix": mix,
                "mix_id": context.mix_ids[j],
                "H": horizon,
            }
            samples = {name: values[:, j] for name, values in sims[horizon].items()}
            rows.append(_record(base, samples, context.realized[horizon][j], context.pit_rng.random(2)))
    return rows


def _baseline_rows(context: _OriginContext) -> list[dict]:
    """Repères : fenêtres glissantes de l'historique <= T (``hist_emp``) et « 2022 seulement » (``stress_2022``)."""
    stress_ret, stress_mdd = context.stress
    rows = []
    for horizon in context.horizons:
        for j, mix in enumerate(context.labels):
            realized = context.realized[horizon][j]
            empirical = rolling_outcomes(context.history[: context.last_month + 1, j], horizon)
            base = {
                "family": context.family,
                "origin": context.origin,
                "mix": mix,
                "mix_id": context.mix_ids[j],
                "H": horizon,
            }
            if len(empirical["ret"]) >= 12:
                rows.append(_record({**base, "model": "hist_emp"}, empirical, realized, context.pit_rng.random(2)))
            forecast = (float(stress_ret[j]), float(stress_mdd[j]))
            rows.append(_point_record({**base, "model": "stress_2022"}, forecast, realized, horizon))
    return rows


def run_origin(task: tuple[str, str, tuple[str, ...], dict]) -> tuple[list[dict], list[dict]]:
    """Une origine d'une famille : ajuste chaque modèle sur les mois <= T, simule et note. Renvoie (scores, fits)."""
    family, origin, models, opts = task
    pool: Pool = _STATE["pools"][family]
    mixes = _mixes_for(family)
    mix_ids = list(mixes.values())
    weights = weight_matrix(pool, mix_ids)
    history = hist_log_returns(pool, weights)["nominal"]
    cut = pd.Timestamp(origin).to_period("M").to_timestamp(how="end").normalize()
    last_month = int(np.flatnonzero(np.asarray(pool.dates == cut))[0])
    horizons = [horizon for horizon in opts["horizons"] if last_month + 12 * horizon <= pool.n - 1]
    if not horizons:
        return [], []
    context = _OriginContext(
        family=family,
        origin=origin,
        pool=pool,
        labels=list(mixes),
        mix_ids=mix_ids,
        weights=weights,
        cut=cut,
        last_month=last_month,
        horizons=horizons,
        history=history,
        stress=_stress_2022(pool, weights),
        realized=_realized_outcomes(history, last_month, horizons),
        seed=int(opts["seed"]),
        n_paths=opts["n_paths"],
        pit_rng=rng_for(opts["seed"], "pit", family, origin),
    )
    rows: list[dict] = []
    fits: list[dict] = []
    for label in models:
        fitted = _fit_checked(context, label)
        fits.append(_fit_row(context, label, fitted))
        rows += _model_rows(context, label, _simulated_outcomes(context, label, fitted))
    return rows + _baseline_rows(context), fits


def build_tasks(config: WFConfig, pools: dict[str, Pool]) -> list[tuple]:
    tasks = []
    opts = {"horizons": tuple(config.horizons), "n_paths": int(config.n_paths), "seed": int(config.seed)}
    for family in config.families:
        models = tuple(config.models) + (BLOCK_MODELS if family in config.block_models_families else ())
        origins = origins_for(
            pools[family], config.first_origin[family], config.origin_step_years, max(config.horizons)
        )
        if config.max_origins:
            origins = origins[: config.max_origins]
        tasks += [(family, origin, models, opts) for origin in origins]
    return tasks


def run_walkforward(config: WFConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Exécute toutes les origines (en parallèle si ``workers`` > 1). Résultat indépendant de ``workers``."""
    _init_worker(config.input_dir)
    tasks = build_tasks(config, _STATE["pools"])
    if config.workers > 1:
        with ProcessPoolExecutor(
            max_workers=min(config.workers, os.cpu_count() or 1),
            initializer=_init_worker,
            initargs=(config.input_dir,),
        ) as executor:
            results = list(executor.map(run_origin, tasks, chunksize=1))
    else:
        results = [run_origin(task) for task in tasks]
    rows = [row for origin_rows, _ in results for row in origin_rows]
    fits = [fit_row for _, origin_fits in results for fit_row in origin_fits]
    scores = pd.DataFrame(rows).sort_values(["family", "model", "mix", "H", "origin"], kind="stable")
    return scores.reset_index(drop=True), pd.DataFrame(fits)
