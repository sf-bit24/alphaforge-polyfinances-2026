"""ReplayModel : un BedrockModel de Strands dont chaque appel est enregistré puis rejouable.

Usage dans un graphe Strands :
    model = ReplayModel(node_id="lentille_risque", store=FileStore("llm_records"), mode="replay",
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
- En replay, une clé absente lève ``ReplayMiss`` : aucun appel silencieux au modèle.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from strands.models.bedrock import BedrockModel

from .core import KEY_VERSION, Mode, ReplayMiss, Store, strict_schema

_CONFIG_KEYS = ("model_id", "additional_request_fields", "guardrail_id", "guardrail_version",
                "max_tokens", "stop_sequences", "streaming")


def _canon(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


class ReplayModel(BedrockModel):
    def __init__(self, *, node_id: str, store: Store, mode: Mode | None = None,
                 versions: dict[str, str] | None = None, **bedrock_kwargs: Any):
        cfg = {k: v for k, v in bedrock_kwargs.items() if k in _CONFIG_KEYS}
        if "temperature" in bedrock_kwargs or "top_p" in bedrock_kwargs:
            raise ValueError("temperature/top_p refusés par Claude 5.x : retirer ces paramètres")
        gv = cfg.get("guardrail_version")
        if gv is not None and str(gv).upper() == "DRAFT":
            raise ValueError("guardrail DRAFT interdit : utiliser une version numérotée")
        super().__init__(**bedrock_kwargs)
        self.node_id, self.store, self.versions = node_id, store, dict(versions or {})
        self._mode = mode
        self.last_key: str | None = None
        self.last_replayed: bool | None = None

    @property
    def mode(self) -> Mode:
        m = self._mode or os.environ.get("ALPHAFORGE_LLM_MODE", "record")
        if m not in ("live", "record", "replay"):
            raise ValueError(f"mode inconnu : {m}")
        return m  # type: ignore[return-value]

    def replay_key(self, messages, tool_specs, system_prompt, tool_choice, system_prompt_content,
                   structured_output_model, invocation_state) -> tuple[str, dict]:
        cfg = self.get_config()
        canon = {
            "key_version": KEY_VERSION, "kind": "strands_stream", "node_id": self.node_id,
            "round": (invocation_state or {}).get("debate_round"), "versions": self.versions,
            "config": {k: cfg.get(k) for k in _CONFIG_KEYS if cfg.get(k) is not None},
            "messages": messages, "tool_specs": tool_specs, "system_prompt": system_prompt,
            "system_prompt_content": system_prompt_content, "tool_choice": tool_choice,
            "output_schema": strict_schema(structured_output_model.model_json_schema())
            if structured_output_model else None,
        }
        return hashlib.sha256(_canon(canon).encode("utf-8")).hexdigest(), canon

    async def stream(self, messages, tool_specs=None, system_prompt=None, *, tool_choice=None,
                     system_prompt_content=None, cancel_signal=None, structured_output_model=None,
                     **kwargs: Any) -> AsyncGenerator[dict]:
        key, canon = self.replay_key(messages, tool_specs, system_prompt, tool_choice,
                                     system_prompt_content, structured_output_model,
                                     kwargs.get("invocation_state"))
        self.last_key = key
        mode = self.mode
        from opentelemetry import trace as _otel
        _sp = _otel.get_current_span()
        _sp.set_attribute("alphaforge.node_id", self.node_id)
        _sp.set_attribute("alphaforge.replay.key", key)
        _sp.set_attribute("alphaforge.replay.mode", mode)
        if mode in ("replay", "record"):
            rec = self.store.get(key)
            if rec is not None:
                self.last_replayed = True
                _sp.set_attribute("alphaforge.replay.replayed", True)
                for ev in rec["events"]:
                    yield ev
                return
            if mode == "replay":
                raise ReplayMiss(f"aucune réponse enregistrée pour le nœud {self.node_id} ({key[:12]})")

        upstream = super().stream(messages, tool_specs, system_prompt, tool_choice=tool_choice,
                                  system_prompt_content=system_prompt_content, cancel_signal=cancel_signal,
                                  structured_output_model=structured_output_model, **kwargs)
        self.last_replayed = False
        _sp.set_attribute("alphaforge.replay.replayed", False)
        if mode == "live":
            async for ev in upstream:
                yield ev
            return
        # record : on bufferise, on publie (écriture unique), puis on émet la version ENREGISTRÉE.
        # Si un appel concurrent de même clé a gagné, on émet la sienne : la décision et le rejeu
        # portent alors exactement la même réponse.
        events = [json.loads(_canon(ev)) async for ev in upstream]
        rec = {"key": key, "created_utc": datetime.now(UTC).isoformat(), "request": canon, "events": events}
        if not self.store.put_once(key, rec):
            winner = self.store.get(key)
            if winner is not None:
                events = winner["events"]
                self.last_replayed = True
                _sp.set_attribute("alphaforge.replay.replayed", True)
        for ev in events:
            yield ev
