"""Fenêtre de rendements point-in-time pour un mandat (aucune donnée après ``as_of``)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..backtest import data as bt_data
from ..contracts import PolicySpec


class InsufficientHistory(ValueError):
    """Moins de ``min_history_months`` mois communs à tous les actifs investissables."""


@dataclass(frozen=True)
class ReturnWindow:
    returns: pd.DataFrame            # mois × actifs, rendements totaux mensuels dans la devise du mandat
    as_of: pd.Timestamp
    currency: str
    data_version: str
    info: dict = field(default_factory=dict)

    @property
    def start(self) -> pd.Timestamp:
        return self.returns.index[0]

    @property
    def end(self) -> pd.Timestamp:
        return self.returns.index[-1]

    @property
    def n_obs(self) -> int:
        return len(self.returns)


def returns_window(policy: PolicySpec, as_of, assets: list[str] | None = None) -> ReturnWindow:
    """Rendements mensuels des ``lookback_months`` derniers mois terminés au plus tard à ``as_of``.

    L'engine ne renvoie que les dates où tous les actifs ont un rendement ; l'actif qui limite
    la fenêtre est rapporté dans ``info``.
    """
    as_of = bt_data.to_month_end(as_of)
    assets = list(assets or policy.investable)
    df = bt_data.load_returns(assets, end=as_of, currency=policy.currency)
    info = dict(df.attrs.get("info") or {})
    df = df.loc[:as_of].tail(policy.lookback_months)
    if len(df) < policy.min_history_months:
        raise InsufficientHistory(
            f"{len(df)} mois communs avant {as_of.date()} (< {policy.min_history_months}) ; "
            f"limitant : {info}")
    if df.isna().any().any():
        raise ValueError("rendements manquants dans la fenêtre")
    return ReturnWindow(df[assets], as_of, policy.currency,
                        str(bt_data.data_version().get("data_sha256")), info)
