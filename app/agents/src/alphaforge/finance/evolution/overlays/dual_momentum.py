"""Double momentum (absolu) : actions contre quasi-liquidités sur 12-1 ; perdant → actions au plancher borné."""

from __future__ import annotations

from .base import (
    OverlayContext,
    OverlaySignal,
    basket_returns,
    clean,
    equity_share,
    fact,
    momentum_12_1,
    move_equity,
    params_of,
)


class DualMomentum:
    """Si le 12-1 du panier actions < celui des quasi-liquidités (0 s'il n'y en a pas), demande de sortir toutes les
    actions ; les bornes ramènent la baisse à −``max_equity_shift`` et au plancher ``e_min`` du profil."""

    name = "dual_momentum"

    def __init__(self, params: dict | None = None):
        self.params = params

    def compute(self, ctx: OverlayContext) -> OverlaySignal:
        p = params_of(ctx, self.name, self.params)
        lb, skip = int(p.get("lookback", 12)), int(p.get("skip", 1))
        me = momentum_12_1(basket_returns(ctx.returns_upto, ctx.target, ctx.equity_assets), lb, skip)
        if me is None:
            return OverlaySignal(self.name, None, {}, f"historique insuffisant (< {lb + skip} mois)")
        cash_r = basket_returns(ctx.returns_upto, ctx.target, ctx.cash_like)
        mc = momentum_12_1(cash_r, lb, skip) if len(cash_r) else None
        mc_v = 0.0 if mc is None else mc
        facts = [
            fact(
                ctx,
                self.name,
                "mom_equity",
                f"Rendement {lb}-{skip} du panier actions",
                me,
                "ratio",
                params=("lookback", "skip"),
            ),
            fact(
                ctx,
                self.name,
                "mom_cash",
                f"Rendement {lb}-{skip} des quasi-liquidités",
                mc_v,
                "ratio",
                params=("lookback", "skip"),
                status="FAIT" if mc is not None else "HYPOTHESE",
                processing=None if mc is not None else "aucune quasi-liquidité avec historique : 0 supposé",
            ),
        ]
        if me >= mc_v:
            return OverlaySignal(
                self.name, 1.0, {}, f"actions {me:+.1%} ≥ quasi-liquidités {mc_v:+.1%} : aucun déplacement", facts
            )
        delta = clean(
            move_equity(ctx.target, -equity_share(ctx.target, ctx.equity_assets), ctx.equity_assets, ctx.cash_like)
        )
        return OverlaySignal(
            self.name,
            -1.0,
            delta,
            f"actions {me:+.1%} < quasi-liquidités {mc_v:+.1%} : sortie des actions demandée (bornée par le profil)",
            facts,
        )
