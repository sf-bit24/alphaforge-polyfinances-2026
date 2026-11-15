"""Dérive des poids entre deux décisions (valorisation au marché) et mesures d'écart à la cible.

Même formule que le moteur de backtest (``backtest.run_window``) : w' = w·(1+r) / (1+Σ w·r).
Poids = fractions du portefeuille (somme = 1), rendements mensuels simples dans la devise du rejeu.
"""
from __future__ import annotations

import math
from collections.abc import Mapping


def _ret(returns: Mapping[str, float], a: str) -> float | None:
    v = returns.get(a)
    if v is None:
        return None
    v = float(v)
    return None if math.isnan(v) else v


def mark_to_market(weights: Mapping[str, float],
                   returns: Mapping[str, float]) -> tuple[dict[str, float], float, list[str]]:
    """Fait dériver ``weights`` d'un mois de ``returns``.

    Renvoie (poids dérivés de somme 1, rendement brut Σ w·r, actifs détenus sans rendement).
    Un rendement absent ou NaN est traité comme 0 (prix figé) et l'actif est listé, trié, pour être
    signalé. Toutes les clés d'entrée sont conservées. Si 1 + brut <= 0 (perte totale), les poids sont
    renvoyés inchangés, comme dans le backtest.
    """
    missing = sorted(a for a, w in weights.items() if float(w) != 0.0 and _ret(returns, a) is None)
    r = {a: (_ret(returns, a) or 0.0) for a in weights}
    gross = sum(float(w) * r[a] for a, w in weights.items())
    if 1.0 + gross <= 0.0:
        out = {a: float(w) for a, w in weights.items()}
    else:
        out = {a: float(w) * (1.0 + r[a]) / (1.0 + gross) for a, w in weights.items()}
    s = sum(out.values())
    if s > 0 and abs(s - 1.0) > 1e-12:
        out = {a: v / s for a, v in out.items()}
    return out, gross, missing


def active_weights(w: Mapping[str, float], target: Mapping[str, float]) -> dict[str, float]:
    """Poids actifs w − w* sur l'union des clés (clé absente = 0), triés par asset_id."""
    keys = sorted(set(w) | set(target))
    return {a: float(w.get(a, 0.0)) - float(target.get(a, 0.0)) for a in keys}


def drift_metric(w: Mapping[str, float], target: Mapping[str, float]) -> float:
    """Dérive du portefeuille = Σ|w − w*| / 2 (définition de Betterment) : part du portefeuille
    qu'il faudrait déplacer pour revenir exactement à la cible (rotation aller simple)."""
    return 0.5 * sum(abs(v) for v in active_weights(w, target).values())
