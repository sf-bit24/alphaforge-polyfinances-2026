"""Robust selection and walk-forward (out-of-sample) validation over windows."""
from __future__ import annotations

import numpy as np
import pandas as pd


def robust_table(rows: pd.DataFrame, quantile: float = 0.10, max_breach_rate: float | None = None) -> pd.DataFrame:
    """Per strategy: distribution of the objective score across windows. Ranked by the
    `quantile` (default 10th percentile = 'bad-case' window), not by the mean."""
    ex = rows[~rows["hindsight"]]
    g = ex.groupby("strategy")
    t = pd.DataFrame(
        {
            "n_windows": g.size(),
            f"score_p{int(quantile * 100)}": g["score"].quantile(quantile),
            "score_median": g["score"].median(),
            "score_mean": g["score"].mean(),
            "score_worst": g["score"].min(),
            "ann_real_return_median": g["ann_real_return"].median(),
            "max_drawdown_worst": g["max_drawdown"].max(),
            "breach_rate": g["n_breaches"].apply(lambda s: float(np.mean(s > 0))),
            "shortfall_prob": g["missed_target"].apply(
                lambda s: float(np.mean(s.astype(float))) if s.notna().all() else np.nan
            ),
            "fallback_share": g["fallback_months"].sum() / g["n_months"].sum(),
        }
    )
    t["eligible"] = True if max_breach_rate is None else t["breach_rate"] <= max_breach_rate
    key = f"score_p{int(quantile * 100)}"
    t = t.sort_values(["eligible", key, "score_median"], ascending=[False, False, False])
    t["rank"] = np.arange(1, len(t) + 1)
    return t


def select_robust(rows: pd.DataFrame, quantile: float = 0.10, max_breach_rate: float | None = None) -> str | None:
    if rows.empty:
        return None
    t = robust_table(rows, quantile, max_breach_rate)
    return t.index[0]


def walk_forward(
    rows: pd.DataFrame, quantile: float = 0.10, max_breach_rate: float | None = None, min_past_windows: int = 3
) -> pd.DataFrame:
    """For each window k, choose the strategy using ONLY windows that ended before k starts,
    then record how the chosen strategy did on window k (out-of-sample)."""
    ex = rows[~rows["hindsight"]].copy()
    ex["start"] = pd.to_datetime(ex["start"])
    ex["end"] = pd.to_datetime(ex["end"])
    wins = ex[["window", "start", "end"]].drop_duplicates().sort_values("start")
    orc = rows[rows["hindsight"]].set_index("window")["score"] if rows["hindsight"].any() else pd.Series(dtype=float)
    out = []
    for _, w in wins.iterrows():
        past = ex[ex["end"] < w["start"]]
        n_past = past["window"].nunique()
        if n_past < min_past_windows:
            continue
        chosen = select_robust(past, quantile, max_breach_rate)
        cur = ex[ex["window"] == w["window"]].set_index("strategy")
        best_ex_post = cur["score"].idxmax()
        out.append(
            {
                "window": w["window"],
                "n_past_windows": n_past,
                "chosen": chosen,
                "chosen_score": float(cur.at[chosen, "score"]),
                "chosen_missed_target": cur.at[chosen, "missed_target"],
                "chosen_rank_in_window": int(cur["score"].rank(ascending=False).at[chosen]),
                "best_ex_post": best_ex_post,
                "best_ex_post_score": float(cur["score"].max()),
                "oracle_score": float(orc.get(w["window"], np.nan)),
            }
        )
    return pd.DataFrame(out)
