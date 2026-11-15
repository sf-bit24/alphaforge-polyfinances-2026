"""Force relative entre FNB du cœur : déplacement de ``tilt`` du poids des moins bons vers les meilleurs."""

from __future__ import annotations

import math

from .base import OverlayContext, OverlaySignal, clean, fact, momentum_12_1, params_of


class RelativeStrength:
    """Classe les FNB actions du cœur détenus par leur 12-1 ; la moitié la moins bonne cède ``tilt`` de son poids
    cible à la meilleure moitié (au prorata des cibles). Part actions et part du cœur inchangées."""

    name = "relative_strength"

    def __init__(self, params: dict | None = None):
        self.params = params

    def compute(self, ctx: OverlayContext) -> OverlaySignal:
        p = params_of(ctx, self.name, self.params)
        lb, skip, tilt = int(p.get("lookback", 12)), int(p.get("skip", 1)), float(p.get("tilt", 0.25))
        held = sorted(a for a in ctx.core_etfs if ctx.target.get(a, 0.0) > 0 and a in ctx.returns_upto.columns)
        mom = {a: m for a in held if (m := momentum_12_1(ctx.returns_upto[a], lb, skip)) is not None}
        if len(mom) < 2:
            return OverlaySignal(self.name, None, {}, "moins de deux FNB du cœur avec historique suffisant")
        ranked = sorted(mom, key=lambda a: (-mom[a], a))
        half = len(ranked) // 2
        best, worst = ranked[:half], ranked[len(ranked) - half :]
        moved = {a: tilt * ctx.target[a] for a in worst}
        tot = math.fsum(moved.values())
        tb = math.fsum(ctx.target[a] for a in best)
        delta = {a: -v for a, v in moved.items()}
        for a in best:
            delta[a] = delta.get(a, 0.0) + tot * ctx.target[a] / tb
        facts = [
            fact(
                ctx,
                self.name,
                f"mom_{a}",
                f"Rendement {lb}-{skip} de {a}",
                mom[a],
                "ratio",
                params=("lookback", "skip"),
            )
            for a in ranked
        ]
        facts.append(
            fact(ctx, self.name, "moved", "Poids déplacé vers les mieux classés", tot, "ratio", params=("tilt",))
        )
        return OverlaySignal(
            self.name,
            float(half),
            clean(delta),
            f"{', '.join(best)} en tête ; {tot:.1%} pris à {', '.join(worst)}",
            facts,
        )
