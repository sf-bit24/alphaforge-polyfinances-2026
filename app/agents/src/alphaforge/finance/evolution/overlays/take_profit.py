"""Prise de profit sur les satellites : poids courant > ``multiple`` × cible → la cible rend la moitié de l'excédent."""

from __future__ import annotations

import math

from .base import OverlayContext, OverlaySignal, clean, fact, params_of


class TakeProfit:
    """Pour un satellite dont le poids courant w dépasse ``multiple`` × sa cible t, la cible est réduite de
    (w − t)/2 (plancher 0) et ce poids va au cœur de FNB au prorata des cibles. Choix prudent : la règle ne fait
    jamais monter le risque ; le rééquilibrage ramène alors la ligne sous sa cible de base (« mi-chemin » de
    l'excédent rendu au cœur). Satellites seulement."""

    name = "take_profit"

    def __init__(self, params: dict | None = None):
        self.params = params

    def compute(self, ctx: OverlayContext) -> OverlaySignal:
        p = params_of(ctx, self.name, self.params)
        mult = float(p.get("multiple", 1.5))
        core = [a for a in sorted(ctx.core_etfs) if ctx.target.get(a, 0.0) > 0]
        delta: dict[str, float] = {}
        facts, reasons = [], []
        for a in sorted(ctx.satellites):
            t, w = ctx.target.get(a, 0.0), ctx.weights.get(a, 0.0)
            if t <= 0 or not core:
                continue
            facts.append(
                fact(
                    ctx,
                    self.name,
                    f"ratio_{a}",
                    f"Poids courant / cible de {a}",
                    w / t,
                    "ratio",
                    params=("multiple",),
                    processing="poids courants après dérive",
                )
            )
            if w > mult * t:
                cut = min(t, (w - t) / 2)
                delta[a] = delta.get(a, 0.0) - cut
                tc = math.fsum(ctx.target[c] for c in core)
                for c in core:
                    delta[c] = delta.get(c, 0.0) + cut * ctx.target[c] / tc
                reasons.append(f"{a} à {w / t:.2f} × sa cible : −{cut:.1%} vers le cœur")
        return OverlaySignal(
            self.name,
            float(len(reasons)),
            clean(delta),
            " ; ".join(reasons) or "aucun satellite au-delà du multiple",
            facts,
        )
