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
from ..models import fit, rng_for
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

        def eq(e):
            return {"CA_EQ": e / 200.0, "US_MKT": e / 200.0, "BONDS": (100 - e) / 100.0}
    else:

        def eq(e):
            return {"US_MKT": e / 100.0, "BONDS": (100 - e) / 100.0}

    out = {f"eq{e:02d}_fi{100 - e:02d}": mix_id(eq(e)) for e in (0, 30, 40, 70)}
    out["eq100_fi00"] = mix_id(eq(100))
    out["eq00_cs100"] = mix_id({"CASH": 1.0})
    return dict(sorted(out.items(), key=lambda kv: (kv[0] == "eq00_cs100", kv[0])))


# Familles : celles du produit + USD1953 (USD1926 sans les 327 mois d'obligations du taux long de Shiller, lissé),
# pour le contrôle (iii) du HMM.
FAMILY_FIRST_ORIGIN = {"CAD77": "1990-12", "CAD71": "1975-12", "USD1926": "1950-12", "USD1953": "1963-12"}


def make_pools(inputs) -> dict[str, Pool]:
    pools = {f: build_pool(inputs, f) for f in ("CAD77", "CAD71", "USD1926")}
    usd = pools["USD1926"]
    keep = np.flatnonzero(np.asarray(usd.dates >= pd.Timestamp("1953-04-30")))
    p53 = usd._subset(keep)
    p53.name = "USD1953"
    pools["USD1953"] = p53
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
    y0 = int(first[:4])
    out = []
    for y in range(y0, last.year + 1, step_years):
        t = pd.Timestamp(f"{y}-12-31")
        if t + pd.DateOffset(months=12) <= last + pd.offsets.MonthEnd(0):
            out.append(f"{y}-12")
    return out


_STATE: dict[str, Any] = {}


def _init_worker(input_dir: str) -> None:
    _STATE["pools"] = make_pools(load_inputs(input_dir))


def _stress_2022(pool: Pool, W: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lr = hist_log_returns(pool, W)["nominal"]
    m = np.asarray(pool.dates.year == 2022)
    cum = np.vstack([np.zeros((1, lr.shape[1])), np.cumsum(lr[m], axis=0)])
    ret = np.expm1(cum[-1])
    mdd = -np.expm1(-(np.maximum.accumulate(cum, axis=0) - cum).max(axis=0))
    return ret, mdd


def _record(base: dict, ret_s, mdd_s, logw_s, y_ret, y_mdd, y_logw, u: np.ndarray) -> dict:
    """Scores d'une distribution prédictive (échantillons) contre un résultat réalisé."""
    rq = np.quantile(ret_s, RET_Q)
    mq = np.quantile(mdd_s, MDD_Q)
    rec = {
        **base,
        "n_samples": int(len(ret_s)),
        "y_ret": y_ret,
        "y_mdd": y_mdd,
        "pit_ret": pit(ret_s, y_ret, float(u[0])),
        "pit_mdd": pit(mdd_s, y_mdd, float(u[1])),
        "crps_ret": crps_samples(ret_s, y_ret),
        "crps_mdd": crps_samples(mdd_s, y_mdd),
        "pin_ret_q05": pinball(rq[0], y_ret, 0.05),
        "pin_ret_q10": pinball(rq[1], y_ret, 0.10),
        "pin_mdd_q90": pinball(mq[3], y_mdd, 0.90),
        "in80_ret": float(rq[1] <= y_ret <= rq[3]),
        "in90_ret": float(rq[0] <= y_ret <= rq[4]),
        "in80_mdd": float(mq[1] <= y_mdd <= mq[3]),
        "in90_mdd": float(mq[0] <= y_mdd <= mq[4]),
        "exc_mdd_q90": float(y_mdd > mq[3]),
        "below_ret_q10": float(y_ret < rq[1]),
    }
    for q, v in zip(RET_Q, rq, strict=True):
        rec[f"ret_q{int(q * 100):02d}"] = float(v)
    for q, v in zip(MDD_Q, mq, strict=True):
        rec[f"mdd_q{int(q * 100):02d}"] = float(v)
    for x in LOSS_EVENTS:
        thr = np.log1p(-x / 100.0)
        rec[f"p_loss_gt_{x:02d}"] = float(np.mean(logw_s < thr))
        rec[f"o_loss_gt_{x:02d}"] = float(y_logw < thr)
    for x in MDD_EVENTS:
        rec[f"p_mdd_gt_{x:02d}"] = float(np.mean(mdd_s > x / 100.0))
        rec[f"o_mdd_gt_{x:02d}"] = float(y_mdd > x / 100.0)
    return rec


def _point_record(base: dict, x_ret: float, x_mdd: float, y_ret, y_mdd, y_logw, H: int) -> dict:
    """Prévision ponctuelle (« 2022 seulement ») : CRPS = erreur absolue, probabilités d'événement 0 ou 1."""
    rec = {
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
    for q in RET_Q:
        rec[f"ret_q{int(q * 100):02d}"] = x_ret
    for q in MDD_Q:
        rec[f"mdd_q{int(q * 100):02d}"] = x_mdd
    x_logw = H * np.log1p(x_ret)  # 2022 répété chaque année : richesse (1 + r_2022)^H
    for x in LOSS_EVENTS:
        thr = np.log1p(-x / 100.0)
        rec[f"p_loss_gt_{x:02d}"] = float(x_logw < thr)
        rec[f"o_loss_gt_{x:02d}"] = float(y_logw < thr)
    for x in MDD_EVENTS:
        rec[f"p_mdd_gt_{x:02d}"] = float(x_mdd > x / 100.0)
        rec[f"o_mdd_gt_{x:02d}"] = float(y_mdd > x / 100.0)
    return rec


def run_origin(task: tuple[str, str, tuple[str, ...], dict]) -> tuple[list[dict], list[dict]]:
    """Une origine d'une famille : ajuste chaque modèle sur les mois <= T, simule et note. Renvoie (scores, fits)."""
    family, origin, models, opts = task
    pool: Pool = _STATE["pools"][family]
    mixes = _mixes_for(family)
    labels, mids = list(mixes), list(mixes.values())
    W = weight_matrix(pool, mids)
    lr_full = hist_log_returns(pool, W)["nominal"]
    cut = pd.Timestamp(origin).to_period("M").to_timestamp(how="end").normalize()
    t0 = int(np.flatnonzero(np.asarray(pool.dates == cut))[0])
    horizons = [H for H in opts["horizons"] if t0 + 12 * H <= pool.n - 1]
    if not horizons:
        return [], []
    s22_ret, s22_mdd = _stress_2022(pool, W)
    realized = {H: [realized_outcome(lr_full[t0 + 1 : t0 + 1 + 12 * H, m]) for m in range(len(mids))] for H in horizons}
    u_rng = rng_for(opts["seed"], "pit", family, origin)
    rows: list[dict] = []
    fits: list[dict] = []
    seed = int(opts["seed"])
    for label in models:
        model_id, params = MODEL_SPECS[label]
        fitted = fit(pool, model_id, fitted_through=origin, seed=seed, params=params)
        # garde-fous anti look-ahead (re-vérifiés à chaque ajustement)
        assert fitted.fitted_through == origin, (fitted.fitted_through, origin)
        assert fitted.pool.n == t0 + 1 and fitted.pool.dates[-1] == cut
        idx = fitted.simulate_indices(opts["n_paths"], 12 * max(horizons), rng_for(seed, "wf", family, label, origin))
        assert int(idx.max()) <= t0
        lr_fit = hist_log_returns(fitted.pool, W)["nominal"]
        sims = path_outcomes(lr_fit, idx, horizons)
        info = fitted.info
        fits.append(
            {
                "family": family,
                "model": label,
                "origin": origin,
                "n_hist": fitted.pool.n,
                "mean_block": info.get("mean_block"),
                "block_raw": info.get("block_raw"),
                "k": info.get("k"),
                "cash_scale": info.get("cash_scale"),
            }
        )
        for H in horizons:
            for m, lab in enumerate(labels):
                y_ret, y_mdd, y_logw = realized[H][m]
                base = {"family": family, "model": label, "origin": origin, "mix": lab, "mix_id": mids[m], "H": H}
                rows.append(
                    _record(
                        base,
                        sims[H]["ret"][:, m],
                        sims[H]["mdd"][:, m],
                        sims[H]["logw"][:, m],
                        y_ret,
                        y_mdd,
                        y_logw,
                        u_rng.random(2),
                    )
                )
    # repères
    for H in horizons:
        for m, lab in enumerate(labels):
            y_ret, y_mdd, y_logw = realized[H][m]
            emp = rolling_outcomes(lr_full[: t0 + 1, m], H)
            base = {"family": family, "origin": origin, "mix": lab, "mix_id": mids[m], "H": H}
            if len(emp["ret"]) >= 12:
                rows.append(
                    _record(
                        {**base, "model": "hist_emp"},
                        emp["ret"],
                        emp["mdd"],
                        emp["logw"],
                        y_ret,
                        y_mdd,
                        y_logw,
                        u_rng.random(2),
                    )
                )
            rows.append(
                _point_record(
                    {**base, "model": "stress_2022"}, float(s22_ret[m]), float(s22_mdd[m]), y_ret, y_mdd, y_logw, H
                )
            )
    return rows, fits


def build_tasks(cfg: WFConfig, pools: dict[str, Pool]) -> list[tuple]:
    tasks = []
    opts = {"horizons": tuple(cfg.horizons), "n_paths": int(cfg.n_paths), "seed": int(cfg.seed)}
    for family in cfg.families:
        models = tuple(cfg.models) + (BLOCK_MODELS if family in cfg.block_models_families else ())
        origins = origins_for(pools[family], cfg.first_origin[family], cfg.origin_step_years, max(cfg.horizons))
        if cfg.max_origins:
            origins = origins[: cfg.max_origins]
        tasks += [(family, o, models, opts) for o in origins]
    return tasks


def run_walkforward(cfg: WFConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Exécute toutes les origines (en parallèle si ``workers`` > 1). Résultat indépendant de ``workers``."""
    _init_worker(cfg.input_dir)
    tasks = build_tasks(cfg, _STATE["pools"])
    if cfg.workers > 1:
        with ProcessPoolExecutor(
            max_workers=min(cfg.workers, os.cpu_count() or 1), initializer=_init_worker, initargs=(cfg.input_dir,)
        ) as ex:
            results = list(ex.map(run_origin, tasks, chunksize=1))
    else:
        results = [run_origin(t) for t in tasks]
    rows = [r for res in results for r in res[0]]
    fits = [f for res in results for f in res[1]]
    scores = pd.DataFrame(rows).sort_values(["family", "model", "mix", "H", "origin"], kind="stable")
    return scores.reset_index(drop=True), pd.DataFrame(fits)
