"""Instrumentation OpenTelemetry des runtimes AgentCore (ADOT), lancée par ``main.py`` avant tout autre import.

AgentCore Runtime pose ``AGENT_OBSERVABILITY_ENABLED=true`` et ses variables ``OTEL_*`` (attributs de ressource,
en-têtes des journaux; Terraform pose aussi ce drapeau, voir agentcore.tf). ADOT (``aws-opentelemetry-distro``) en
déduit les exportateurs : spans vers X-Ray (Transaction Search), journaux vers le groupe du runtime, métriques en EMF.
Les spans de Strands (``gen_ai.*``, jetons compris), de botocore et de Starlette alimentent ainsi le tableau de bord
Observability d'AgentCore : sessions, traces, coût en jetons.

``start`` fait ce que fait ``opentelemetry-instrument python main.py`` (le point d'entrée que documente AWS) sans
passer par le script ``bin/opentelemetry-instrument``, que package.sh retire du zip. Il doit tourner avant l'import de
``bedrock_agentcore`` : l'instrumentation de Starlette remplace la classe ``Starlette``, et une application déjà
définie à partir de l'ancienne classe ne serait pas tracée.

Sans le drapeau (développement local, tests), rien n'est chargé.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Le zip contient deux distributions OpenTelemetry (celle d'AWS et celle d'opentelemetry-distro, sa dépendance) :
# sans ces variables, la première trouvée l'emporterait.
_ADOT_DEFAULTS = {"OTEL_PYTHON_DISTRO": "aws_distro", "OTEL_PYTHON_CONFIGURATOR": "aws_configurator"}

state = {"active": False}


def enabled() -> bool:
    """Vrai si l'observabilité d'AgentCore est demandée (``AGENT_OBSERVABILITY_ENABLED=true``)."""
    return os.environ.get("AGENT_OBSERVABILITY_ENABLED", "").strip().lower() == "true"


def start() -> bool:
    """Lance l'instrumentation automatique d'ADOT si elle est demandée. Renvoie vrai si elle est active.

    Une erreur d'ADOT est journalisée et ignorée : la télémétrie ne doit jamais empêcher le runtime de démarrer.
    """
    if state["active"] or not enabled():
        return state["active"]
    for name, value in _ADOT_DEFAULTS.items():
        os.environ.setdefault(name, value)
    try:
        from opentelemetry.instrumentation.auto_instrumentation import initialize
    except ImportError:
        logger.warning("opentelemetry: aws-opentelemetry-distro is missing, runtime not instrumented")
        return False
    initialize(swallow_exceptions=True)
    state["active"] = True
    return True
