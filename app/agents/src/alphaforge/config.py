"""Réglages d'exécution lus dans l'environnement (CONTRACTS.md, section 1).

Aucun secret n'est lu ici : les identifiants AWS viennent de la chaîne par défaut de boto3
(rôle d'exécution du runtime AgentCore, ou profil du poste en développement).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

# "router", "expert", "researcher" : recherche par experts de sujet (alphaforge.research, CONTRACTS.md section 11).
# "portfolio" : construction du portefeuille simulé (volet finance, section 12), déployé seulement si portfolio_enabled.
ROLES = ("profile", "press", "data", "supervisor", "router", "expert", "researcher", "portfolio")
DEFAULT_MODEL_ID = "us.anthropic.claude-opus-5-5"
DEFAULT_REGION = "us-east-1"


@dataclass(frozen=True)
class Settings:
    role: str
    env: str
    release: str
    region: str
    store: str
    bucket: str | None
    local_dir: str
    model_id: str
    kb_id: str | None
    guardrail_id: str | None
    guardrail_version: str | None
    # Recherche par experts : ARN ou nom du runtime researcher (Terraform pose le nom, l'ARN est trouvé par
    # ListAgentRuntimes; vides en local : les chercheurs tournent dans des fils)
    # et modèle facultatif des chercheurs (par défaut celui de tous les agents).
    researcher_arn: str | None = None
    researcher_name: str | None = None
    researcher_model_id: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ

        def opt(name: str) -> str | None:
            value = (env.get(name) or "").strip()
            return value or None

        return cls(
            role=(opt("AGENT_ROLE") or "profile").lower(),
            env=opt("ALPHAFORGE_ENV") or "local",
            release=opt("ALPHAFORGE_RELEASE") or "dev",
            region=opt("ALPHAFORGE_REGION") or opt("AWS_REGION") or DEFAULT_REGION,
            store=(opt("ALPHAFORGE_STORE") or "local").lower(),
            bucket=opt("ALPHAFORGE_BUCKET"),
            local_dir=opt("ALPHAFORGE_LOCAL_DIR") or ".local-kb",
            model_id=opt("ALPHAFORGE_MODEL_ID") or DEFAULT_MODEL_ID,
            kb_id=opt("ALPHAFORGE_KB_ID"),
            guardrail_id=opt("ALPHAFORGE_GUARDRAIL_ID"),
            guardrail_version=opt("ALPHAFORGE_GUARDRAIL_VERSION"),
            researcher_arn=opt("ALPHAFORGE_RESEARCHER_ARN"),
            researcher_name=opt("ALPHAFORGE_RESEARCHER_NAME"),
            researcher_model_id=opt("ALPHAFORGE_RESEARCHER_MODEL_ID"),
        )

    @property
    def guardrail_enabled(self) -> bool:
        return bool(self.guardrail_id)
