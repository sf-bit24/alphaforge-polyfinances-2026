"""Registre des overlays (nom YAML → classe) et construction dans l'ordre de ``cfg.overlays.order``."""

from __future__ import annotations

from ..config import EvolutionConfig
from .base import Overlay
from .drawdown import DrawdownControl
from .dual_momentum import DualMomentum
from .relative_strength import RelativeStrength
from .stops import StopLoss, TrailingStop
from .take_profit import TakeProfit
from .trend import TrendTilt
from .tsmom import TimeSeriesMomentum
from .vol_target import VolTarget

REGISTRY: dict[str, type] = {
    c.name: c
    for c in (
        DrawdownControl,
        TrendTilt,
        TimeSeriesMomentum,
        DualMomentum,
        RelativeStrength,
        StopLoss,
        TrailingStop,
        TakeProfit,
        VolTarget,
    )
}


def build_overlays(cfg: EvolutionConfig, params: dict[str, dict] | None = None) -> list[Overlay]:
    """Tous les overlays de ``cfg.overlays.order`` (y compris désactivés : ils restent visibles, non appliqués).
    ``params`` remplace des paramètres par overlay (variantes de la porte de validation)."""
    params = params or {}
    unknown = [n for n in cfg.overlays.order if n not in REGISTRY]
    if unknown:
        raise KeyError(f"overlays inconnus dans evolution.yaml : {unknown}")
    return [REGISTRY[n](params.get(n)) for n in cfg.overlays.order]
