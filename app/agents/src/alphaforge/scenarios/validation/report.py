"""Tableaux Markdown générés à partir des sorties (``tables.md``) : le rapport VALIDATION.md n'en recopie que des
extraits, chaque chiffre vient donc d'un fichier produit par ce module."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

MODEL_ORDER = [
    "sbb",
    "sbb_ca",
    "iid",
    "iid_ca",
    "hmm_rs",
    "hmm_rs_ca",
    "hmm_rs_fl",
    "sbb_L06",
    "sbb_L12",
    "sbb_L48",
    "sbb_L96",
    "hist_emp",
    "stress_2022",
]
# Modèles des tableaux agrégés : sans les variantes de borne de bloc (sbb_Lxx), qui ont leurs propres sections.
_CORE_MODELS = ["sbb", "sbb_ca", "iid", "iid_ca", "hmm_rs", "hmm_rs_ca", "hmm_rs_fl", "hist_emp", "stress_2022"]


@dataclass(frozen=True)
class ValidationResults:
    """Sorties de la validation reprises dans ``tables.md`` (agrégats, contrôles ciblés, ajustements)."""

    pooled: pd.DataFrame
    per_mix: pd.DataFrame
    reliability: pd.DataFrame
    rising_rates: pd.DataFrame
    recent: pd.DataFrame
    hmm: dict
    historical_mdd: pd.DataFrame
    monotonicity: pd.DataFrame
    duplicates: dict
    look_ahead: list[dict]
    fits: pd.DataFrame
    ks_summary: pd.DataFrame | None = None


def _pct(x, digits=0):
    return "" if x is None or not np.isfinite(x) else f"{100 * x:.{digits}f}"


def _ci(mean, low, high, digits=0):
    if mean is None or not np.isfinite(mean):
        return "n/a"
    return f"{_pct(mean, digits)} [{_pct(low, digits)}; {_pct(high, digits)}]"


def _num(x, digits=3):
    return "" if x is None or not np.isfinite(x) else f"{x:.{digits}f}"


def md(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_(vide)_\n"
    columns = list(frame.columns)
    lines = ["| " + " | ".join(map(str, columns)) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in columns) + " |")
    return "\n".join(lines) + "\n"


def _order(frame: pd.DataFrame) -> pd.DataFrame:
    rank = {model: i for i, model in enumerate(MODEL_ORDER)}
    return frame.assign(_r=frame["model"].map(lambda model: rank.get(model, 99))).sort_values(["_r"]).drop(columns="_r")


def pooled_table(pooled: pd.DataFrame, family: str, horizon: int, models=None) -> str:
    selected = pooled[(pooled["family"] == family) & (pooled["H"] == horizon)]
    if models:
        selected = selected[selected["model"].isin(models)]
    selected = _order(selected)
    rows = []
    for _, row in selected.iterrows():
        rows.append(
            {
                "modèle": row["model"],
                "n orig. (indép.)": f"{row['n_origins']} ({row['n_nonoverlap']})",
                "couv. 80 % rend.": _ci(row["in80_ret"], row["in80_ret_lo"], row["in80_ret_hi"]),
                "couv. 90 % rend.": _ci(row["in90_ret"], row["in90_ret_lo"], row["in90_ret_hi"]),
                "rend. < p10": _ci(row["below_ret_q10"], row["below_ret_q10_lo"], row["below_ret_q10_hi"]),
                "couv. 80 % MDD": _ci(row["in80_mdd"], row["in80_mdd_lo"], row["in80_mdd_hi"]),
                "MDD > p90": _ci(row["exc_mdd_q90"], row["exc_mdd_q90_lo"], row["exc_mdd_q90_hi"]),
                "CRPSS rend.": _ci(
                    row.get("crps_ret_skill", np.nan), row.get("crps_ret_skill_lo"), row.get("crps_ret_skill_hi")
                ),
                "CRPSS MDD": _ci(
                    row.get("crps_mdd_skill", np.nan), row.get("crps_mdd_skill_lo"), row.get("crps_mdd_skill_hi")
                ),
                "Brier (6 év.)": _num(row["brier_all"], 4),
                "BSS": _pct(row.get("brier_skill", np.nan)),
            }
        )
    return md(pd.DataFrame(rows))


def per_mix_table(per_mix: pd.DataFrame, family: str, horizon: int, models) -> str:
    selected = per_mix[(per_mix["family"] == family) & (per_mix["H"] == horizon) & per_mix["model"].isin(models)]
    rows = []
    for _, row in _order(selected).sort_values(["mix"], kind="stable").iterrows():
        rows.append(
            {
                "mélange (actions/RF)": row["mix"],
                "modèle": row["model"],
                "n": row["n_origins"],
                "couv. 80 % rend.": _ci(row["in80_ret"], row["in80_ret_lo"], row["in80_ret_hi"]),
                "rend. < p10": _pct(row["below_ret_q10"]),
                "MDD > p90": _pct(row["exc_mdd_q90"]),
                "P̄(MDD>20) prévu": _pct(row["pbar_mdd_gt_20"], 1),
                "fréq. obs. MDD>20": _pct(row["obar_mdd_gt_20"], 1),
                "Brier MDD>20": _num(row["brier_mdd_gt_20"], 3),
                "KS rend. p (déc. 0 / min)": (
                    f"{_num(row.get('ks_pit_ret_p', np.nan), 2)} / "
                    f"{_num(row.get('ks_pit_ret_pmin_offsets', np.nan), 2)} (n={row.get('ks_pit_ret_n', '')})"
                ),
            }
        )
    return md(pd.DataFrame(rows))


def _format_columns(frame: pd.DataFrame, columns: Iterable[str], formatter: Callable) -> None:
    for column in columns:
        frame[column] = frame[column].map(formatter)


def _ci_cells(means: pd.Series, lows: pd.Series, highs: pd.Series) -> list[str]:
    return [_ci(mean, low, high) for mean, low, high in zip(means, lows, highs, strict=True)]


def _pooled_sections(pooled: pd.DataFrame) -> list[str]:
    parts = []
    for family in ("CAD77", "CAD71", "USD1926", "USD1953"):
        for horizon in (1, 3, 5, 10):
            if ((pooled["family"] == family) & (pooled["H"] == horizon)).any():
                parts.append(f"\n## Agrégé {family}, H = {horizon} ans\n")
                parts.append(pooled_table(pooled, family, horizon, _CORE_MODELS))
    return parts


def _block_bound_sections(pooled: pd.DataFrame) -> list[str]:
    parts = []
    for family in ("CAD77", "USD1926"):
        for horizon in (1, 3, 5, 10):
            parts.append(f"\n## Borne de bloc {family}, H = {horizon}\n")
            parts.append(
                pooled_table(pooled, family, horizon, ["sbb_L06", "sbb_L12", "sbb", "sbb_L48", "sbb_L96", "iid"])
            )
    return parts


def _per_mix_sections(per_mix: pd.DataFrame) -> list[str]:
    parts = []
    for family in ("CAD77", "USD1926"):
        for horizon in (5, 10):
            parts.append(f"\n## Par mélange {family}, H = {horizon}\n")
            parts.append(
                per_mix_table(per_mix, family, horizon, ["sbb", "sbb_ca", "hmm_rs", "hist_emp", "stress_2022"])
            )
    return parts


def _risky_mixes_section(pooled: pd.DataFrame) -> list[str]:
    heading = "\n## Mélanges risqués seulement (sans cash) : rendement sous p10 et MDD au-dessus de p90\n"
    sub = pooled[pooled["model"].isin(_CORE_MODELS)].copy()
    sub["rend<p10 (sans cash)"] = _ci_cells(
        sub["below_ret_q10_nc"], sub["below_ret_q10_nc_lo"], sub["below_ret_q10_nc_hi"]
    )
    sub["couv80 rend (sans cash)"] = _ci_cells(sub["in80_ret_nc"], sub["in80_ret_nc_lo"], sub["in80_ret_nc_hi"])
    sub["MDD>p90"] = _ci_cells(sub["exc_mdd_q90"], sub["exc_mdd_q90_lo"], sub["exc_mdd_q90_hi"])
    sub["Brier [IC]"] = [
        f"{mean:.4f} [{low:.4f}; {high:.4f}]"
        for mean, low, high in zip(sub["brier_all"], sub["brier_all_lo"], sub["brier_all_hi"], strict=True)
    ]
    columns = ["family", "H", "model", "couv80 rend (sans cash)", "rend<p10 (sans cash)", "MDD>p90", "Brier [IC]"]
    return [heading, md(_order(sub)[columns].sort_values(["family", "H"], kind="stable"))]


def _single_mix_table(per_mix: pd.DataFrame, mix: str) -> str:
    selected = per_mix[(per_mix["mix"] == mix) & per_mix["model"].isin(["sbb", "sbb_ca", "hmm_rs", "iid", "hist_emp"])]
    selected = selected.assign(
        below=selected["below_ret_q10"].map(_pct),
        exc=selected["exc_mdd_q90"].map(_pct),
        p20=selected["pbar_mdd_gt_20"].map(lambda x: _pct(x, 1)),
        o20=selected["obar_mdd_gt_20"].map(lambda x: _pct(x, 1)),
    )
    columns = ["family", "H", "model", "n_origins", "below", "exc", "p20", "o20"]
    return md(_order(selected)[columns].sort_values(["family", "H"], kind="stable"))


def _single_mix_sections(per_mix: pd.DataFrame) -> list[str]:
    parts = []
    for mix in ("eq00_fi100", "eq100_fi00"):
        parts.append(f"\n## Mélange {mix} : rendement sous p10, MDD au-dessus de p90, P(MDD>20) prévu / observé\n")
        parts.append(_single_mix_table(per_mix, mix))
    return parts


def _ks_section(ks_summary: pd.DataFrame | None) -> list[str]:
    if ks_summary is None or ks_summary.empty:
        return []
    heading = "\n## KS du PIT (sous-ensemble non chevauchant), mélanges rejetés à 5 % sur 5 (hors cash)\n"
    return [heading, md(ks_summary[ks_summary["model"].isin(_CORE_MODELS)])]


def _reliability_table(reliability: pd.DataFrame, events: str) -> str:
    table = reliability[
        (reliability["events"] == events) & reliability["model"].isin(["sbb", "sbb_ca", "hmm_rs", "hist_emp"])
    ].copy()
    _format_columns(table, ("mean_forecast", "observed_freq"), lambda x: _pct(x, 1))
    return md(table)


def _reliability_sections(reliability: pd.DataFrame) -> list[str]:
    return [
        "\n## Fiabilité (événements MDD > 10/20/30 %, tous H, sans cash)\n",
        _reliability_table(reliability, "mdd"),
        "\n## Fiabilité (événements perte cumulée > 0/10/20 %, tous H, sans cash)\n",
        _reliability_table(reliability, "loss"),
    ]


def _rising_rates_section(rising_rates: pd.DataFrame) -> list[str]:
    heading = "\n## (i) Hausse des taux (fenêtres finissant <= 1981)\n"
    table = rising_rates[rising_rates["model"].isin(["sbb", "sbb_ca", "hmm_rs", "hmm_rs_ca", "iid", "hist_emp"])].copy()
    _format_columns(table, ("mean_pit_ret", "mean_pit_mdd"), lambda x: _num(x, 2))
    percent_columns = (
        "cov80_ret",
        "below_q10_ret",
        "exc_q90_mdd",
        "mean_y_ret",
        "mean_q10_ret",
        "mean_y_mdd",
        "mean_q90_mdd",
    )
    _format_columns(table, percent_columns, lambda x: _pct(x, 1))
    return [heading, md(table)]


def _recent_section(recent: pd.DataFrame) -> list[str]:
    models = ["sbb", "sbb_ca", "hmm_rs", "hmm_rs_ca", "hist_emp", "stress_2022"]
    table = recent[recent["model"].isin(models)].copy()
    percent_columns = (
        "y_ret",
        "ret_q05",
        "ret_q10",
        "y_mdd",
        "mdd_q90",
        "mdd_q95",
        "p_mdd_gt_10",
        "p_mdd_gt_20",
        "p_loss_gt_10",
    )
    _format_columns(table, percent_columns, lambda x: _pct(x, 1))
    _format_columns(table, ("pit_ret", "pit_mdd"), lambda x: _num(x, 3))
    return ["\n## (i) 2021-2023\n", md(table)]


def _block_length_section(fits: pd.DataFrame) -> list[str]:
    stats = fits[fits["model"] == "sbb"].groupby("family")["block_raw"].describe()[["count", "min", "50%", "max"]]
    return ["\n## (ii) Longueur de bloc brute (Politis-White) aux origines\n", md(stats.reset_index().round(1))]


def _hmm_section(hmm: dict) -> list[str]:
    return [
        "\n## (iii) HMM USD1926 / USD1953 (toute la fenêtre)\n",
        "```json\n" + json.dumps(hmm, indent=1) + "\n```\n",
    ]


def _historical_section(historical_mdd: pd.DataFrame) -> list[str]:
    table = historical_mdd.copy()
    _format_columns(table, ("freq_mdd_gt_20", "max_mdd"), lambda x: _pct(x, 1))
    return ["\n## (v) Fenêtres historiques glissantes, perte max. > 20 %\n", md(table)]


def _monotonicity_section(monotonicity: pd.DataFrame) -> list[str]:
    if monotonicity.empty:
        return []
    heading = "\n## (v) Monotonie de P(MDD > x) le long de la ligne actions/obligations (run de référence)\n"
    summary = monotonicity.groupby(["model_id", "family"]).agg(
        n=("monotone_increasing", "size"),
        non_monotone=("monotone_increasing", lambda x: int((~x).sum())),
        argmin_eq_median=("argmin_equity_share", "median"),
    )
    example = monotonicity[
        (monotonicity["metric"] == "p_mdd_gt_20") & (monotonicity["H"] == 5) & (monotonicity["family"] == "CAD77")
    ]
    return [
        heading,
        md(summary.reset_index()),
        "\nExemple CAD77, H = 5, P(MDD > 20 %) :\n\n"
        + md(example[["model_id", "equity_shares", "values", "argmin_equity_share"]]),
    ]


def _duplicates_section(duplicates: dict) -> list[str]:
    if not duplicates:
        return []
    return [f"\n## Doublons dans sensitivity_block_length.csv du run de référence\n\n{duplicates}\n"]


def _look_ahead_section(look_ahead: list[dict]) -> list[str]:
    return ["\n## Look-ahead (vraies données, mois postérieurs corrompus)\n", md(pd.DataFrame(look_ahead))]


def write_tables(out: Path, results: ValidationResults) -> None:
    """Écrit ``tables.md`` : les sections suivent l'ordre du rapport VALIDATION.md."""
    parts = ["# Tableaux générés (volet C)\n", "Valeurs en %, IC 90 % par bootstrap par blocs sur les origines.\n"]
    parts += _pooled_sections(results.pooled)
    parts += _block_bound_sections(results.pooled)
    parts += _per_mix_sections(results.per_mix)
    parts += _risky_mixes_section(results.pooled)
    parts += _single_mix_sections(results.per_mix)
    parts += _ks_section(results.ks_summary)
    parts += _reliability_sections(results.reliability)
    parts += _rising_rates_section(results.rising_rates)
    parts += _recent_section(results.recent)
    parts += _block_length_section(results.fits)
    parts += _hmm_section(results.hmm)
    parts += _historical_section(results.historical_mdd)
    parts += _monotonicity_section(results.monotonicity)
    parts += _duplicates_section(results.duplicates)
    parts += _look_ahead_section(results.look_ahead)
    (out / "tables.md").write_text("\n".join(parts), encoding="utf-8")
