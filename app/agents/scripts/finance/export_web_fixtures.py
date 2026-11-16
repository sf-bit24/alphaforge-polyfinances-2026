"""Fixtures du mode ``mock`` de l'interface web : vraies décisions du moteur pour les trois profils FICTION.

Usage (depuis ``app/agents``) :
    ALPHAFORGE_BT_DATA=<données longues> uv run --group finance python scripts/finance/export_web_fixtures.py [dossier]

Pour chaque profil de démonstration (Amira, Mateo, Robert, ``tests/finance/policy/_personas.py``, FICTION), le
script appelle ``finance.debate.pipeline.build_portfolio`` en mode ``rules`` (déterministe, sans modèle) et écrit
la réponse de l'action ``build`` du runtime ``portfolio`` (CONTRACTS.md, section 12), même forme que
``portfolio_service.PortfolioService.build`` : ``decision`` (``Decision.model_dump(mode="json")``), ``rounds``,
``explanation_report``, ``grounding``, ``strategy`` (``StrategyResult.summary()``) et ``allocation``
(répartition de l'argent, ``finance/debate/allocation.py``).

Aucun nombre n'est écrit à la main : tout vient du moteur. Le dossier par défaut est
``app/web/src/lib/fixtures/`` (``portfolio-<persona>.json``). Simulation éducative seulement.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Le code de CE dépôt d'abord (un venv peut avoir une installation éditable d'un autre worktree), puis tests/.
# Deux insertions en tête (app/agents puis app/agents/src) : ruff admet ces appels avant les imports (E402).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from tests.finance.policy import _personas as personas

from alphaforge.finance.debate.pipeline import Request, build_portfolio
from alphaforge.finance.strategy import StyleInputs

AGENTS = Path(__file__).resolve().parents[2]
DEFAULT_OUT = AGENTS.parent / "web" / "src" / "lib" / "fixtures"

# client_id fixes (UUID v4) des profils de démonstration : la réponse du runtime en porte toujours un.
CLIENT_IDS = {
    "amira": "3f6c1a2e-8b4d-4c7a-9e21-a1d5f0b7c301",
    "mateo": "7a2e9c4b-1d3f-4e8a-b6c5-d2f4a8e1c702",
    "robert": "c5d8e2f1-6a9b-4b3c-8d7e-f1a2b3c4d503",
}

SCENARIOS = {
    "amira": {
        "profile": personas.amira,
        "request": None,
        "style_inputs": StyleInputs(
            employment_sector="technology", goal="growth", interests=("technology",), amount_cad=100_000
        ),
    },
    "mateo": {"profile": personas.mateo, "request": None, "style_inputs": StyleInputs(amount_cad=150_000)},
    "robert": {
        "profile": personas.robert,
        "request": Request("TSLA", amount_cad=50_000),
        "style_inputs": StyleInputs(amount_cad=200_000),
    },
}


def response_for(persona: str) -> dict:
    sc = SCENARIOS[persona]
    profile = sc["profile"]()
    result = build_portfolio(
        profile,
        personas.AS_OF,
        request=sc["request"],
        mode="rules",
        style_inputs=sc["style_inputs"],
        decision_id=f"dec-{profile.profile_id}-v{profile.version}-fixture",
    )
    client_id = CLIENT_IDS[persona]
    decision = result.decision
    return {
        "ok": True,
        "release": "fixture",
        "client_id": client_id,
        "as_of": personas.AS_OF.isoformat(),
        "mode": "rules",
        "simulation_only": True,
        "decision_key": f"clients/{client_id}/decisions/{decision.decision_id}.md",
        "decision": decision.model_dump(mode="json"),
        "rounds": [
            {
                "round": r.round,
                "verdicts": r.verdicts,
                "amendments": [a.model_dump(mode="json") for a in r.decisions],
            }
            for r in result.rounds
        ],
        "explanation_report": result.explanation_report,
        "grounding": result.grounding,
        "strategy": result.strategy.summary() if result.strategy is not None else None,
        "allocation": result.allocation,
    }


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    for persona in SCENARIOS:
        body = response_for(persona)
        path = out / f"portfolio-{persona}.json"
        path.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        d = body["decision"]
        print(
            f"{persona}: {d['kind']}, {len(d['positions'])} positions, {len(d['facts'])} facts, "
            f"style {body['strategy']['style'] if body['strategy'] else 'off'} -> {path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
