"""Test d'accès à Claude sur Amazon Bedrock (client Mantle) + sortie structurée Pydantic.

Usage (identifiants AWS chargés dans l'environnement, jamais écrits ici) :
    .venv/bin/python bedrock_smoke.py [--model anthropic.claude-opus-5-5]

Démontre le rôle prévu du LLM dans le moteur (R3) : extraire d'un texte une information
structurée, citée et horodatée — jamais calculer un chiffre. Le texte ci-dessous est FICTIF.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Literal

import anthropic
from anthropic import AnthropicBedrockMantle
from pydantic import BaseModel, Field

FICTIONAL_TEXT = (
    "[TEXTE FICTIF DE TEST] Communiqué du 2026-10-29 : la banque centrale relève son taux "
    "directeur d'un quart de point, citant une inflation persistante des services."
)


class PolicyEvent(BaseModel):
    """Événement de politique monétaire extrait d'un texte (pas une prévision)."""
    published: str = Field(description="Date de publication AAAA-MM-JJ telle qu'écrite dans le texte")
    direction: Literal["hausse", "baisse", "statu_quo", "inconnu"]
    tone: Literal["restrictif", "accommodant", "neutre", "inconnu"]
    quote: str = Field(description="Phrase exacte du texte qui justifie l'extraction")
    is_fictional: bool = Field(description="Vrai si le texte se déclare lui-même fictif")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic.claude-opus-5-5")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    client = AnthropicBedrockMantle(aws_region=args.region, timeout=args.timeout, max_retries=0)
    t0 = time.perf_counter()
    try:
        response = client.messages.parse(
            model=args.model,
            max_tokens=2000,
            output_config={"effort": "low"},
            system="Tu extrais des faits d'un texte. Tu n'inventes rien et tu ne calcules aucun chiffre.",
            messages=[{"role": "user", "content": f"Extrais l'événement de ce texte :\n{FICTIONAL_TEXT}"}],
            output_format=PolicyEvent,
        )
    except anthropic.NotFoundError as e:
        print(f"MODELE INTROUVABLE ({args.model}) : {e.message}")
        return 2
    except anthropic.PermissionDeniedError as e:
        print(f"ACCES REFUSE : {e.message}")
        return 3
    except anthropic.RateLimitError:
        print("QUOTA ATTEINT (429) : réessayer plus tard ou utiliser Haiku pour les sous-agents")
        return 4
    except anthropic.APIStatusError as e:
        print(f"ERREUR API {e.status_code} : {e.message}")
        return 5
    except anthropic.APITimeoutError:
        print(f"DELAI DEPASSE ({args.timeout}s) pour {args.model}")
        return 8
    except anthropic.APIConnectionError as e:
        print(f"ERREUR RESEAU : {e}")
        return 6

    dt = time.perf_counter() - t0
    if response.stop_reason == "refusal":
        print(f"REFUS : {response.stop_details}")
        return 7
    print(json.dumps({
        "model": response.model, "stop_reason": response.stop_reason, "latency_s": round(dt, 2),
        "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
        "parsed": response.parsed_output.model_dump(),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
