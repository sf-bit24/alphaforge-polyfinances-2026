"""Outillage commun des agents Strands : modèle Bedrock, traces, limites et erreurs.

Claude Opus 5.5 sur Bedrock (Converse) : la réflexion est toujours active. On n'envoie donc jamais
``thinking: disabled`` ni ``budget_tokens``, ni ``temperature``/``top_p``/``top_k`` (refusés avec une 400).
L'effort se règle par agent avec ``additional_request_fields={"output_config": {"effort": ...}}``.
Le choix forcé d'un outil est refusé par ce modèle : les agents gardent ``tool_choice`` automatique et le
code vérifie que l'outil attendu a bien été appelé.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from botocore.config import Config as BotocoreConfig
from strands import Agent, ModelRetryStrategy
from strands.hooks import AfterModelCallEvent, AfterToolCallEvent, BeforeModelCallEvent, HookProvider, HookRegistry
from strands.models import BedrockModel, CacheConfig

from .config import Settings
from .errors import AppError, pick
from .trace import Trace, compact_value

logger = logging.getLogger("alphaforge.agents")

EFFORTS = ("low", "medium", "high")
ModelFactory = Callable[..., Any]


def bedrock_model_factory(settings: Settings) -> ModelFactory:
    """Fabrique de modèles Bedrock pour tous les agents (profil d'inférence ``ALPHAFORGE_MODEL_ID``)."""

    def factory(*, effort: str, guardrail: bool = False, max_tokens: int = 8000) -> BedrockModel:
        if effort not in EFFORTS:
            raise ValueError(f"invalid effort {effort!r}")
        config: dict[str, Any] = {
            "model_id": settings.model_id,
            "max_tokens": max_tokens,
            "additional_request_fields": {"output_config": {"effort": effort}},
            "cache_config": CacheConfig(strategy="auto"),
        }
        if guardrail and settings.guardrail_id:
            config.update(
                guardrail_id=settings.guardrail_id,
                guardrail_version=settings.guardrail_version or "DRAFT",
                guardrail_trace="enabled",
                guardrail_latest_message=True,
                guardrail_redact_input=True,
            )
        return BedrockModel(
            region_name=settings.region,
            boto_client_config=BotocoreConfig(
                connect_timeout=10, read_timeout=180, retries={"max_attempts": 2, "mode": "standard"}
            ),
            **config,
        )

    return factory


@dataclass
class AgentSpec:
    actor: str
    name: str
    effort: str
    system_prompt: str
    tools: list[Any]
    max_turns: int = 6
    max_tokens: int = 8000
    guardrail: bool = False
    tool_summaries: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = field(default_factory=dict)


class TraceHooks(HookProvider):
    """Ajoute à la trace une étape par appel du modèle et par appel d'outil (actions observables seulement)."""

    def __init__(self, trace: Trace, spec: AgentSpec, model_id: str):
        self.trace = trace
        self.spec = spec
        self.model_id = model_id
        self._model_started = 0.0
        self.model_calls = 0
        self.tool_calls: list[str] = []

    def register_hooks(self, registry: HookRegistry, **_: Any) -> None:
        registry.add_callback(BeforeModelCallEvent, self._before_model)
        registry.add_callback(AfterModelCallEvent, self._after_model)
        registry.add_callback(AfterToolCallEvent, self._after_tool)

    def _before_model(self, event: BeforeModelCallEvent) -> None:
        self._model_started = time.perf_counter()

    def _after_model(self, event: AfterModelCallEvent) -> None:
        self.model_calls += 1
        duration = int((time.perf_counter() - self._model_started) * 1000) if self._model_started else 0
        outputs: dict[str, Any] = {}
        if event.stop_response is not None:
            outputs["stop_reason"] = event.stop_response.stop_reason
            requested = [
                block["toolUse"]["name"]
                for block in event.stop_response.message.get("content", [])
                if isinstance(block, dict) and "toolUse" in block
            ]
            if requested:
                outputs["tools_requested"] = requested
        if event.exception is not None:
            outputs["error"] = type(event.exception).__name__
        self.trace.add(
            "model",
            self.spec.actor,
            self.trace.t("Appel du modèle", "Model call"),
            f"{self.model_id} · effort {self.spec.effort}",
            inputs={"call": self.model_calls},
            outputs=outputs,
            duration_ms=duration,
        )

    def _after_tool(self, event: AfterToolCallEvent) -> None:
        name = event.tool_use.get("name", "?")
        self.tool_calls.append(name)
        raw_input = event.tool_use.get("input") or {}
        summarize = self.spec.tool_summaries.get(name)
        inputs = summarize(raw_input) if summarize and isinstance(raw_input, dict) else raw_input
        result = event.result or {}
        status = result.get("status", "success") if isinstance(result, dict) else "success"
        payload: Any = None
        for block in (result.get("content") or []) if isinstance(result, dict) else []:
            if "text" in block:
                try:
                    payload = json.loads(block["text"])
                except (TypeError, ValueError):
                    payload = block["text"]
                break
        self.trace.add(
            "tool",
            self.spec.actor,
            self.trace.t(f"Outil {name}", f"Tool {name}"),
            None,
            inputs=compact_value(inputs if isinstance(inputs, dict) else {"input": inputs}),
            outputs={"status": status, "result": compact_value(payload)},
            duration_ms=int((event.duration or 0) * 1000),
        )


@dataclass
class AgentRun:
    agent: Any
    result: Any
    hooks: TraceHooks

    @property
    def stop_reason(self) -> str:
        return str(getattr(self.result, "stop_reason", ""))

    def usage(self) -> dict[str, Any]:
        metrics = getattr(self.result, "metrics", None)
        usage = getattr(metrics, "accumulated_usage", None) or {}
        return {k: usage.get(k) for k in ("inputTokens", "outputTokens", "totalTokens") if k in usage}

    def follow_up(self, prompt: str, trace: Trace, max_turns: int = 3) -> None:
        """Relance l'agent dans la même conversation (par exemple s'il n'a pas appelé l'outil final)."""
        self.result = _invoke(self.agent, prompt, max_turns, trace, self.hooks.spec)


def model_error(exc: Exception, locale: str) -> AppError:
    code = None
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
    logger.warning("model call failed: %s %s", type(exc).__name__, code or "")
    return AppError(
        "model_error",
        pick(
            locale,
            "Le modèle n'a pas pu répondre. Réessayez dans un instant.",
            "The model could not answer. Please try again in a moment.",
        ),
        {"type": type(exc).__name__, **({"code": code} if code else {})},
    )


def _invoke(agent: Any, prompt: Any, max_turns: int, trace: Trace, spec: AgentSpec) -> Any:
    try:
        return agent(prompt, limits={"turns": max_turns})
    except AppError:
        raise
    except Exception as exc:  # erreurs Bedrock, réseau, limites du fournisseur
        raise model_error(exc, trace.locale) from exc


def run_agent(
    spec: AgentSpec,
    prompt: Any,
    *,
    model_factory: ModelFactory,
    model_id: str,
    trace: Trace,
) -> AgentRun:
    model = model_factory(effort=spec.effort, guardrail=spec.guardrail, max_tokens=spec.max_tokens)
    hooks = TraceHooks(trace, spec, model_id)
    agent = Agent(
        model=model,
        tools=spec.tools,
        system_prompt=spec.system_prompt,
        callback_handler=None,
        hooks=[hooks],
        retry_strategy=ModelRetryStrategy(max_attempts=3, initial_delay=2, max_delay=8),
        name=spec.name,
    )
    started = time.perf_counter()
    result = _invoke(agent, prompt, spec.max_turns, trace, spec)
    run = AgentRun(agent=agent, result=result, hooks=hooks)
    trace.add(
        "agent",
        spec.actor,
        trace.t(f"{spec.actor} : tour terminé", f"{spec.actor}: turn finished"),
        spec.name,
        inputs={"effort": spec.effort, "max_turns": spec.max_turns},
        outputs={
            "stop_reason": run.stop_reason,
            "model_calls": hooks.model_calls,
            "tools": hooks.tool_calls,
            **run.usage(),
        },
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    check_stop_reason(run, trace, spec)
    return run


def check_stop_reason(run: AgentRun, trace: Trace, spec: AgentSpec) -> None:
    if run.stop_reason == "guardrail_intervened":
        trace.add(
            "guardrail",
            "guardrail",
            trace.t("Garde-fou déclenché", "Guardrail triggered"),
            trace.t(
                "Le garde-fou du cadre responsable a bloqué l'échange.",
                "The responsible-use guardrail blocked the exchange.",
            ),
            outputs={"agent": spec.actor},
        )
        raise AppError(
            "guardrail_blocked",
            trace.t(
                "Cette demande sort du cadre du prototype (simulation seulement, aucun conseil personnalisé). "
                "Reformulez votre message sur votre profil d'investisseur.",
                "This request is outside the prototype's scope (simulation only, no personalised advice). "
                "Please rephrase your message about your investor profile.",
            ),
        )
    if run.stop_reason == "content_filtered":
        raise AppError(
            "model_error",
            trace.t("Le modèle a refusé de répondre à cette demande.", "The model declined to answer this request."),
            {"stop_reason": run.stop_reason},
        )


def tool_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
