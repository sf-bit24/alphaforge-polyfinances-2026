"""Backtest windows over a monthly calendar."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .data import to_month_end


@dataclass(frozen=True)
class Window:
    start: pd.Timestamp  # first month whose return is included (month-end date)
    end: pd.Timestamp  # last month included (month-end date)
    n_months: int

    @property
    def label(self) -> str:
        return f"{self.start:%Y-%m}..{self.end:%Y-%m}"


def windows(  # noqa: PLR0913 - frozen public signature (calibration scripts, README, run.py)
    horizon_years: float,
    start,
    end,
    mode: str = "non_overlapping",
    step_months: int = 12,
    index: pd.DatetimeIndex | None = None,
) -> list[Window]:
    """Split [start, end] (inclusive month-ends) into windows of `horizon_years`.

    mode="non_overlapping": consecutive windows, step = horizon (e.g. 3y on 1926-07..2026-09 -> 33 windows).
    mode="rolling": a window starts every `step_months` months (overlapping).
    Only complete windows are returned. If `index` is given, windows are cut on that
    index (positions), otherwise on a regular month-end calendar.
    """
    n = int(round(horizon_years * 12))
    if n <= 0:
        raise ValueError("horizon must be positive")
    if mode not in ("non_overlapping", "rolling"):
        raise ValueError("mode must be 'non_overlapping' or 'rolling'")
    step = n if mode == "non_overlapping" else int(step_months)
    if step <= 0:
        raise ValueError("step_months must be positive")
    if index is None:
        calendar = pd.date_range(to_month_end(start), to_month_end(end), freq="ME")
    else:
        calendar = index[(index >= to_month_end(start)) & (index <= to_month_end(end))]
    result = []
    i = 0
    while i + n <= len(calendar):
        result.append(Window(calendar[i], calendar[i + n - 1], n))
        i += step
    return result
