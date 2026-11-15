"""Section 2 « Construire le portefeuille » : débat A3 avocat contre 4 lentilles, Judge, explication.

Simulation uniquement, aucun conseil financier. Voir le brain : references/calibration/README.md.

Import paresseux du pipeline (moteur : numpy, cvxpy) : ``merge``, ``facts``, ``schemas`` et ``okf_bridge`` restent
importables sans le groupe ``finance``, donc testables en CI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .pipeline import BuildResult, Request, build_portfolio

__all__ = ["BuildResult", "Request", "build_portfolio"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from . import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
