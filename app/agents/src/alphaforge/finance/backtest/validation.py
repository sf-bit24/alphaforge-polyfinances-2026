"""Robust selection and walk-forward (out-of-sample) validation over windows."""

from __future__ import annotations

import numpy as np
import pandas as pd


def robust_table(rows: pd.DataFrame, quantile: float = 0.10, max_breach_rate: float | None = None) -> pd.DataFrame:
    """Per strategy: distribution of the objective score across windows. Ranked by the
    `quantile` (default 10th percentile = 'bad-case' window), not by the mean."""
    by_strategy = rows[~rows["hindsight"]].groupby("strategy")
    table = pd.DataFrame(
        {
            "n_windows": by_strategy.size(),
            f"score_p{int(quantile * 100)}": by_strategy["score"].quantile(quantile),
            "score_median": by_strategy["score"].median(),
            "score_mean": by_strategy["score"].mean(),
            "score_worst": by_strategy["score"].min(),
            "ann_real_return_median": by_strategy["ann_real_return"].median(),
            "max_drawdown_worst": by_strategy["max_drawdown"].max(),
            "breach_rate": by_strategy["n_breaches"].apply(lambda breaches: float(np.mean(breaches > 0))),
            "shortfall_prob": by_strategy["missed_target"].apply(
                lambda missed: float(np.mean(missed.astype(float))) if missed.notna().all() else np.nan
            ),
            "fallback_share": by_strategy["fallback_months"].sum() / by_strategy["n_months"].sum(),
        }
    )
    table["eligible"] = True if max_breach_rate is None else table["breach_rate"] <= max_breach_rate
    key = f"score_p{int(quantile * 100)}"
    table = table.sort_values(["eligible", key, "score_median"], ascending=[False, False, False])
    table["rank"] = np.arange(1, len(table) + 1)
    return table


def select_robust(rows: pd.DataFrame, quantile: float = 0.10, max_breach_rate: float | None = None) -> str | None:
    if rows.empty:
        return None
    return robust_table(rows, quantile, max_breach_rate).index[0]


def walk_forward(
    rows: pd.DataFrame, quantile: float = 0.10, max_breach_rate: float | None = None, min_past_windows: int = 3
) -> pd.DataFrame:
    """For each window k, choose the strategy using ONLY windows that ended before k starts,
    then record how the chosen strategy did on window k (out-of-sample)."""
    ex_ante = rows[~rows["hindsight"]].copy()
    ex_ante["start"] = pd.to_datetime(ex_ante["start"])
    ex_ante["end"] = pd.to_datetime(ex_ante["end"])
    window_dates = ex_ante[["window", "start", "end"]].drop_duplicates().sort_values("start")
    hindsight = rows["hindsight"]
    oracle_scores = rows[hindsight].set_index("window")["score"] if hindsight.any() else pd.Series(dtype=float)
    out_of_sample = []
    for _, window in window_dates.iterrows():
        past = ex_ante[ex_ante["end"] < window["start"]]
        n_past = past["window"].nunique()
        if n_past < min_past_windows:
            continue
        chosen = select_robust(past, quantile, max_breach_rate)
        current = ex_ante[ex_ante["window"] == window["window"]].set_index("strategy")
        best_ex_post = current["score"].idxmax()
        out_of_sample.append(
            {
                "window": window["window"],
                "n_past_windows": n_past,
                "chosen": chosen,
                "chosen_score": float(current.at[chosen, "score"]),
                "chosen_missed_target": current.at[chosen, "missed_target"],
                "chosen_rank_in_window": int(current["score"].rank(ascending=False).at[chosen]),
                "best_ex_post": best_ex_post,
                "best_ex_post_score": float(current["score"].max()),
                "oracle_score": float(oracle_scores.get(window["window"], np.nan)),
            }
        )
    return pd.DataFrame(out_of_sample)
