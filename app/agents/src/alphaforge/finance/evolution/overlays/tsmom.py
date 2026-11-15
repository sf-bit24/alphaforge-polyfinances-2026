"""Momentum temporel (time-series momentum) : signe du rendement 12-1 du panier actions, et de l'or s'il est détenu."""
from __future__ import annotations

import math

from .base import (
    OverlayContext,
    OverlaySignal,
    basket_returns,
    clean,
    fact,
    momentum_12_1,
    move_equity,
    params_of,
)

GOLD_CLASSES = frozenset({"commodity", "etf_commodity"})


class TimeSeriesMomentum:
    """Rendement 12-1 du panier actions > 0 → +shift, < 0 → −shift. Or (``GLD`` ou classe matière première) détenu
    avec un 12-1 négatif : jusqu'à ``shift`` de sa cible va aux quasi-liquidités (jamais de hausse de l'or)."""

    name = "tsmom"

    def __init__(self, params: dict | None = None):
        self.params = params

    def compute(self, ctx: OverlayContext) -> OverlaySignal:
        p = params_of(ctx, self.name, self.params)
        lb, skip, shift = int(p.get("lookback", 12)), int(p.get("skip", 1)), float(p.get("shift", 0.05))
        m = momentum_12_1(basket_returns(ctx.returns_upto, ctx.target, ctx.equity_assets), lb, skip)
        if m is None:
            return OverlaySignal(self.name, None, {}, f"historique insuffisant (< {lb + skip} mois)")
        sig = 1.0 if m > 0 else -1.0
        delta = move_equity(ctx.target, sig * shift, ctx.equity_assets, ctx.cash_like)
        facts = [fact(ctx, self.name, "mom_equity", f"Rendement {lb}-{skip} du panier actions", m, "ratio",
                      params=("lookback", "skip"))]
        reason = f"rendement {lb}-{skip} des actions {m:+.1%} : {sig * shift:+.0%} d'actions demandé"
        gold = [a for a, w in ctx.target.items() if w > 0 and (a == "GLD" or ctx.asset_class.get(a) in GOLD_CLASSES)]
        cash = [a for a in sorted(ctx.cash_like) if a in ctx.target]
        for g in gold:
            if g not in ctx.returns_upto.columns:
                continue
            mg = momentum_12_1(ctx.returns_upto[g], lb, skip)
            if mg is None:
                continue
            facts.append(fact(ctx, self.name, f"mom_{g}", f"Rendement {lb}-{skip} de {g}", mg, "ratio",
                              params=("lookback", "skip")))
            if mg < 0 and cash:
                cut = min(shift, ctx.target[g] + delta.get(g, 0.0))
                delta[g] = delta.get(g, 0.0) - cut
                tc = math.fsum(ctx.target.get(a, 0.0) for a in cash)
                for a in cash:
                    share = ctx.target.get(a, 0.0) / tc if tc > 0 else 1 / len(cash)
                    delta[a] = delta.get(a, 0.0) + cut * share
                reason += f" ; {g} {mg:+.1%} : −{cut:.0%} vers les quasi-liquidités"
        return OverlaySignal(self.name, sig, clean(delta), reason, facts)
