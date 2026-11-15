"""Agrégation des scores walk-forward : couverture, PIT/KS sur sous-ensembles non chevauchants, CRPS et score de
Brier avec intervalles par bootstrap par blocs sur les origines.

Dépendance entre observations : avec des origines espacées de 12 mois, deux fenêtres de H ans se chevauchent sur
H − 1 ans. Deux traitements, toujours indiqués dans les sorties :

- **KS / PIT** : test sur des sous-ensembles d'origines espacées de H ans (aucun chevauchement) ; on donne la
  p-valeur du sous-ensemble de décalage 0 et la plus petite p-valeur parmi les H décalages (non corrigée) ;
- **moyennes** (couverture, CRPS, Brier) : estimation sur toutes les origines, intervalle à 90 % par bootstrap par
  blocs mobiles circulaire sur la suite des origines, blocs de ``max(2, H)`` origines ; les mélanges d'une même
  origine sont rééchantillonnés ensemble (dépendance entre mélanges conservée).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..models import rng_for
from .scoring import block_ci, ks_uniform, moving_block_bootstrap
from .walkforward import LOSS_EVENTS, MDD_EVENTS

EVENTS = [f"loss_gt_{x:02d}" for x in LOSS_EVENTS] + [f"mdd_gt_{x:02d}" for x in MDD_EVENTS]
CASH_MIX = "eq00_cs100"


def _block_length(horizon: int) -> int:
    return max(2, int(horizon))


@dataclass(frozen=True)
class _Bootstrap:
    """Bootstrap par blocs mobiles sur la suite des origines : longueur de bloc, réplications, générateur."""

    block: int
    n_boot: int
    rng: np.random.Generator

    def indices(self, n: int) -> np.ndarray:
        return moving_block_bootstrap(n, self.block, self.n_boot, self.rng)

    def mean_ci(self, values: np.ndarray) -> tuple[float, float, float]:
        return block_ci(values, self.block, self.n_boot, self.rng)


def _ks_nonoverlap(scores: pd.DataFrame, column: str, horizon: int) -> dict:
    origins = sorted(scores["origin"].unique())
    p_values, d_first, p_first, n_first = [], np.nan, np.nan, 0
    for offset in range(horizon):
        subset = set(origins[offset::horizon])
        statistic, p_value, n = ks_uniform(scores.loc[scores["origin"].isin(subset), column].to_numpy())
        if offset == 0:
            d_first, p_first, n_first = statistic, p_value, n
        if np.isfinite(p_value):
            p_values.append(p_value)
    return {
        f"ks_{column}_D": d_first,
        f"ks_{column}_p": p_first,
        f"ks_{column}_n": n_first,
        f"ks_{column}_pmin_offsets": float(min(p_values)) if p_values else np.nan,
    }


def _coverage_columns(group: pd.DataFrame, boot: _Bootstrap) -> dict:
    """Taux de couverture et de dépassement, avec leur intervalle par bootstrap par blocs d'origines."""
    record = {}
    for column in ("in80_ret", "in90_ret", "in80_mdd", "in90_mdd", "exc_mdd_q90", "below_ret_q10"):
        record[column], record[column + "_lo"], record[column + "_hi"] = boot.mean_ci(group[column].to_numpy())
    return record


def _crps_skill(model_rows: pd.DataFrame, hist_rows: pd.DataFrame, boot: _Bootstrap) -> dict:
    """CRPSS contre hist_emp, lignes alignées sur les mêmes origines : 1 - CRPS moyen / CRPS moyen de hist_emp."""
    record = {}
    for column in ("crps_ret", "crps_mdd"):
        model_crps, hist_crps = model_rows[column].to_numpy(), hist_rows[column].to_numpy()
        indices = boot.indices(len(model_crps))
        ratio = model_crps[indices].mean(axis=1) / np.maximum(hist_crps[indices].mean(axis=1), 1e-12)
        record[column + "_skill"] = float(1.0 - model_crps.mean() / max(hist_crps.mean(), 1e-12))
        record[column + "_skill_lo"] = float(1.0 - np.quantile(ratio, 0.95))
        record[column + "_skill_hi"] = float(1.0 - np.quantile(ratio, 0.05))
    return record


def _event_columns(group: pd.DataFrame) -> dict:
    """Score de Brier, probabilité moyenne prévue et fréquence observée de chaque événement."""
    record = {}
    for event in EVENTS:
        forecast, observed = group["p_" + event].to_numpy(), group["o_" + event].to_numpy()
        record["brier_" + event] = float(np.mean((forecast - observed) ** 2))
        record["pbar_" + event] = float(forecast.mean())
        record["obar_" + event] = float(observed.mean())
    return record


def per_mix_summary(scores: pd.DataFrame, n_boot: int, seed: int) -> pd.DataFrame:
    """Une ligne par (famille, modèle, mélange, H)."""
    out = []
    hist = scores[scores["model"] == "hist_emp"].set_index(["family", "mix", "H", "origin"])
    for (family, model, mix, horizon), unsorted in scores.groupby(["family", "model", "mix", "H"], sort=True):
        group = unsorted.sort_values("origin")
        boot = _Bootstrap(_block_length(horizon), n_boot, rng_for(seed, "agg", family, model, mix, int(horizon)))
        record = {"family": family, "model": model, "mix": mix, "mix_id": group["mix_id"].iloc[0], "H": int(horizon)}
        record["n_origins"] = len(group)
        record["n_nonoverlap"] = int(np.ceil(len(group) / horizon))
        record["first_origin"], record["last_origin"] = group["origin"].iloc[0], group["origin"].iloc[-1]
        record.update(_coverage_columns(group, boot))
        for column in ("crps_ret", "crps_mdd", "pin_ret_q05", "pin_mdd_q90"):
            record[column] = float(group[column].mean())
        # score de compétence CRPS contre hist_emp, sur les origines communes
        keys = pd.MultiIndex.from_tuples([(family, mix, horizon, origin) for origin in group["origin"]])
        common = hist.index.intersection(keys)
        if len(common) >= 3 and model != "hist_emp":
            model_rows = group.set_index("origin").loc[[key[3] for key in common]]
            record.update(_crps_skill(model_rows, hist.loc[common], boot))
        record.update(_event_columns(group))
        if model != "stress_2022":
            record.update(_ks_nonoverlap(group, "pit_ret", int(horizon)))
            record.update(_ks_nonoverlap(group, "pit_mdd", int(horizon)))
        out.append(record)
    return pd.DataFrame(out)


def _brier_all(frame: pd.DataFrame) -> np.ndarray:
    """Score de Brier de chaque ligne, moyen sur les événements."""
    return np.mean([(frame["p_" + e] - frame["o_" + e]) ** 2 for e in EVENTS], axis=0)


def _risky_mixes(group: pd.DataFrame) -> pd.DataFrame:
    """Mélanges sans cash, avec les colonnes ``*_nc`` et les scores de Brier de chaque ligne."""
    risky = group[group["mix"] != CASH_MIX].assign(
        in80_ret_nc=lambda frame: frame["in80_ret"], below_ret_q10_nc=lambda frame: frame["below_ret_q10"]
    )
    # Brier moyen sur événements × mélanges non triviaux
    risky = risky.copy()
    risky["brier_all"] = _brier_all(risky)
    risky["brier_mdd20"] = (risky["p_mdd_gt_20"] - risky["o_mdd_gt_20"]) ** 2
    return risky


def _origin_mean_ci(frame: pd.DataFrame, column: str, origins: list, indices: np.ndarray) -> tuple[float, float, float]:
    """Moyenne par origine (mélanges confondus), puis moyenne et intervalle à 90 % par bootstrap sur les origines."""
    # matrice origines × mélanges -> moyenne par origine, puis bootstrap sur les origines
    per_origin = frame.groupby("origin")[column].mean().reindex(origins).to_numpy()
    finite = np.isfinite(per_origin)
    mean = float(np.nanmean(per_origin)) if finite.any() else np.nan
    boots = np.nanmean(per_origin[indices], axis=1)
    return mean, float(np.nanquantile(boots, 0.05)), float(np.nanquantile(boots, 0.95))


def _pooled_rates(group: pd.DataFrame, risky: pd.DataFrame, origins: list, indices: np.ndarray) -> dict:
    """Couvertures, dépassements, Brier et CRPS moyens, avec leur intervalle (même tirage des origines)."""
    columns = (
        ("in80_ret", group),
        ("in90_ret", group),
        ("below_ret_q10", group),
        ("in80_mdd", risky),
        ("in90_mdd", risky),
        ("exc_mdd_q90", risky),
        ("in80_ret_nc", risky),
        ("below_ret_q10_nc", risky),
        ("brier_all", risky),
        ("brier_mdd20", risky),
        ("crps_ret", group),
        ("crps_mdd", risky),
    )
    record = {}
    for column, frame in columns:
        record[column], record[column + "_lo"], record[column + "_hi"] = _origin_mean_ci(
            frame, column, origins, indices
        )
    return record


def _pooled_crps_skill(group: pd.DataFrame, hist_group: pd.DataFrame, origins: list, boot: _Bootstrap) -> dict:
    """CRPSS contre hist_emp sur les origines communes (au moins 3)."""
    record = {}
    pairs = (
        ("crps_ret", group, hist_group),
        ("crps_mdd", group[group["mix"] != CASH_MIX], hist_group[hist_group["mix"] != CASH_MIX]),
    )
    for column, model_rows, hist_rows in pairs:
        model_by_origin = model_rows.groupby("origin")[column].mean().reindex(origins).to_numpy()
        hist_by_origin = hist_rows.groupby("origin")[column].mean().reindex(origins).to_numpy()
        common = np.isfinite(model_by_origin) & np.isfinite(hist_by_origin)
        if common.sum() >= 3:
            model_crps, hist_crps = model_by_origin[common], hist_by_origin[common]
            indices = boot.indices(len(model_crps))
            ratio = model_crps[indices].mean(axis=1) / hist_crps[indices].mean(axis=1)
            record[column + "_skill"] = float(1 - model_crps.mean() / hist_crps.mean())
            record[column + "_skill_lo"] = float(1 - np.quantile(ratio, 0.95))
            record[column + "_skill_hi"] = float(1 - np.quantile(ratio, 0.05))
            record[column + "_skill_n"] = int(common.sum())
    return record


def _pooled_brier_skill(risky: pd.DataFrame, hist_group: pd.DataFrame, origins: list) -> dict:
    """BSS contre hist_emp, mélanges sans cash, sur les origines communes (au moins 3)."""
    hist_risky = hist_group[hist_group["mix"] != CASH_MIX].copy()
    if not len(hist_risky):
        return {}
    hist_risky["brier_all"] = _brier_all(hist_risky)
    model_by_origin = risky.groupby("origin")["brier_all"].mean().reindex(origins).to_numpy()
    hist_by_origin = hist_risky.groupby("origin")["brier_all"].mean().reindex(origins).to_numpy()
    common = np.isfinite(model_by_origin) & np.isfinite(hist_by_origin)
    if common.sum() < 3:
        return {}
    return {"brier_skill": float(1 - model_by_origin[common].mean() / hist_by_origin[common].mean())}


def pooled_summary(scores: pd.DataFrame, n_boot: int, seed: int) -> pd.DataFrame:
    """Une ligne par (famille, modèle, H), moyennes sur les mélanges non triviaux.

    - rendement : les 6 mélanges (le cash teste l'hypothèse de niveau des taux) ;
    - perte maximale et événements : sans le cash (perte maximale nominale toujours nulle, triviale).
    Bootstrap : blocs d'origines, tous les mélanges d'une origine ensemble.
    """
    out = []
    hist = scores[scores["model"] == "hist_emp"]
    for (family, model, horizon), group in scores.groupby(["family", "model", "H"], sort=True):
        boot = _Bootstrap(_block_length(horizon), n_boot, rng_for(seed, "pooled", family, model, int(horizon)))
        origins = sorted(group["origin"].unique())
        indices = boot.indices(len(origins))
        record = {"family": family, "model": model, "H": int(horizon), "n_origins": len(origins)}
        record["n_nonoverlap"] = int(np.ceil(len(origins) / horizon))
        risky = _risky_mixes(group)
        record.update(_pooled_rates(group, risky, origins, indices))
        # compétences contre hist_emp (origines communes, même bootstrap)
        if model != "hist_emp":
            hist_group = hist[(hist["family"] == family) & (hist["H"] == horizon)]
            record.update(_pooled_crps_skill(group, hist_group, origins, boot))
            record.update(_pooled_brier_skill(risky, hist_group, origins))
        out.append(record)
    return pd.DataFrame(out)


def _reliability_bins(forecast: np.ndarray, observed: np.ndarray, bins) -> list[dict]:
    """Effectif, probabilité moyenne prévue et fréquence observée de chaque classe de probabilité non vide."""
    classes = np.digitize(forecast, bins) - 1
    rows = []
    for k in range(len(bins) - 1):
        in_bin = classes == k
        if in_bin.sum() == 0:
            continue
        rows.append(
            {
                "bin": f"[{bins[k]:.2f},{min(bins[k + 1], 1):.2f})",
                "n": int(in_bin.sum()),
                "mean_forecast": float(forecast[in_bin].mean()),
                "observed_freq": float(observed[in_bin].mean()),
            }
        )
    return rows


def reliability(scores: pd.DataFrame, bins=(0.0, 0.02, 0.10, 0.25, 0.50, 0.75, 1.0001)) -> pd.DataFrame:
    """Diagramme de fiabilité (tableau) par (famille, modèle, type d'événement), mélanges non triviaux, tous H."""
    rows = []
    risky = scores[(scores["mix"] != CASH_MIX) & (scores["model"] != "stress_2022")]
    for (family, model), group in risky.groupby(["family", "model"]):
        for kind, events in (
            ("loss", [e for e in EVENTS if e.startswith("loss")]),
            ("mdd", [e for e in EVENTS if e.startswith("mdd")]),
        ):
            forecast = np.concatenate([group["p_" + e].to_numpy() for e in events])
            observed = np.concatenate([group["o_" + e].to_numpy() for e in events])
            for cell in _reliability_bins(forecast, observed, bins):
                rows.append({"family": family, "model": model, "events": kind, **cell})
    return pd.DataFrame(rows)


def pit_histogram(scores: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    """Histogramme PIT (descriptif, toutes origines, observations dépendantes) par (famille, modèle, H, variable)."""
    rows = []
    distributions = scores[scores["model"] != "stress_2022"]
    for (family, model, horizon), group in distributions.groupby(["family", "model", "H"]):
        for variable, frame in (("ret", group), ("mdd", group[group["mix"] != CASH_MIX])):
            pit_values = frame["pit_" + variable].to_numpy()
            counts, _ = np.histogram(pit_values, bins=np.linspace(0, 1, n_bins + 1))
            rows.append(
                {"family": family, "model": model, "H": int(horizon), "var": variable, "n": int(len(pit_values))}
                | {f"b{k}": int(count) for k, count in enumerate(counts)}
            )
    return pd.DataFrame(rows)


def ks_summary(per_mix: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """Nombre de mélanges (hors cash) dont le PIT est rejeté par KS au seuil ``alpha`` (sous-ensemble non chevauchant
    de décalage 0), par famille, modèle et H. Puissance faible quand n est petit (H = 10 : 3 à 7 fenêtres)."""
    risky = per_mix[(per_mix["mix"] != CASH_MIX) & (per_mix["model"] != "stress_2022")]
    rows = []
    for (family, model, horizon), group in risky.groupby(["family", "model", "H"]):
        rows.append(
            {
                "family": family,
                "model": model,
                "H": int(horizon),
                "n_mixes": len(group),
                "n_indep": int(group["ks_pit_ret_n"].median()),
                "rejects_ret": int((group["ks_pit_ret_p"] < alpha).sum()),
                "rejects_mdd": int((group["ks_pit_mdd_p"] < alpha).sum()),
            }
        )
    return pd.DataFrame(rows)
