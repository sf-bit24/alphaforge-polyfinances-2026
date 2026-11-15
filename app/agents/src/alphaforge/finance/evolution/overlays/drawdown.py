"""Contrôle de baisse de type CPPI sur un objectif « besoin » : part risquée max = m × coussin / valeur."""

from __future__ import annotations

from .base import OverlayContext, OverlaySignal, clean, equity_share, fact, move_equity, params_of


class DrawdownControl:
    """Plancher F = ``floor_share_of_need`` × ``need_floor_cad`` ; part actions max = clip(m × (V − F)/V, 0, 1).
    Si la part actions courante (ou la cible) dépasse ce maximum : baisse demandée jusqu'à ce maximum ; sinon 0.
    Sans objectif « besoin » (``need_floor_cad`` absent) : inactif. Ne peut jamais descendre sous ``e_min``."""

    name = "drawdown_control"

    def __init__(self, params: dict | None = None):
        self.params = params

    def compute(self, ctx: OverlayContext) -> OverlaySignal:
        p = params_of(ctx, self.name, self.params)
        if ctx.need_floor_cad is None or ctx.value_cad <= 0:
            return OverlaySignal(self.name, None, {}, "aucun objectif « besoin » : CPPI inactif")
        m, share = float(p.get("multiplier", 3.0)), float(p.get("floor_share_of_need", 1.0))
        floor = share * float(ctx.need_floor_cad)
        cushion = (ctx.value_cad - floor) / ctx.value_cad
        max_risky = min(max(m * cushion, 0.0), 1.0)
        eq_w, eq_t = equity_share(ctx.weights, ctx.equity_assets), equity_share(ctx.target, ctx.equity_assets)
        facts = [
            fact(
                ctx,
                self.name,
                "cushion",
                "Coussin (valeur − plancher) / valeur",
                cushion,
                "ratio",
                params=("floor_share_of_need",),
                processing="valeur du portefeuille et besoin déclaré",
            ),
            fact(
                ctx,
                self.name,
                "max_risky",
                "Part actions maximale CPPI",
                max_risky,
                "ratio",
                params=("multiplier", "floor_share_of_need"),
            ),
        ]
        if max(eq_w, eq_t) <= max_risky:
            return OverlaySignal(
                self.name,
                max_risky,
                {},
                f"part actions {eq_w:.0%} ≤ maximum CPPI {max_risky:.0%} : aucun déplacement",
                facts,
            )
        shift = min(0.0, max_risky - eq_t)
        delta = clean(move_equity(ctx.target, shift, ctx.equity_assets, ctx.cash_like)) if shift < 0 else {}
        return OverlaySignal(
            self.name,
            max_risky,
            delta,
            f"part actions {eq_w:.0%} > maximum CPPI {max_risky:.0%} (coussin {cushion:.0%}) : {shift:+.0%} demandé",
            facts,
        )
