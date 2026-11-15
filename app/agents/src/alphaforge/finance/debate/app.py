"""Point d'entrée AgentCore Runtime (streaming) pour « construire le portefeuille ».

Charge utile attendue :
    {"profile_id": "...", "as_of": "2026-09-30", "request": {"ticker": "TSLA", "amount_cad": 50000} | null,
     "mode": "llm" | "rules"}
Le profil vient de l'OKF client du magasin de l'app (``ALPHAFORGE_STORE``) ; la Decision est réécrite dans l'OKF client.
Les événements streamés donnent l'avancement ; le dernier contient la Decision complète.
Local : ``python -m agents.app`` puis POST http://localhost:8080/invocations
"""

from __future__ import annotations

import os
from datetime import date

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from .pipeline import Request, build_portfolio

app = BedrockAgentCoreApp()


def _stores():
    from alphaforge.finance.debate.okf_bridge import stores_from_env

    return stores_from_env()


@app.entrypoint
async def invoke(payload, context=None):
    cs, ms = _stores()
    yield {"event": "start", "profile_id": payload["profile_id"]}
    profile = cs.load_profile(payload["profile_id"])
    req = payload.get("request")
    res = build_portfolio(
        profile,
        date.fromisoformat(payload.get("as_of", "2026-09-30")),
        request=Request(**req) if req else None,
        mode=payload.get("mode", "llm"),
        evidence_fn=ms.evidence,
        guardrail_id=os.environ.get("ALPHAFORGE_GUARDRAIL_ID"),
        guardrail_version=os.environ.get("ALPHAFORGE_GUARDRAIL_VERSION"),
    )
    for r in res.rounds:
        yield {
            "event": "round",
            "round": r.round,
            "verdicts": r.verdicts,
            "amendments": [a.model_dump() for a in r.decisions],
        }
    uri = cs.save_decision(res.decision, res.policy)
    yield {
        "event": "decision",
        "uri": uri,
        "decision": res.decision.model_dump(mode="json"),
        "explanation_report": res.explanation_report,
        "grounding": res.grounding,
    }


if __name__ == "__main__":
    app.run()
