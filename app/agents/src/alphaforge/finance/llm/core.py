"""Appels LLM enregistrés et rejouables — la couche de déterminisme d'AlphaForge AI.

Claude 5.x sur Bedrock n'a ni ``temperature`` ni ``seed``, et sa pensée est toujours active :
une même requête peut donner deux sorties différentes. Le seul moyen de reproduire une
décision au bit près est d'**enregistrer** chaque réponse puis de la **rejouer**.

Modes (variable ALPHAFORGE_LLM_MODE ou argument) :
- ``live``   : appel Bedrock, réponse validée, PAS enregistrée ;
- ``record`` : appel Bedrock, réponse validée et enregistrée (écriture unique, jamais écrasée) ;
- ``replay`` : lecture seule ; une clé absente lève ``ReplayMiss`` (aucun appel silencieux).

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
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError

Mode = Literal["live", "record", "replay"]
KEY_VERSION = "1"


class ReplayMiss(KeyError):
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
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        return node
    return walk(json.loads(json.dumps(schema)))

@dataclass(frozen=True)
class LLMRequest:
    model_id: str                                   # ex. us.anthropic.claude-opus-5-5 (bedrock-runtime)
    messages: tuple[dict, ...]                      # format Converse
    system: str | None = None
    output_model: type[BaseModel] | None = None     # sortie structurée native (JSON Schema)
    effort: str | None = None                       # low | medium | high | xhigh | max
    max_tokens: int = 4000
    prompt_ref: str | None = None                   # ARN Prompt Management + version (traçabilité)
    guardrail: tuple[str, str] | None = None        # (identifiant, version NUMÉROTÉE, jamais DRAFT)
    node_id: str = "default"                        # nœud du graphe (lentille, avocat, juge…)
    round: int = 0                                  # tour du débat
    data_version: str | None = None
    policy_version: str | None = None
    extra: tuple[tuple[str, str], ...] = ()         # autres versions à figer (clé, valeur)

    def __post_init__(self):
        if self.guardrail and self.guardrail[1].upper() == "DRAFT":
            raise ValueError("guardrail DRAFT interdit : utiliser une version numérotée")

    def schema(self) -> dict | None:
        return strict_schema(self.output_model.model_json_schema()) if self.output_model else None

    def canonical(self) -> dict:
        return {"key_version": KEY_VERSION, "model_id": self.model_id, "system": self.system,
                "messages": list(self.messages), "output_schema": self.schema(), "effort": self.effort,
                "max_tokens": self.max_tokens, "prompt_ref": self.prompt_ref,
                "guardrail": list(self.guardrail) if self.guardrail else None, "node_id": self.node_id,
                "round": self.round, "data_version": self.data_version,
                "policy_version": self.policy_version, "extra": [list(x) for x in self.extra]}

    def key(self) -> str:
        blob = json.dumps(self.canonical(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- stockage

class Store(Protocol):
    def get(self, key: str) -> dict | None: ...
    def put_once(self, key: str, record: dict) -> bool: ...   # False si la clé existe déjà


class FileStore:
    """Un fichier JSON par clé ; création exclusive, aucune réécriture (dev, tests, démo hors ligne)."""

    def __init__(self, root: str | os.PathLike):
        self.root = os.fspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, key: str) -> str:
        return os.path.join(self.root, key[:2], f"{key}.json")

    def get(self, key: str) -> dict | None:
        try:
            with open(self._path(key), encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def put_once(self, key: str, record: dict) -> bool:
        """Écrit dans un fichier temporaire, puis publie par lien dur (atomique, sans écrasement) :
        un lecteur ne voit jamais un fichier à moitié écrit."""
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            return False
        tmp = f"{path}.{os.getpid()}.{time.monotonic_ns()}.tmp"
        try:
            with open(tmp, "x", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=1, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(tmp, path)               # échoue si path existe : pas d'écrasement
                return True
            except FileExistsError:
                return False
            except OSError:                      # système de fichiers sans lien dur
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
                os.close(fd)
                os.replace(tmp, path)
                return True
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _meta(record: dict, field: str) -> str:
    """Champ d'index commun aux enregistrements llm_call (à plat) et ReplayModel (sous « config »)."""
    req = record.get("request") or {}
    val = req.get(field) or (req.get("config") or {}).get(field)
    return str(val) if val is not None else "inconnu"


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
        obj = self.s3.get_object(Bucket=self.bucket, Key=item["s3_key"]["S"], VersionId=item["s3_version"]["S"])
        return json.loads(obj["Body"].read())

    def put_once(self, key: str, record: dict) -> bool:
        if self.get(key) is not None:
            return False
        s3_key = f"{self.prefix}{key[:2]}/{key}.json"
        put = self.s3.put_object(Bucket=self.bucket, Key=s3_key, ContentType="application/json",
                                 Body=json.dumps(record, ensure_ascii=False, sort_keys=True).encode())
        try:
            self.ddb.put_item(TableName=self.table, ConditionExpression="attribute_not_exists(pk)",
                              Item={"pk": {"S": key}, "s3_key": {"S": s3_key},
                                    "s3_version": {"S": put.get("VersionId", "null")},
                                    "created_utc": {"S": record["created_utc"]},
                                    "model_id": {"S": _meta(record, "model_id")},
                                    "node_id": {"S": _meta(record, "node_id")}})
            return True
        except self.ddb.exceptions.ConditionalCheckFailedException:
            return False


# --------------------------------------------------------------------------- transport Bedrock

Transport = Callable[[dict], dict]


def converse_kwargs(req: LLMRequest) -> dict:
    kw: dict[str, Any] = {"modelId": req.model_id, "messages": list(req.messages),
                          "inferenceConfig": {"maxTokens": req.max_tokens}}
    if req.system:
        kw["system"] = [{"text": req.system}]
    out: dict[str, Any] = {}
    if req.output_model is not None:
        out["textFormat"] = {"type": "json_schema", "structure": {"jsonSchema": {
            "name": req.output_model.__name__, "schema": json.dumps(req.schema(), ensure_ascii=False)}}}
    if req.effort:
        out["effort"] = req.effort
    if out:
        kw["outputConfig"] = out
    if req.guardrail:
        kw["guardrailConfig"] = {"guardrailIdentifier": req.guardrail[0],
                                 "guardrailVersion": req.guardrail[1]}
    return kw


def bedrock_transport(region: str = "us-east-1") -> Transport:
    """bedrock-runtime Converse (couvert par le model invocation logging, contrairement à Mantle)."""
    import boto3
    from botocore.config import Config
    client = boto3.client("bedrock-runtime", region_name=region,
                          config=Config(read_timeout=300, retries={"max_attempts": 3, "mode": "adaptive"}))
    return lambda kw: client.converse(**kw)


def _text(resp: dict) -> str:
    blocks = resp.get("output", {}).get("message", {}).get("content", [])
    return "".join(b.get("text", "") for b in blocks if "text" in b)


# --------------------------------------------------------------------------- appel

@dataclass
class LLMResult:
    key: str
    text: str
    parsed: Any
    replayed: bool
    record: dict = field(repr=False)


def _mode(mode: Mode | None) -> Mode:
    m = mode or os.environ.get("ALPHAFORGE_LLM_MODE", "record")
    if m not in ("live", "record", "replay"):
        raise ValueError(f"mode inconnu : {m}")
    return m  # type: ignore[return-value]


def llm_call(req: LLMRequest, store: Store, mode: Mode | None = None,
             transport: Transport | None = None, max_attempts: int = 2) -> LLMResult:
    """Un appel LLM déterministe au sens « rejouable » : même requête → même réponse en replay.
    Tracé par un span aux conventions OpenTelemetry GenAI (gen_ai.*) + attributs alphaforge.*."""
    from ..observability.telemetry import log_event, tracer
    with tracer().start_as_current_span(f"chat {req.model_id}") as sp:
        sp.set_attribute("gen_ai.operation.name", "chat")
        sp.set_attribute("gen_ai.system", "aws.bedrock")
        sp.set_attribute("gen_ai.request.model", req.model_id)
        sp.set_attribute("gen_ai.request.max_tokens", req.max_tokens)
        for k, v in (("alphaforge.node_id", req.node_id), ("alphaforge.round", req.round),
                     ("alphaforge.effort", req.effort), ("alphaforge.replay.key", req.key()),
                     ("alphaforge.data_version", req.data_version), ("alphaforge.policy_version", req.policy_version),
                     ("aws.bedrock.guardrail.version", req.guardrail[1] if req.guardrail else None)):
            if v is not None:
                sp.set_attribute(k, v)
        res = _llm_call(req, store, mode, transport, max_attempts)
        sp.set_attribute("alphaforge.replay.replayed", res.replayed)
        last = (res.record.get("attempts") or [{}])[-1]
        usage = last.get("usage") or {}
        if usage:
            sp.set_attribute("gen_ai.usage.input_tokens", usage.get("inputTokens", 0))
            sp.set_attribute("gen_ai.usage.output_tokens", usage.get("outputTokens", 0))
        if last.get("stop_reason"):
            sp.set_attribute("gen_ai.response.finish_reasons", [last["stop_reason"]])
        sp.set_attribute("alphaforge.attempts", len(res.record.get("attempts") or []))
        log_event("llm.call", node_id=req.node_id, round=req.round, model=req.model_id, replayed=res.replayed,
                  key=res.key, attempts=len(res.record.get("attempts") or []))
        return res


def _llm_call(req: LLMRequest, store: Store, mode: Mode | None, transport: Transport | None,
              max_attempts: int) -> LLMResult:
    mode = _mode(mode)
    key = req.key()
    if mode in ("replay", "record"):
        rec = store.get(key)
        if rec is not None:
            parsed = req.output_model.model_validate(rec["parsed"]) if req.output_model else rec["parsed"]
            return LLMResult(key, rec["text"], parsed, True, rec)
        if mode == "replay":
            raise ReplayMiss(f"aucune réponse enregistrée pour {req.node_id}/tour {req.round} ({key[:12]})")

    transport = transport or bedrock_transport()
    kw = converse_kwargs(req)
    kw["requestMetadata"] = {"alphaforge_node": req.node_id[:256], "alphaforge_round": str(req.round),
                             "alphaforge_key": key[:32]}
    attempts = []
    for i in range(max_attempts):
        t0 = time.perf_counter()
        resp = transport(kw)
        text = _text(resp)
        stop = resp.get("stopReason")
        att = {"attempt": i + 1, "stop_reason": stop, "latency_s": round(time.perf_counter() - t0, 3),
               "usage": resp.get("usage"), "metrics": resp.get("metrics")}
        try:
            if stop not in ("end_turn", "stop_sequence"):
                raise ValueError(f"stopReason={stop}")
            parsed = req.output_model.model_validate_json(text).model_dump(mode="json") if req.output_model else text
        except (ValidationError, ValueError) as exc:
            att["error"] = str(exc)[:500]
            attempts.append(att)
            continue
        attempts.append(att)
        rec = {"key": key, "created_utc": datetime.now(UTC).isoformat(), "request": req.canonical(),
               "text": text, "parsed": parsed, "stop_reason": stop, "attempts": attempts,
               "response_model": resp.get("ResponseMetadata", {}).get("HTTPHeaders", {}).get("x-amzn-bedrock-model-id")}
        if mode == "record":
            if not store.put_once(key, rec):          # course : quelqu'un a écrit avant → on rejoue la sienne
                rec = store.get(key)
        out = req.output_model.model_validate(rec["parsed"]) if req.output_model else rec["parsed"]
        return LLMResult(key, rec["text"], out, False, rec)
    raise LLMOutputError(f"{req.node_id}/tour {req.round} : sortie invalide après {max_attempts} essais : "
                         f"{[a.get('error') for a in attempts]}")
