"""ReplayModel : un BedrockModel de Strands dont chaque appel est enregistré puis rejouable.

Usage dans un graphe Strands :
    model = ReplayModel(node_id="lentille_risque", store=FileStore("tests/finance/fixtures/llm_records"), mode="replay",
                        versions={"data": data_sha, "policy": "risk_levels@0.2.0"},
                        model_id="us.anthropic.claude-sonnet-5-5",
                        additional_request_fields={"output_config": {"effort": "medium"}})
    Agent(model=model, ...)

- Seule ``stream()`` est redéfinie. ``structured_output()`` de BedrockModel passe par ``self.stream()``
  et devient donc rejouable aussi.
- La clé couvre : nœud, tour (``invocation_state["debate_round"]``), versions figées, configuration du
  modèle (id, champs additionnels, guardrail), messages, outils, ``tool_choice``, système et schéma de
  sortie. Elle exclut ce qui varie d'une exécution à l'autre sans changer la requête (identifiant de
  session, signal d'annulation).
- En replay, une clé absente lève ``ReplayMissError`` : aucun appel silencieux au modèle.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime
from typing import Any

from strands.models.bedrock import BedrockModel

from .core import KEY_VERSION, Mode, ReplayMissError, Store, resolve_mode, strict_schema

_CONFIG_KEYS = (
    "model_id",
    "additional_request_fields",
    "guardrail_id",
    "guardrail_version",
    "max_tokens",
    "stop_sequences",
    "streaming",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


class ReplayModel(BedrockModel):
    def __init__(
        self,
        *,
        node_id: str,
        store: Store,
        mode: Mode | None = None,
        versions: dict[str, str] | None = None,
        **bedrock_kwargs: Any,
    ):
        config = {name: value for name, value in bedrock_kwargs.items() if name in _CONFIG_KEYS}
        if "temperature" in bedrock_kwargs or "top_p" in bedrock_kwargs:
            raise ValueError("temperature/top_p refusés par Claude 5.x : retirer ces paramètres")
        guardrail_version = config.get("guardrail_version")
        if guardrail_version is not None and str(guardrail_version).upper() == "DRAFT":
            raise ValueError("guardrail DRAFT interdit : utiliser une version numérotée")
        super().__init__(**bedrock_kwargs)
        self.node_id, self.store, self.versions = node_id, store, dict(versions or {})
        self._mode = mode
        self.last_key: str | None = None
        self.last_replayed: bool | None = None

    @property
    def mode(self) -> Mode:
        return resolve_mode(self._mode)

    def replay_key(self, request: dict[str, Any], invocation_state: dict | None) -> tuple[str, dict]:
        """Clé de rejeu et forme canonique : nœud, tour, versions figées, configuration du modèle et ``request``
        (messages, outils, ``tool_choice``, système, schéma de sortie)."""
        config = self.get_config()
        canon = {
            "key_version": KEY_VERSION,
            "kind": "strands_stream",
            "node_id": self.node_id,
            "round": (invocation_state or {}).get("debate_round"),
            "versions": self.versions,
            "config": {name: config.get(name) for name in _CONFIG_KEYS if config.get(name) is not None},
            **request,
        }
        return hashlib.sha256(_canonical_json(canon).encode("utf-8")).hexdigest(), canon

    async def stream(  # noqa: PLR0913 (signature de BedrockModel.stream, imposée par Strands)
        self,
        messages,
        tool_specs=None,
        system_prompt=None,
        *,
        tool_choice=None,
        system_prompt_content=None,
        cancel_signal=None,
        structured_output_model=None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict]:
        output_schema = strict_schema(structured_output_model.model_json_schema()) if structured_output_model else None
        request = {
            "messages": messages,
            "tool_specs": tool_specs,
            "system_prompt": system_prompt,
            "system_prompt_content": system_prompt_content,
            "tool_choice": tool_choice,
            "output_schema": output_schema,
        }
        key, canon = self.replay_key(request, kwargs.get("invocation_state"))
        self.last_key = key
        mode = self.mode
        span = self._replay_span(key, mode)
        recorded = self._recorded_events(key, mode, span)
        if recorded is not None:
            for event in recorded:
                yield event
            return
        upstream = super().stream(
            messages,
            tool_specs,
            system_prompt,
            tool_choice=tool_choice,
            system_prompt_content=system_prompt_content,
            cancel_signal=cancel_signal,
            structured_output_model=structured_output_model,
            **kwargs,
        )
        self._set_replayed(span, replayed=False)
        if mode == "live":
            async for event in upstream:
                yield event
            return
        # record : on bufferise, on publie (écriture unique), puis on émet la version ENREGISTRÉE.
        # Si un appel concurrent de même clé a gagné, on émet la sienne : la décision et le rejeu
        # portent alors exactement la même réponse.
        for event in await self._record(key, canon, upstream, span):
            yield event

    def _replay_span(self, key: str, mode: Mode):
        """Span courant, annoté du nœud, de la clé et du mode de rejeu."""
        from opentelemetry import trace as otel_trace

        span = otel_trace.get_current_span()
        span.set_attribute("alphaforge.node_id", self.node_id)
        span.set_attribute("alphaforge.replay.key", key)
        span.set_attribute("alphaforge.replay.mode", mode)
        return span

    def _set_replayed(self, span, *, replayed: bool) -> None:
        self.last_replayed = replayed
        span.set_attribute("alphaforge.replay.replayed", replayed)

    def _recorded_events(self, key: str, mode: Mode, span) -> list[dict] | None:
        """Réponse déjà enregistrée (modes replay et record) ; en replay, une clé absente lève ``ReplayMissError``."""
        if mode not in ("replay", "record"):
            return None
        record = self.store.get(key)
        if record is not None:
            self._set_replayed(span, replayed=True)
            return record["events"]
        if mode == "replay":
            raise ReplayMissError(f"aucune réponse enregistrée pour le nœud {self.node_id} ({key[:12]})")
        return None

    async def _record(self, key: str, canon: dict, upstream: AsyncIterator[dict], span) -> list[dict]:
        """Événements à émettre en mode record : les nôtres, ou ceux de l'appel concurrent qui a publié avant."""
        events = [json.loads(_canonical_json(event)) async for event in upstream]
        record = {"key": key, "created_utc": datetime.now(UTC).isoformat(), "request": canon, "events": events}
        if self.store.put_once(key, record):
            return events
        winner = self.store.get(key)
        if winner is None:
            return events
        winner_events = winner["events"]
        self._set_replayed(span, replayed=True)
        return winner_events
