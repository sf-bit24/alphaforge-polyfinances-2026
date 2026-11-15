"""Ce que le service prête à un agent du runtime ``profile`` le temps d'une requête.

Les trois agents (A1, A2 et A1 avec son skill de base du client) se lancent de la même façon : sur le modèle du
déploiement, avec ou sans garde-fou, en inscrivant leurs étapes à la trace de la requête. ``AgentRunner`` réunit
ces éléments pour qu'un agent ne les reçoive pas un à un.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..agentkit import AgentRun, AgentSpec, ModelFactory, run_agent
from ..trace import Emitter, Trace


@dataclass(frozen=True)
class AgentRunner:
    """Lance les agents d'une requête : modèle, garde-fou, trace et flux de la réponse."""

    model_factory: ModelFactory
    # Identifiant du modèle, inscrit à la trace de chaque appel.
    model_id: str
    guardrail: bool
    trace: Trace
    # Flux SSE de la requête, ``None`` quand la réponse n'est pas diffusée.
    emitter: Emitter | None

    def run(self, spec: AgentSpec, prompt: Any) -> AgentRun:
        return run_agent(spec, prompt, model_factory=self.model_factory, model_id=self.model_id, trace=self.trace)

    def stream_message(self, text: str) -> None:
        """Envoie le message d'un agent à l'interface dès qu'il est prêt, sans attendre la fin de la requête."""
        if self.emitter is not None:
            self.emitter.delta(text)
