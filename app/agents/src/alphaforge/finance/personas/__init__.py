"""Personas FICTION de démonstration pour le runtime portfolio (``{"action": "build", "persona": "amira"}``).

Les profils sont les personas de test du moteur ; les variables de style et la demande précise sont des choix de
démonstration (``demo.yaml``), étiquetés FICTION. Ils ne remplacent jamais un vrai profil client (``client_id``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DIR = Path(__file__).parent


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    return yaml.safe_load((DIR / "demo.yaml").read_text(encoding="utf-8"))["personas"]


def ids() -> list[str]:
    return sorted(catalog())


def load(persona: str) -> tuple[Any, Any, dict | None, str]:
    """(InvestorProfile, StyleInputs, demande ou None, libellé) d'un persona FICTION."""
    from alphaforge.finance.contracts import InvestorProfile
    from alphaforge.finance.strategy import StyleInputs

    spec = catalog()[persona]
    profile = InvestorProfile.model_validate(json.loads((DIR / f"{persona}.json").read_text(encoding="utf-8")))
    si = dict(spec.get("style_inputs") or {})
    for k in ("interests", "exclusions", "account_types", "products_known", "portfolio_flags"):
        if k in si:
            si[k] = tuple(si[k])
    if profile.investable_wealth and "amount_cad" not in si:
        si["amount_cad"] = float(profile.investable_wealth)
    return profile, StyleInputs(**si), spec.get("request"), spec["label"]
