"""Ciblage de volatilité : part actions × (vol cible / vol réalisée de la cible), sans levier (borné ensuite)."""

from __future__ import annotations

import math

from .base import OverlayContext, OverlaySignal, basket_returns, clean, equity_share, fact, move_equity, params_of


class VolTarget:
    """Vol réalisée (annualisée, ``lookback`` mois) du portefeuille cible ; shift = part actions × (vc/vr − 1).
    Désactivé par défaut (décision D4) : comparateur seulement."""

    name = "vol_target"

    def __init__(self, params: dict | None = None):
        self.params = params

    def compute(self, ctx: OverlayContext) -> OverlaySignal:
        p = params_of(ctx, self.name, self.params)
        tv, lb = float(p.get("target_vol", 0.08)), int(p.get("lookback", 12))
        r = basket_returns(ctx.returns_upto, ctx.target, ctx.target.keys())
        if len(r) < lb:
            return OverlaySignal(self.name, None, {}, f"historique insuffisant ({len(r)} mois < {lb})")
        vol = float(r.iloc[-lb:].std(ddof=1)) * math.sqrt(12)
        if not math.isfinite(vol) or vol <= 0:
            return OverlaySignal(self.name, None, {}, "volatilité réalisée nulle ou indéfinie")
        eq = equity_share(ctx.target, ctx.equity_assets)
        shift = eq * (min(tv / vol, 1.0 / max(eq, 1e-9)) - 1)
        facts = [
            fact(
                ctx,
                self.name,
                "realized_vol",
                f"Volatilité réalisée {lb} mois (annualisée)",
                vol,
                "ratio",
                params=("lookback",),
            ),
            fact(
                ctx, self.name, "scale", "Rapport vol cible / vol réalisée", tv / vol, "ratio", params=("target_vol",)
            ),
        ]
        delta = clean(move_equity(ctx.target, shift, ctx.equity_assets, ctx.cash_like))
        return OverlaySignal(
            self.name,
            tv / vol,
            delta,
            f"vol réalisée {vol:.1%} vs cible {tv:.1%} : {shift:+.1%} d'actions demandé",
            facts,
        )
