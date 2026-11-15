"""Étape 0 du volet finance : stratégie (défensive / dynamique / offensive) et sélection de titres.

Partie pure (CI) : ``config``, ``style``, ``rules``, ``features`` (jeu de départ, bibliothèque standard).
Partie moteur (groupe ``finance``) : ``scoring`` (historique long) et ``select.apply_strategy``, importés à la demande.
Le style change la COMPOSITION à risque égal : jamais R, le niveau, e_cap, l* ni un budget risk.*.
SIMULATION ÉDUCATIVE SEULEMENT, jamais un conseil.
"""

from .config import STYLES, StrategyConfig, StyleId, load_strategy
from .rules import Candidate, Plan, Ranked, apply_to_policy, build_limits, clamp_strategy_floors, degrade_steps
from .style import BehaviorFlags, StyleDecision, StyleInputs, band_target, behavior_flags, derive_style, k_rule

__all__ = [
    "STYLES",
    "BehaviorFlags",
    "Candidate",
    "Plan",
    "Ranked",
    "StrategyConfig",
    "StyleDecision",
    "StyleId",
    "StyleInputs",
    "apply_strategy",
    "apply_to_policy",
    "band_target",
    "behavior_flags",
    "build_limits",
    "clamp_strategy_floors",
    "degrade_steps",
    "derive_style",
    "k_rule",
    "load_strategy",
]


def apply_strategy(*args, **kwargs):
    """Import paresseux : ``select`` dépend du moteur (numpy, cvxpy)."""
    from .select import apply_strategy as _apply

    return _apply(*args, **kwargs)
