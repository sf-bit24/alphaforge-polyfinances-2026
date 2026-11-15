"""Stops sur les satellites seulement (titres individuels, crypto) : perte depuis l'entrée, baisse depuis le plus haut.

Un satellite stoppé voit sa cible ramenée à 0, le poids allant au cœur de FNB (au prorata des cibles ; à défaut
aux quasi-liquidités). Retour autorisé seulement quand son prix repasse au-dessus de sa moyenne mobile de
``reentry_ma_months``. Les niveaux (``entry_prices``, ``peaks``) sont dans les unités de ``base.price_level`` et
tenus par le tick (``base.update_stop_levels``). Aucun autre actif n'est jamais touché.
"""

from __future__ import annotations

import math

from ...contracts import Fact
from .base import OverlayContext, OverlaySignal, clean, fact, params_of, price_level


def _to_core(ctx: OverlayContext, amount: float) -> dict[str, float]:
    pool = [a for a in sorted(ctx.core_etfs) if ctx.target.get(a, 0.0) > 0] or [
        a for a in sorted(ctx.cash_like) if a in ctx.target
    ]
    if not pool:
        return {}
    tot = math.fsum(ctx.target.get(a, 0.0) for a in pool)
    return {a: amount * (ctx.target.get(a, 0.0) / tot if tot > 0 else 1 / len(pool)) for a in pool}


class _Stop:
    name = "stop"
    trigger_key = ""
    trigger_param = ""

    def __init__(self, params: dict | None = None):
        self.params = params

    def _ref(self, ctx: OverlayContext, a: str) -> float | None:
        raise NotImplementedError

    def _check(self, ctx: OverlayContext, a: str, thr: float, ma: int) -> tuple[str | None, Fact | None]:
        """(raison si le satellite ``a`` est ramené ou maintenu à 0, sinon None ; Fact de la baisse si mesurée)."""
        lvl = price_level(ctx.returns_upto, a)
        if lvl.empty:
            return None, None
        cur = float(lvl.iloc[-1])
        if ctx.weights.get(a, 0.0) <= 1e-9:  # déjà soldé : retour seulement au-dessus de la moyenne
            above_ma = len(lvl) >= ma and cur > float(lvl.iloc[-ma:].mean())
            return (None if above_ma else f"{a} soldé, prix sous sa moyenne {ma} mois : pas de retour"), None
        ref = self._ref(ctx, a)
        if ref is None or not ref > 0:  # sans niveau de référence positif (NaN compris) : aucun stop
            return None, None
        fall = 1 - cur / ref
        measured = fact(
            ctx,
            self.name,
            f"{self.trigger_key}_{a}",
            f"Baisse de {a} ({self.trigger_key})",
            fall,
            "ratio",
            params=(self.trigger_param,),
        )
        return (f"{a} −{fall:.0%} ≥ {thr:.0%} : cible ramenée à 0" if fall >= thr else None), measured

    def compute(self, ctx: OverlayContext) -> OverlaySignal:
        p = params_of(ctx, self.name, self.params)
        thr, ma = float(p[self.trigger_param]), int(p.get("reentry_ma_months", 10))
        delta: dict[str, float] = {}
        facts, reasons, n_out = [], [], 0
        for a in sorted(ctx.satellites):
            t = ctx.target.get(a, 0.0)
            if t <= 0 or a not in ctx.returns_upto.columns:
                continue
            reason, measured = self._check(ctx, a, thr, ma)
            if measured is not None:
                facts.append(measured)
            if reason is None:
                continue
            reasons.append(reason)
            n_out += 1
            delta[a] = delta.get(a, 0.0) - t
            for c, v in _to_core(ctx, t).items():
                delta[c] = delta.get(c, 0.0) + v
        return OverlaySignal(
            self.name, float(n_out), clean(delta), " ; ".join(reasons) or "aucun stop déclenché", facts
        )


class StopLoss(_Stop):
    """Perte depuis le niveau d'entrée ≥ ``loss`` (sans niveau d'entrée connu : aucun stop)."""

    name = "stop_loss"
    trigger_key = "loss_from_entry"
    trigger_param = "loss"

    def _ref(self, ctx, a):
        return ctx.entry_prices.get(a)


class TrailingStop(_Stop):
    """Baisse depuis le plus haut ≥ ``drop_from_peak`` ; sans ``peaks`` fourni, plus haut des 12 derniers mois."""

    name = "trailing_stop"
    trigger_key = "drop_from_peak"
    trigger_param = "drop_from_peak"

    def _ref(self, ctx, a):
        if a in ctx.peaks:
            return ctx.peaks[a]
        lvl = price_level(ctx.returns_upto, a)
        return float(lvl.iloc[-12:].max()) if len(lvl) else None
