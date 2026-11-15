"""Appels LLM enregistrés et rejouables — la couche de déterminisme d'AlphaForge AI.

Claude 5.x sur Bedrock n'a ni ``temperature`` ni ``seed``, et sa pensée est toujours active :
une même requête peut donner deux sorties différentes. Le seul moyen de reproduire une
décision au bit près est d'**enregistrer** chaque réponse puis de la **rejouer**.

Modes (variable ALPHAFORGE_LLM_MODE ou argument) :
- ``live``   : appel Bedrock, réponse validée, PAS enregistrée ;
- ``record`` : appel Bedrock, réponse validée et enregistrée (écriture unique, jamais écrasée) ;
- ``replay`` : lecture seule ; une clé absente lève ``ReplayMissError`` (aucun appel silencieux).

La clé est le sha256 d'une forme canonique de TOUT ce qui influence la réponse : modèle, version
du prompt et du guardrail, effort, système, messages, outils, schéma de sortie, versions des
données et de la politique, nœud du graphe et numéro de tour.
Les chiffres ne viennent jamais du LLM : cette couche ne sert qu'aux textes et aux choix fermés.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, NamedTuple, Protocol

from pydantic import BaseModel, ValidationError

Mode = Literal["live", "record", "replay"]
KEY_VERSION = "1"


class ReplayMissError(KeyError):
    """Mode replay et aucune réponse enregistrée pour cette clé."""


class LLMOutputError(RuntimeError):
    """Sortie non valide après le nombre maximal de tentatives : l'appelant bascule sur son repli
    déterministe (gabarit) au lieu de boucler."""


# --------------------------------------------------------------------------- requête et clé


def strict_schema(schema: dict) -> dict:
    """Schéma strict exigé par la sortie structurée de Claude : chaque objet a
    ``additionalProperties: false`` et tous ses champs sont obligatoires (``$defs`` compris)."""

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                node["additionalProperties"] = False
                if "properties" in node:
                    node["required"] = sorted(node["properties"])
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
        return node

    return walk(json.loads(json.dumps(schema)))


@dataclass(frozen=True)
class LLMRequest:
    model_id: str  # ex. us.anthropic.claude-opus-5-5 (bedrock-runtime)
    messages: tuple[dict, ...]  # format Converse
    system: str | None = None
    output_model: type[BaseModel] | None = None  # sortie structurée native (JSON Schema)
    effort: str | None = None  # low | medium | high | xhigh | max
    max_tokens: int = 4000
    prompt_ref: str | None = None  # ARN Prompt Management + version (traçabilité)
    guardrail: tuple[str, str] | None = None  # (identifiant, version NUMÉROTÉE, jamais DRAFT)
    node_id: str = "default"  # nœud du graphe (lentille, avocat, juge…)
    round: int = 0  # tour du débat
    data_version: str | None = None
    policy_version: str | None = None
    extra: tuple[tuple[str, str], ...] = ()  # autres versions à figer (clé, valeur)

    def __post_init__(self):
        if self.guardrail and self.guardrail[1].upper() == "DRAFT":
            raise ValueError("guardrail DRAFT interdit : utiliser une version numérotée")

    def schema(self) -> dict | None:
        return strict_schema(self.output_model.model_json_schema()) if self.output_model else None

    def canonical(self) -> dict:
        return {
            "key_version": KEY_VERSION,
            "model_id": self.model_id,
            "system": self.system,
            "messages": list(self.messages),
            "output_schema": self.schema(),
            "effort": self.effort,
            "max_tokens": self.max_tokens,
            "prompt_ref": self.prompt_ref,
            "guardrail": list(self.guardrail) if self.guardrail else None,
            "node_id": self.node_id,
            "round": self.round,
            "data_version": self.data_version,
            "policy_version": self.policy_version,
            "extra": [list(x) for x in self.extra],
        }

    def key(self) -> str:
        blob = json.dumps(self.canonical(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- stockage


class Store(Protocol):
    def get(self, key: str) -> dict | None: ...
    def put_once(self, key: str, record: dict) -> bool: ...  # False si la clé existe déjà


class FileStore:
    """Un fichier JSON par clé ; création exclusive, aucune réécriture (dev, tests, démo hors ligne)."""

    def __init__(self, root: str | os.PathLike):
        self.root = os.fspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, key: str) -> str:
        return os.path.join(self.root, key[:2], f"{key}.json")

    def get(self, key: str) -> dict | None:
        try:
            with open(self._path(key), encoding="utf-8") as record_file:
                return json.load(record_file)
        except FileNotFoundError:
            return None

    def put_once(self, key: str, record: dict) -> bool:
        """Écrit dans un fichier temporaire, puis publie par lien dur (atomique, sans écrasement) :
        un lecteur ne voit jamais un fichier à moitié écrit."""
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            return False
        staging = f"{path}.{os.getpid()}.{time.monotonic_ns()}.tmp"
        try:
            with open(staging, "x", encoding="utf-8") as staging_file:
                json.dump(record, staging_file, ensure_ascii=False, indent=1, sort_keys=True)
                staging_file.flush()
                os.fsync(staging_file.fileno())
            try:
                os.link(staging, path)  # échoue si path existe : pas d'écrasement
                return True
            except FileExistsError:
                return False
            except OSError:  # système de fichiers sans lien dur
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
                os.close(descriptor)
                os.replace(staging, path)
                return True
        finally:
            if os.path.exists(staging):
                os.unlink(staging)


def _meta(record: dict, name: str) -> str:
    """Champ d'index commun aux enregistrements llm_call (à plat) et ReplayModel (sous « config »)."""
    request = record.get("request") or {}
    value = request.get(name) or (request.get("config") or {}).get(name)
    return str(value) if value is not None else "inconnu"


class DynamoS3Store:
    """Index DynamoDB (écriture conditionnelle ``attribute_not_exists``) + corps dans S3 versionné
    (Object Lock recommandé). Le bucket et la table sont créés hors de ce code (IaC)."""

    def __init__(self, table: str, bucket: str, prefix: str = "llm-replay/", region: str = "us-east-1"):
        import boto3

        self.ddb = boto3.client("dynamodb", region_name=region)
        self.s3 = boto3.client("s3", region_name=region)
        self.table, self.bucket, self.prefix = table, bucket, prefix

    def get(self, key: str) -> dict | None:
        item = self.ddb.get_item(TableName=self.table, Key={"pk": {"S": key}}, ConsistentRead=True).get("Item")
        if not item:
            return None
        stored = self.s3.get_object(Bucket=self.bucket, Key=item["s3_key"]["S"], VersionId=item["s3_version"]["S"])
        return json.loads(stored["Body"].read())

    def put_once(self, key: str, record: dict) -> bool:
        if self.get(key) is not None:
            return False
        s3_key = f"{self.prefix}{key[:2]}/{key}.json"
        put = self.s3.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            ContentType="application/json",
            Body=json.dumps(record, ensure_ascii=False, sort_keys=True).encode(),
        )
        try:
            self.ddb.put_item(
                TableName=self.table,
                ConditionExpression="attribute_not_exists(pk)",
                Item={
                    "pk": {"S": key},
                    "s3_key": {"S": s3_key},
                    "s3_version": {"S": put.get("VersionId", "null")},
                    "created_utc": {"S": record["created_utc"]},
                    "model_id": {"S": _meta(record, "model_id")},
                    "node_id": {"S": _meta(record, "node_id")},
                },
            )
            return True
        except self.ddb.exceptions.ConditionalCheckFailedException:
            return False


# --------------------------------------------------------------------------- transport Bedrock

Transport = Callable[[dict], dict]


def converse_kwargs(request: LLMRequest) -> dict:
    kwargs: dict[str, Any] = {
        "modelId": request.model_id,
        "messages": list(request.messages),
        "inferenceConfig": {"maxTokens": request.max_tokens},
    }
    if request.system:
        kwargs["system"] = [{"text": request.system}]
    output_config: dict[str, Any] = {}
    if request.output_model is not None:
        schema = json.dumps(request.schema(), ensure_ascii=False)
        output_config["textFormat"] = {
            "type": "json_schema",
            "structure": {"jsonSchema": {"name": request.output_model.__name__, "schema": schema}},
        }
    if request.effort:
        output_config["effort"] = request.effort
    if output_config:
        kwargs["outputConfig"] = output_config
    if request.guardrail:
        kwargs["guardrailConfig"] = {
            "guardrailIdentifier": request.guardrail[0],
            "guardrailVersion": request.guardrail[1],
        }
    return kwargs


def bedrock_transport(region: str = "us-east-1") -> Transport:
    """bedrock-runtime Converse (couvert par le model invocation logging, contrairement à Mantle)."""
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(read_timeout=300, retries={"max_attempts": 3, "mode": "adaptive"}),
    )
    return lambda kwargs: client.converse(**kwargs)


def _text(response: dict) -> str:
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    return "".join(block.get("text", "") for block in blocks if "text" in block)


# --------------------------------------------------------------------------- appel


@dataclass
class LLMResult:
    key: str
    text: str
    parsed: Any
    replayed: bool
    record: dict = field(repr=False)


def resolve_mode(mode: Mode | None) -> Mode:
    """Mode demandé, sinon ALPHAFORGE_LLM_MODE, sinon « record »."""
    resolved = mode or os.environ.get("ALPHAFORGE_LLM_MODE", "record")
    if resolved not in ("live", "record", "replay"):
        raise ValueError(f"mode inconnu : {resolved}")
    return resolved  # type: ignore[return-value]


def _annotate_request(span, request: LLMRequest) -> None:
    span.set_attribute("gen_ai.operation.name", "chat")
    span.set_attribute("gen_ai.system", "aws.bedrock")
    span.set_attribute("gen_ai.request.model", request.model_id)
    span.set_attribute("gen_ai.request.max_tokens", request.max_tokens)
    for name, value in (
        ("alphaforge.node_id", request.node_id),
        ("alphaforge.round", request.round),
        ("alphaforge.effort", request.effort),
        ("alphaforge.replay.key", request.key()),
        ("alphaforge.data_version", request.data_version),
        ("alphaforge.policy_version", request.policy_version),
        ("aws.bedrock.guardrail.version", request.guardrail[1] if request.guardrail else None),
    ):
        if value is not None:
            span.set_attribute(name, value)


def _annotate_result(span, result: LLMResult) -> None:
    span.set_attribute("alphaforge.replay.replayed", result.replayed)
    attempts = result.record.get("attempts") or []
    last = (attempts or [{}])[-1]
    usage = last.get("usage") or {}
    if usage:
        span.set_attribute("gen_ai.usage.input_tokens", usage.get("inputTokens", 0))
        span.set_attribute("gen_ai.usage.output_tokens", usage.get("outputTokens", 0))
    if last.get("stop_reason"):
        span.set_attribute("gen_ai.response.finish_reasons", [last["stop_reason"]])
    span.set_attribute("alphaforge.attempts", len(attempts))


def llm_call(
    request: LLMRequest,
    store: Store,
    mode: Mode | None = None,
    transport: Transport | None = None,
    max_attempts: int = 2,
) -> LLMResult:
    """Un appel LLM déterministe au sens « rejouable » : même requête → même réponse en replay.
    Tracé par un span aux conventions OpenTelemetry GenAI (gen_ai.*) + attributs alphaforge.*."""
    from ..observability.telemetry import log_event, tracer

    with tracer().start_as_current_span(f"chat {request.model_id}") as span:
        _annotate_request(span, request)
        result = _llm_call(request, store, mode, transport, max_attempts)
        _annotate_result(span, result)
        log_event(
            "llm.call",
            node_id=request.node_id,
            round=request.round,
            model=request.model_id,
            replayed=result.replayed,
            key=result.key,
            attempts=len(result.record.get("attempts") or []),
        )
        return result


def _parsed(request: LLMRequest, record: dict) -> Any:
    return request.output_model.model_validate(record["parsed"]) if request.output_model else record["parsed"]


def _replayed(request: LLMRequest, store: Store, mode: Mode, key: str) -> LLMResult | None:
    """Réponse déjà enregistrée (modes replay et record) ; en replay, une clé absente lève ``ReplayMissError``."""
    if mode not in ("replay", "record"):
        return None
    record = store.get(key)
    if record is not None:
        parsed = _parsed(request, record)
        return LLMResult(key, record["text"], parsed, True, record)
    if mode == "replay":
        raise ReplayMissError(f"aucune réponse enregistrée pour {request.node_id}/tour {request.round} ({key[:12]})")
    return None


def _converse_request(request: LLMRequest, key: str) -> dict:
    kwargs = converse_kwargs(request)
    kwargs["requestMetadata"] = {
        "alphaforge_node": request.node_id[:256],
        "alphaforge_round": str(request.round),
        "alphaforge_key": key[:32],
    }
    return kwargs


class _Reply(NamedTuple):
    response: dict
    text: str
    stop: str | None


def _call_once(transport: Transport, kwargs: dict, number: int) -> tuple[_Reply, dict]:
    """Un appel au modèle, et la tentative telle qu'elle est enregistrée."""
    started = time.perf_counter()
    response = transport(kwargs)
    text = _text(response)
    stop = response.get("stopReason")
    attempt = {
        "attempt": number,
        "stop_reason": stop,
        "latency_s": round(time.perf_counter() - started, 3),
        "usage": response.get("usage"),
        "metrics": response.get("metrics"),
    }
    return _Reply(response, text, stop), attempt


def _validated(request: LLMRequest, reply: _Reply) -> Any:
    """Sortie conforme au schéma (forme JSON), ou le texte sans schéma ; ValueError si le modèle n'a pas fini."""
    if reply.stop not in ("end_turn", "stop_sequence"):
        raise ValueError(f"stopReason={reply.stop}")
    return (
        request.output_model.model_validate_json(reply.text).model_dump(mode="json")
        if request.output_model
        else reply.text
    )


def _new_record(request: LLMRequest, key: str, reply: _Reply, parsed: Any, attempts: list[dict]) -> dict:
    return {
        "key": key,
        "created_utc": datetime.now(UTC).isoformat(),
        "request": request.canonical(),
        "text": reply.text,
        "parsed": parsed,
        "stop_reason": reply.stop,
        "attempts": attempts,
        "response_model": reply.response.get("ResponseMetadata", {})
        .get("HTTPHeaders", {})
        .get("x-amzn-bedrock-model-id"),
    }


def _published(store: Store, mode: Mode, key: str, record: dict) -> dict:
    """En mode record, publie la réponse (écriture unique)."""
    if mode == "record" and not store.put_once(key, record):  # course : quelqu'un a écrit avant → on rejoue la sienne
        return store.get(key)
    return record


def _llm_call(
    request: LLMRequest, store: Store, mode: Mode | None, transport: Transport | None, max_attempts: int
) -> LLMResult:
    mode = resolve_mode(mode)
    key = request.key()
    replayed = _replayed(request, store, mode, key)
    if replayed is not None:
        return replayed
    transport = transport or bedrock_transport()
    kwargs = _converse_request(request, key)
    attempts: list[dict] = []
    for number in range(1, max_attempts + 1):
        reply, attempt = _call_once(transport, kwargs, number)
        attempts.append(attempt)
        try:
            parsed = _validated(request, reply)
        except (ValidationError, ValueError) as exc:
            attempt["error"] = str(exc)[:500]
            continue
        record = _published(store, mode, key, _new_record(request, key, reply, parsed, attempts))
        output = _parsed(request, record)
        return LLMResult(key, record["text"], output, False, record)
    raise LLMOutputError(
        f"{request.node_id}/tour {request.round} : sortie invalide après {max_attempts} essais : "
        f"{[attempt.get('error') for attempt in attempts]}"
    )
