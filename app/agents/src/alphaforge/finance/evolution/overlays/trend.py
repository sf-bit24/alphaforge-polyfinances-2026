"""Inclinaison de tendance : panier actions (pondéré par la cible) contre sa moyenne mobile de ``ma_months``."""
from __future__ import annotations

from .base import OverlayContext, OverlaySignal, basket_returns, clean, fact, move_equity, params_of


class TrendTilt:
    """Indice du panier actions ≥ sa moyenne des ``ma_months`` derniers niveaux → +shift, sinon −shift
    (même règle que ``backtest.strategies.TrendFilter``, appliquée au panier, en inclinaison bornée)."""

    name = "trend_tilt"

    def __init__(self, params: dict | None = None):
        self.params = params

    def compute(self, ctx: OverlayContext) -> OverlaySignal:
        p = params_of(ctx, self.name, self.params)
        ma, shift = int(p.get("ma_months", 10)), float(p.get("shift", 0.10))
        r = basket_returns(ctx.returns_upto, ctx.target, ctx.equity_assets)
        if len(r) < ma:
            return OverlaySignal(self.name, None, {}, f"historique insuffisant ({len(r)} mois < {ma})")
        idx = (1 + r.iloc[-ma:]).cumprod()
        last, avg = float(idx.iloc[-1]), float(idx.mean())
        sig = 1.0 if last >= avg else -1.0
        delta = clean(move_equity(ctx.target, sig * shift, ctx.equity_assets, ctx.cash_like))
        facts = [fact(ctx, self.name, "ratio_to_ma", f"Indice actions / moyenne mobile {ma} mois", last / avg,
                     "ratio", params=("ma_months",)),
                 fact(ctx, self.name, "signal", "Signal de tendance (+1 au-dessus, −1 en dessous)", sig, "signe",
                      params=("ma_months", "shift"))]
        pos = "au-dessus" if sig > 0 else "en dessous"
        return OverlaySignal(self.name, sig, delta,
                             f"panier actions {pos} de sa moyenne {ma} mois (ratio {last / avg:.3f}) : "
                             f"{sig * shift:+.0%} d'actions demandé", facts)
