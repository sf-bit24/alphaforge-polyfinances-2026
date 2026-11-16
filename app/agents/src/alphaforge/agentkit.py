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
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any

from botocore.config import Config as BotocoreConfig
from strands import Agent, ModelRetryStrategy
from strands.hooks import AfterModelCallEvent, AfterToolCallEvent, BeforeModelCallEvent, HookProvider, HookRegistry
from strands.models import BedrockModel, CacheConfig

from .config import Settings
from .errors import AppError, pick
from .personal_data import contains_sin
from .trace import Trace, compact_value

logger = logging.getLogger("alphaforge.agents")

EFFORTS = ("low", "medium", "high")
ModelFactory = Callable[..., Any]

SIN_ENTITY = "CA_SIN"
# Le NAS dans la trace du garde-fou : filtre géré et regex.
SIN_NAMES = frozenset({"CA_SOCIAL_INSURANCE_NUMBER", "nas-canadien"})
# Nom de la donnée personnelle bloquée, pour le message à l'investisseur : types PII du garde-fou, NAS compris.
PERSONAL_DATA_LABELS = {
    SIN_ENTITY: ("NAS", "SIN"),
    "CA_HEALTH_NUMBER": ("numéro d'assurance maladie", "health card number"),
    "CREDIT_DEBIT_CARD_NUMBER": ("numéro de carte de paiement", "payment card number"),
    "PASSWORD": ("mot de passe", "password"),
    "PIN": ("NIP", "PIN"),
}


class GuardrailTraceMixin:
    """Retient l'évaluation du garde-fou de la dernière réponse du modèle (``metadata.trace.guardrail``).

    Strands lit cette trace pour masquer l'entrée bloquée, mais ne la garde pas dans le résultat de l'agent.
    Seuls les types des politiques en sont lus (``blocked_personal_data``) : ses ``match`` contiennent la donnée
    elle-même et ne sont ni journalisés ni écrits à la trace."""

    guardrail_assessment: dict[str, Any] | None = None

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[Any]:
        self.guardrail_assessment = None
        async for event in super().stream(*args, **kwargs):
            metadata = event.get("metadata") if isinstance(event, dict) else None
            assessment = (metadata.get("trace") or {}).get("guardrail") if isinstance(metadata, dict) else None
            if isinstance(assessment, dict):
                self.guardrail_assessment = assessment
            yield event


class TracedBedrockModel(GuardrailTraceMixin, BedrockModel):
    """Modèle Bedrock des agents : ``BedrockModel`` qui retient la trace du garde-fou."""


def bedrock_model_factory(settings: Settings) -> ModelFactory:
    """Fabrique de modèles Bedrock pour tous les agents (profil d'inférence ``ALPHAFORGE_MODEL_ID``)."""

    def factory(
        *, effort: str, guardrail: bool = False, max_tokens: int = 8000, guard_tagged: bool = False
    ) -> TracedBedrockModel:
        """``guard_tagged`` : le garde-fou n'évalue que les blocs ``guardContent`` que l'agent pose lui-même
        (le texte de l'investisseur), pas le contexte ni les consignes écrits par le code. Sans lui, Strands
        enveloppe tout le dernier message utilisateur, et le filtre d'attaque de prompt prend nos consignes
        pour une attaque."""
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
                guardrail_latest_message=not guard_tagged,
                guardrail_redact_input=True,
            )
        return TracedBedrockModel(
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
    # Vrai quand le prompt marque lui-même le texte de l'investisseur (blocs guardContent, voir guarded()).
    guard_tagged: bool = False
    tool_summaries: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = field(default_factory=dict)
    # Nom de l'agent à l'écran (« Yan » pour A1 et A2); sans lui, les titres de la trace ne nomment personne.
    shown_as: str | None = None
    # Titre à l'écran (français, anglais) de chaque outil; un outil sans titre reçoit un titre général.
    tool_titles: dict[str, tuple[str, str]] = field(default_factory=dict)


def guarded(text: str) -> dict[str, Any]:
    """Bloc évalué par le garde-fou : seulement du texte venu de l'investisseur."""
    return {"guardContent": {"text": {"text": text}}}


def unguarded(prompt: Any) -> Any:
    """Le prompt sans blocs ``guardContent``, remplacés par du texte simple.

    Bedrock refuse un bloc ``guardContent`` sans ``guardrailConfig`` (ValidationException). Sans garde-fou
    configuré (``ALPHAFORGE_GUARDRAIL_ID`` absent, en local par exemple), le texte de l'investisseur part donc
    dans un bloc texte ordinaire."""
    if not isinstance(prompt, list):
        return prompt
    return [
        {"text": block["guardContent"]["text"]["text"]}
        if isinstance(block, dict) and "guardContent" in block
        else block
        for block in prompt
    ]


def guardrail_texts(prompt: Any, *, guard_tagged: bool) -> list[str]:
    """Les textes du prompt que le garde-fou évalue.

    Avec ``guard_tagged``, seulement les blocs ``guardContent`` (le texte de l'investisseur, A1). Sinon, Strands
    enveloppe tout le texte du dernier message utilisateur (A2 : texte collé et fichiers lus comme texte); les
    documents joints (PDF, CSV…) n'y passent pas."""
    if isinstance(prompt, str):
        return [prompt]
    texts = []
    for block in prompt if isinstance(prompt, list) else []:
        if not isinstance(block, dict):
            continue
        if "guardContent" in block:
            texts.append(str(block["guardContent"].get("text", {}).get("text", "")))
        elif not guard_tagged and isinstance(block.get("text"), str):
            texts.append(block["text"])
    return texts


def blocked_personal_data(assessment: Any) -> str | None:
    """Type de la donnée personnelle que le garde-fou a bloquée dans l'entrée, d'après sa trace, ou ``None``.

    ``inputAssessment`` associe à chaque garde-fou ses politiques; dans ``sensitiveInformationPolicy``, un type PII
    (``piiEntities``) ou une regex (``regexes``) en ``BLOCKED``. Le NAS, par le filtre géré ou par la regex
    ``nas-canadien``, devient ``CA_SIN``. Les sorties bloquées (``outputAssessments``) ne viennent pas du message de
    l'investisseur : elles gardent le message général."""
    inputs = assessment.get("inputAssessment") if isinstance(assessment, dict) else None
    policies = [policy for policy in (inputs or {}).values() if isinstance(policy, dict)]
    for policy in policies:
        sensitive = policy.get("sensitiveInformationPolicy") or {}
        for kind, key in (("piiEntities", "type"), ("regexes", "name")):
            for item in sensitive.get(kind) or []:
                if isinstance(item, dict) and item.get("action") == "BLOCKED" and item.get("detected", True):
                    name = str(item.get(key) or "PII")
                    return SIN_ENTITY if name in SIN_NAMES else name
    return None


def personal_data_error(entity: str, trace: Trace, spec: AgentSpec, *, source: str) -> AppError:
    """Refus d'un renseignement personnel : la trace dit lequel (jamais sa valeur), le message dit quoi faire.

    Le code reste ``guardrail_blocked`` (CONTRACTS.md, section 2); ``details.reason`` vaut ``personal_data``."""
    label = PERSONAL_DATA_LABELS.get(entity)
    trace.add(
        "guardrail",
        "guardrail",
        trace.t("Protection de vos renseignements personnels", "Protection of your personal information"),
        trace.t(
            "Votre message contient un renseignement personnel : il n'a pas été traité.",
            "Your message contains personal information: it was not processed.",
        ),
        outputs={"agent": spec.actor, "reason": "personal_data", "entity": entity, "source": source},
    )
    named_fr, named_en = (f" ({label[0]})", f" ({label[1]})") if label else ("", "")
    return AppError(
        "guardrail_blocked",
        trace.t(
            f"Votre message contient un renseignement personnel{named_fr} : retirez-le, puis renvoyez-le.",
            f"Your message contains personal information{named_en}: remove it, then send it again.",
        ),
        {"reason": "personal_data", "entity": entity},
    )


def check_personal_data(prompt: Any, trace: Trace, spec: AgentSpec) -> None:
    """Refuse avant l'appel au modèle un NAS, pour en donner la vraie raison : celui que le garde-fou bloque (trois
    groupes séparés) et celui qu'il laisse passer (9 chiffres collés, voir ``personal_data.contains_sin``)."""
    if any(contains_sin(text) for text in guardrail_texts(prompt, guard_tagged=spec.guard_tagged)):
        raise personal_data_error(SIN_ENTITY, trace, spec, source="local")


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
        who = self.spec.shown_as
        self.trace.add(
            "model",
            self.spec.actor,
            self.trace.t(f"{who} prépare sa réponse", f"{who} prepares the answer")
            if who
            else self.trace.t("Préparation de la réponse", "Preparing the answer"),
            None,
            inputs={"call": self.model_calls, "model": self.model_id, "effort": self.spec.effort},
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
        title = self.spec.tool_titles.get(name) or ("Étape de travail", "Work step")
        self.trace.add(
            "tool",
            self.spec.actor,
            self.trace.t(*title),
            None,
            inputs=compact_value(inputs if isinstance(inputs, dict) else {"input": inputs}),
            outputs={"tool": name, "status": status, "result": compact_value(payload)},
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
            "Le service ne répond pas pour l'instant : réessayez dans un instant.",
            "The service is not answering right now: try again in a moment.",
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
    extra = {"guard_tagged": True} if spec.guard_tagged else {}
    if spec.guardrail:
        check_personal_data(prompt, trace, spec)
    else:
        prompt = unguarded(prompt)
    model = model_factory(effort=spec.effort, guardrail=spec.guardrail, max_tokens=spec.max_tokens, **extra)
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
        trace.t(f"{spec.shown_as} a terminé", f"{spec.shown_as} finished")
        if spec.shown_as
        else trace.t("Réponse terminée", "Answer finished"),
        None,
        inputs={"agent": spec.name, "effort": spec.effort, "max_turns": spec.max_turns},
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
        entity = blocked_personal_data(getattr(getattr(run.agent, "model", None), "guardrail_assessment", None))
        if entity:
            raise personal_data_error(entity, trace, spec, source="guardrail")
        trace.add(
            "guardrail",
            "guardrail",
            trace.t("Vérification du cadre du service", "Service scope check"),
            trace.t(
                "Cette demande sort du cadre du service : elle n'a pas été traitée.",
                "This request is outside the service's scope: it was not processed.",
            ),
            outputs={"agent": spec.actor},
        )
        raise AppError(
            "guardrail_blocked",
            trace.t(
                "Cette demande sort du cadre du service (simulation seulement, aucun conseil personnalisé). "
                "Reformulez votre message sur votre profil d'investisseur.",
                "This request is outside the service's scope (simulation only, no personalised advice). "
                "Please rephrase your message about your investor profile.",
            ),
        )
    if run.stop_reason == "content_filtered":
        raise AppError(
            "model_error",
            trace.t(
                "Nous ne pouvons pas répondre à cette demande. Reformulez votre message.",
                "We cannot answer this request. Please rephrase your message.",
            ),
            {"stop_reason": run.stop_reason},
        )


def tool_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
