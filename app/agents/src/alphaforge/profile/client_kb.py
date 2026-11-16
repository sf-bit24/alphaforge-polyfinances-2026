"""Knowledge Base Bedrock de chaque client : un index de recherche construit à partir de sa base OKF.

L'OKF reste la source de vérité : le code lit toujours les valeurs exactes dans ``clients/<id>/``. La Knowledge Base
du client sert seulement à retrouver un passage (une décision passée, une note d'A1, une réponse au journal).
Isolation par silo : une Knowledge Base et un index S3 Vectors par client, aucun filtre de métadonnées à oublier.

État dans ``clients/<id>/kb.json``, écrit par le code seul (A1 n'écrit que des notes ``.md``), avec une précondition
sur l'ETag : deux requêtes simultanées ne s'écrasent pas, la seconde relit l'état et y reporte ses changements.

- ``creating`` : le runtime ``profile`` crée l'index ``client-<id>`` dans le bucket de vecteurs des clients, puis la
  Knowledge Base (``clientToken`` tiré du client : deux requêtes simultanées obtiennent la même), puis, quand
  ``GetKnowledgeBase`` la dit ``ACTIVE``, sa source de données ``CUSTOM``;
- ``active`` : chaque document passe par l'ingestion directe (``IngestKnowledgeBaseDocuments``, identifiant du
  document = clé OKF, une réingestion remplace le document); une note retirée sort par
  ``DeleteKnowledgeBaseDocuments``;
- ``quota`` (``ServiceQuotaExceededException`` : 100 Knowledge Bases par compte, non ajustable) et ``failed`` :
  nouvel essai après ``retry_at``;
- ``disabled`` : magasin local ou variables absentes; rien n'est créé ni écrit, le runtime fait ce qu'il faisait.

Pas de ``StartIngestionJob`` : 0,1 requête par seconde pour le compte, déjà prise par la collecte.

Un seul point d'accroche voit passer les écritures : ``IndexingStore`` enveloppe le magasin et note chaque document
``.md`` d'une base client (jamais ``traces/``, jamais un ``.json``). À la fin de l'action, ``sync`` fait avancer la
création (une lecture ``GetKnowledgeBase`` tant que la base n'est pas active, rien ensuite), puis envoie les documents
notés et ceux en attente par lots de ``BATCH_SIZE``. Base pas encore active, appel limité : les clés restent en attente
pour le rapprochement suivant. Aucune erreur de Knowledge Base ne fait échouer l'action de l'investisseur : elle va
dans la trace et dans ``kb.json``.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from functools import partial
from typing import Any

import boto3
from botocore.config import Config

from .. import clock, okf
from ..config import Settings
from ..store import ConflictError, ObjectInfo, Store, StoredObject
from ..trace import Trace
from .state import is_client_id

logger = logging.getLogger("alphaforge.client_kb")

SCHEMA = "alphaforge.client_kb/1"
STATUSES = ("disabled", "creating", "active", "failed", "quota")
# Documents par appel IngestKnowledgeBaseDocuments ou DeleteKnowledgeBaseDocuments : le quota du service en permet
# 25, mais le modèle du client botocore (1.44) en refuse plus de 10 avant l'envoi.
BATCH_SIZE = 10
MAX_PENDING = 200
MAX_ERRORS = 20
MAX_TEXT_CHARS = 1_000_000
EXCERPT_CHARS = 700
SAVE_ATTEMPTS = 3
RETRY_AFTER = {"failed": timedelta(minutes=30), "quota": timedelta(hours=1)}
SCOPE_TAG = "alphaforge:scope"
CLIENT_TAG = "alphaforge:client_id"
PREFIX_TAG = "alphaforge:prefix"
DATA_SOURCE_NAME = "client-okf"
# Mêmes réglages que la base générale (bedrock.tf) : passages de 400 jetons, 15 % de recouvrement.
CHUNKING = {
    "chunkingStrategy": "FIXED_SIZE",
    "fixedSizeChunkingConfiguration": {"maxTokens": 400, "overlapPercentage": 15},
}
# Bedrock range le texte des passages et leurs métadonnées dans ces clés : filtrables, elles dépasseraient 2 Ko.
NON_FILTERABLE_KEYS = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
TRANSIENT_CODES = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "ServiceUnavailableException",
        "InternalServerException",
        "RequestTimeoutException",
        "EndpointConnectionError",
        "ConnectTimeoutError",
        "ReadTimeoutError",
        "ConnectionClosedError",
    }
)
_CLIENT_DOC = re.compile(r"^clients/([0-9a-f-]{36})/(.+\.md)$")
# Champs de ``kb.json`` que la création fait avancer (les ensembles ``pending`` et ``indexed`` sont fusionnés à part).
_LIFECYCLE_FIELDS = (
    "status",
    "index_arn",
    "knowledge_base_id",
    "knowledge_base_arn",
    "data_source_id",
    "active_at",
    "retry_at",
    "error",
)


def state_key(client_id: str) -> str:
    return f"clients/{client_id}/kb.json"


def index_name(client_id: str) -> str:
    return f"client-{client_id}"


def indexed_client(key: str) -> str | None:
    """Client dont ``key`` est un document à indexer (``.md`` de sa base, hors ``traces/``), sinon ``None``."""
    match = _CLIENT_DOC.match(key)
    if match is None or not is_client_id(match.group(1)) or match.group(2).startswith("traces/"):
        return None
    return match.group(1)


def error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = (response.get("Error") or {}).get("Code")
        if code:
            return str(code)
    return type(exc).__name__


def status_view(state: dict[str, Any] | None, *, enabled: bool = True) -> dict[str, Any]:
    """``client_kb`` des réponses (CONTRACTS.md 3.3) : statut, identifiant, documents indexés, clés en attente."""
    if not enabled:
        return {"status": "disabled", "knowledge_base_id": None, "documents": 0, "pending": 0}
    if state is None:
        return {"status": "failed", "knowledge_base_id": None, "documents": 0, "pending": 0}
    return {
        "status": state.get("status") or "failed",
        "knowledge_base_id": state.get("knowledge_base_id"),
        "documents": len(state.get("indexed") or []),
        "pending": len(state.get("pending") or []),
    }


def _add_step(trace: Trace | None, title: tuple[str, str], detail: str | None, outputs: dict[str, Any]) -> None:
    if trace is not None:
        trace.add("storage", "store", trace.t(*title), detail, outputs=outputs)


def _chunks(items: list[Any], size: int) -> Iterator[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _later(delay: timedelta) -> str:
    return clock.iso(clock.utcnow() + delay)


def _due(retry_at: Any) -> bool:
    moment = clock.parse_datetime(retry_at) if isinstance(retry_at, str) else None
    return moment is None or moment <= clock.utcnow()


# ---------------------------------------------------------------------- réglages et clients AWS
@dataclass(frozen=True)
class ClientKbConfig:
    """Réglages des Knowledge Bases des clients, posés par Terraform (client_kb.tf) sur profile et portfolio."""

    region: str
    prefix: str
    vector_bucket: str
    role_arn: str
    embedding_model_arn: str
    dimensions: int

    @classmethod
    def from_settings(cls, settings: Settings) -> ClientKbConfig | None:
        """``None`` (désactivé) avec le magasin local ou sans l'une des variables ``ALPHAFORGE_CLIENT_KB_*``."""
        values = (
            settings.client_kb_prefix,
            settings.client_kb_vector_bucket,
            settings.client_kb_role_arn,
            settings.client_kb_embedding_model_arn,
            settings.client_kb_embedding_dimensions,
        )
        if settings.store != "s3" or not all(values):
            return None
        return cls(
            region=settings.region,
            prefix=str(settings.client_kb_prefix),
            vector_bucket=str(settings.client_kb_vector_bucket),
            role_arn=str(settings.client_kb_role_arn),
            embedding_model_arn=str(settings.client_kb_embedding_model_arn),
            dimensions=int(settings.client_kb_embedding_dimensions or 0),
        )

    def kb_name(self, client_id: str) -> str:
        return f"{self.prefix}-client-{client_id}"

    def token(self, kind: str, client_id: str) -> str:
        """``clientToken`` idempotent : le même client donne toujours la même Knowledge Base et la même source."""
        return f"{self.prefix}-{kind}-{client_id}"[:256]

    def tags(self, client_id: str) -> dict[str, str]:
        return {SCOPE_TAG: "client", CLIENT_TAG: client_id, PREFIX_TAG: self.prefix}


@dataclass
class AwsClients:
    agent: Any  # bedrock-agent : création, lecture et ingestion
    runtime: Any  # bedrock-agent-runtime : Retrieve
    vectors: Any  # s3vectors : index du client

    @classmethod
    def for_region(cls, region: str) -> AwsClients:
        # Délais courts et peu de reprises : la Knowledge Base ne doit jamais retenir l'investisseur.
        config = Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 3, "mode": "standard"})
        return cls(
            agent=boto3.client("bedrock-agent", region_name=region, config=config),
            runtime=boto3.client("bedrock-agent-runtime", region_name=region, config=config),
            vectors=boto3.client("s3vectors", region_name=region, config=config),
        )


# ---------------------------------------------------------------------- documents
def document_text(text: str) -> tuple[str, dict[str, Any], bool]:
    """Texte indexé (titre, description, corps Markdown), métadonnées et vrai pour une note retirée."""
    try:
        doc = okf.parse(text)
    except okf.OkfError:
        return text.strip()[:MAX_TEXT_CHARS], {}, False
    summary = okf.summary(doc)
    head = [str(part).strip() for part in (summary["title"], summary["description"]) if part]
    body = "\n".join(head) + "\n\n" + doc.body.strip()
    return body.strip()[:MAX_TEXT_CHARS], summary, doc.data.get("retired") is True


def _attribute(key: str, value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str) or not value:
        return None
    return {"key": key, "value": {"type": "STRING", "stringValue": value[:2048]}}


def ingest_payload(key: str, text: str, summary: dict[str, Any], client_id: str) -> dict[str, Any]:
    """Document ``CUSTOM`` en ligne : identifiant = clé OKF, métadonnées ``type``, ``updated_at``, ``client_id``."""
    attributes = [
        _attribute("type", summary.get("type")),
        _attribute("updated_at", summary.get("generated_at")),
        _attribute("client_id", client_id),
    ]
    return {
        "content": {
            "dataSourceType": "CUSTOM",
            "custom": {
                "customDocumentIdentifier": {"id": key},
                "sourceType": "IN_LINE",
                "inlineContent": {"type": "TEXT", "textContent": {"data": text or key}},
            },
        },
        "metadata": {"type": "IN_LINE_ATTRIBUTE", "inlineAttributes": [item for item in attributes if item]},
    }


def _identifier(key: str) -> dict[str, Any]:
    return {"dataSourceType": "CUSTOM", "custom": {"id": key}}


@dataclass
class SendOutcome:
    """Ce qu'un rapprochement a fait des documents : reporté tel quel dans ``kb.json``, même après un conflit."""

    sent: set[str] = field(default_factory=set)
    removed: set[str] = field(default_factory=set)
    waiting: set[str] = field(default_factory=set)
    done: set[str] = field(default_factory=set)
    errors: dict[str, str] = field(default_factory=dict)

    def apply(self, state: dict[str, Any]) -> None:
        pending = (set(state.get("pending") or []) | self.waiting) - self.done
        indexed = (set(state.get("indexed") or []) | self.sent) - self.removed
        state["pending"] = sorted(pending)[:MAX_PENDING]
        state["indexed"] = sorted(indexed)
        if self.errors:
            errors = {**(state.get("document_errors") or {}), **self.errors}
            state["document_errors"] = dict(sorted(errors.items())[-MAX_ERRORS:])
        if self.sent or self.removed:
            state["ingested_at"] = clock.iso()


@dataclass
class Prepared:
    """Documents à envoyer et à retirer, tirés des clés notées et en attente."""

    documents: list[dict[str, Any]] = field(default_factory=list)
    removals: list[str] = field(default_factory=list)
    dropped: set[str] = field(default_factory=set)


class IndexingStore(Store):
    """Enveloppe du magasin : chaque document ``.md`` écrit dans une base client est noté pour sa Knowledge Base."""

    def __init__(self, inner: Store, kbs: ClientKnowledgeBases):
        self.inner = inner
        self.kbs = kbs
        self.name = inner.name

    def __getattr__(self, name: str) -> Any:
        # Attributs propres au magasin enveloppé (``bucket`` de S3Store, lu par OkfMarketStore).
        return getattr(self.inner, name)

    def get(self, key: str) -> StoredObject | None:
        return self.inner.get(key)

    def exists(self, key: str) -> bool:
        return self.inner.exists(key)

    def list(self, prefix: str, *, limit: int = 1000) -> list[ObjectInfo]:
        return self.inner.list(prefix, limit=limit)

    def put(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str = "text/markdown; charset=utf-8",
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> str:
        etag = self.inner.put(key, body, content_type=content_type, if_match=if_match, if_none_match=if_none_match)
        self.kbs.note_write(key, body)
        return etag


# ---------------------------------------------------------------------- service
class ClientKnowledgeBases:
    """Knowledge Base de chaque client : création (runtime ``profile`` seulement), ingestion et recherche."""

    def __init__(
        self,
        config: ClientKbConfig | None,
        store: Store,
        *,
        can_create: bool,
        clients: AwsClients | None = None,
    ):
        self.config = config
        self.store = store
        self.can_create = can_create
        self._clients = clients
        self._lock = threading.Lock()
        self._written: dict[str, dict[str, bytes]] = {}

    @classmethod
    def from_settings(cls, settings: Settings, store: Store, *, can_create: bool) -> ClientKnowledgeBases:
        return cls(ClientKbConfig.from_settings(settings), store, can_create=can_create)

    @property
    def enabled(self) -> bool:
        return self.config is not None

    @property
    def aws(self) -> AwsClients:
        if self._clients is None:
            self._clients = AwsClients.for_region(self.config.region)
        return self._clients

    def wrap(self, store: Store) -> Store:
        """Magasin à donner au service : enveloppé quand la Knowledge Base des clients est configurée."""
        return IndexingStore(store, self) if self.enabled else store

    # ------------------------------------------------------------------ écritures notées
    def note_write(self, key: str, body: bytes) -> None:
        client_id = indexed_client(key)
        if client_id is None:
            return
        with self._lock:
            self._written.setdefault(client_id, {})[key] = body

    def _take(self, client_id: str) -> dict[str, bytes]:
        with self._lock:
            return self._written.pop(client_id, {})

    def _restore(self, client_id: str, written: dict[str, bytes]) -> None:
        """Rapprochement interrompu : les documents notés iront au suivant (une écriture plus récente gagne)."""
        with self._lock:
            noted = self._written.setdefault(client_id, {})
            for key, body in written.items():
                noted.setdefault(key, body)

    def noted_clients(self) -> list[str]:
        with self._lock:
            return sorted(self._written)

    # ------------------------------------------------------------------ rapprochement
    def sync(self, client_id: str, trace: Trace | None, *, create: bool = False) -> dict[str, Any] | None:
        """Rapprochement de fin d'action : fait avancer la création (``create`` et runtime ``profile``), envoie les
        documents notés et en attente. Rend ``client_kb`` (``status_view``), ou ``None`` sans base ni création."""
        written = self._take(client_id)
        if not self.enabled:
            return status_view(None, enabled=False)
        try:
            state = self._sync(client_id, written, trace, create=create and self.can_create)
        except Exception as exc:  # jamais d'erreur pour l'investisseur : la trace et le journal la gardent
            logger.exception("client knowledge base sync failed")
            self._restore(client_id, written)
            _add_step(
                trace,
                ("Knowledge Base du client : erreur", "Client knowledge base: error"),
                error_code(exc),
                {"error": error_code(exc)},
            )
            return status_view(None) if create else None
        if state is None:
            return None
        return status_view(state)

    def sync_noted(self, trace: Trace | None = None) -> None:
        """Rapproche chaque client dont un document a été écrit (tâches de fond du runtime ``portfolio``)."""
        for client_id in self.noted_clients():
            self.sync(client_id, trace, create=False)

    def _read(self, client_id: str) -> tuple[dict[str, Any] | None, str | None]:
        stored = self.store.get(state_key(client_id))
        if stored is None:
            return None, None
        return json.loads(stored.text), stored.etag

    def _sync(
        self, client_id: str, written: dict[str, bytes], trace: Trace | None, *, create: bool
    ) -> dict[str, Any] | None:
        state, etag = self._read(client_id)
        if state is None and not create:
            return None
        if state is None:
            state = self._new_state(client_id, written)
        base_status = state.get("status") if etag else None
        before = {name: state.get(name) for name in _LIFECYCLE_FIELDS}
        if self.can_create:
            self._advance(client_id, state, trace)
        outcome = self._send(client_id, state, written, trace)
        fields = {name: state.get(name) for name in _LIFECYCLE_FIELDS if state.get(name) != before[name]}
        if etag is not None and not fields and _unchanged(state, outcome):
            return state
        return self._save(client_id, state, etag, base_status, fields, outcome)

    def _new_state(self, client_id: str, written: dict[str, bytes]) -> dict[str, Any]:
        """État d'une base à créer : toutes les notes déjà écrites du client attendent leur première ingestion."""
        existing = {info.key for info in self.store.list(f"clients/{client_id}/") if indexed_client(info.key)}
        now = clock.iso()
        return {
            "schema": SCHEMA,
            "client_id": client_id,
            "status": "creating",
            "vector_bucket": self.config.vector_bucket,
            "index_name": index_name(client_id),
            "index_arn": None,
            "knowledge_base_name": self.config.kb_name(client_id),
            "knowledge_base_id": None,
            "knowledge_base_arn": None,
            "data_source_id": None,
            "created_at": now,
            "updated_at": now,
            "active_at": None,
            "ingested_at": None,
            "retry_at": None,
            "error": None,
            "pending": sorted(existing - set(written)),
            "indexed": [],
        }

    def _save(  # noqa: PLR0913 - l'état lu, son ETag et ce que le rapprochement y a changé, passés ensemble
        self,
        client_id: str,
        state: dict[str, Any],
        etag: str | None,
        base_status: str | None,
        fields: dict[str, Any],
        outcome: SendOutcome,
    ) -> dict[str, Any]:
        """Écrit ``kb.json`` avec une précondition; après un conflit, reporte les changements sur l'état relu."""
        key = state_key(client_id)
        outcome.apply(state)
        for _ in range(SAVE_ATTEMPTS):
            state["updated_at"] = clock.iso()
            try:
                if etag is None:
                    self.store.put_json(key, state, if_none_match=True)
                else:
                    self.store.put_json(key, state, if_match=etag)
                return state
            except ConflictError:
                fresh, etag = self._read(client_id)
                if fresh is None:
                    continue
                if fresh.get("status") == base_status:
                    fresh.update(fields)
                outcome.apply(fresh)
                state = fresh
        logger.warning("client knowledge base state not saved after %d attempts", SAVE_ATTEMPTS)
        return state

    # ------------------------------------------------------------------ création
    def _advance(self, client_id: str, state: dict[str, Any], trace: Trace | None) -> None:
        """Fait avancer la création d'un pas au plus par étape manquante; une erreur est rangée dans l'état."""
        if state.get("status") in RETRY_AFTER and _due(state.get("retry_at")):
            state.update(status="creating", retry_at=None)
        if state.get("status") != "creating":
            return
        try:
            self._create(client_id, state, trace)
        except Exception as exc:  # erreur AWS ou réseau : reportée, la requête de l'investisseur continue
            self._creation_error(state, exc, trace)

    def _create(self, client_id: str, state: dict[str, Any], trace: Trace | None) -> None:
        """Index, Knowledge Base, puis source de données quand la base est ``ACTIVE``; chaque pas est idempotent."""
        state["error"] = None
        if not state.get("index_arn"):
            state["index_arn"] = self._create_index(client_id)
        kb_status = None
        if not state.get("knowledge_base_id"):
            kb_status = self._create_knowledge_base(client_id, state, trace)
        if kb_status is None:
            found = self.aws.agent.get_knowledge_base(knowledgeBaseId=state["knowledge_base_id"])
            kb_status = found["knowledgeBase"].get("status")
        self._activate(client_id, state, kb_status, trace)

    def _create_index(self, client_id: str) -> str:
        vectors = self.aws.vectors
        try:
            response = vectors.create_index(
                vectorBucketName=self.config.vector_bucket,
                indexName=index_name(client_id),
                dataType="float32",
                dimension=self.config.dimensions,
                distanceMetric="cosine",
                metadataConfiguration={"nonFilterableMetadataKeys": NON_FILTERABLE_KEYS},
            )
            return response["indexArn"]
        except Exception as exc:
            if error_code(exc) != "ConflictException":
                raise
        # Index déjà créé (requête simultanée ou reprise) : on reprend le sien.
        found = vectors.get_index(vectorBucketName=self.config.vector_bucket, indexName=index_name(client_id))
        return found["index"]["indexArn"]

    def _create_knowledge_base(self, client_id: str, state: dict[str, Any], trace: Trace | None) -> str | None:
        config = self.config
        params = {
            "clientToken": config.token("kb", client_id),
            "name": config.kb_name(client_id),
            "description": "Index de recherche de la base OKF d'un client (l'OKF reste la source de verite).",
            "roleArn": config.role_arn,
            "knowledgeBaseConfiguration": {
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": config.embedding_model_arn,
                    "embeddingModelConfiguration": {
                        "bedrockEmbeddingModelConfiguration": {
                            "dimensions": config.dimensions,
                            "embeddingDataType": "FLOAT32",
                        }
                    },
                },
            },
            "storageConfiguration": {"type": "S3_VECTORS", "s3VectorsConfiguration": {"indexArn": state["index_arn"]}},
            "tags": config.tags(client_id),
        }
        try:
            kb = self.aws.agent.create_knowledge_base(**params)["knowledgeBase"]
        except Exception as exc:
            if error_code(exc) != "ConflictException":
                raise
            kb = self._find_knowledge_base(config.kb_name(client_id))
            if kb is None:
                raise
        state["knowledge_base_id"] = kb["knowledgeBaseId"]
        state["knowledge_base_arn"] = kb.get("knowledgeBaseArn")
        _add_step(
            trace,
            ("Knowledge Base du client créée", "Client knowledge base created"),
            kb["knowledgeBaseId"],
            {"knowledge_base_id": kb["knowledgeBaseId"], "index": index_name(client_id), "status": kb.get("status")},
        )
        return kb.get("status")

    def _find_knowledge_base(self, name: str) -> dict[str, Any] | None:
        """Knowledge Base déjà créée sous ce nom (``clientToken`` expiré, par exemple), ou ``None``."""
        pages = self.aws.agent.get_paginator("list_knowledge_bases").paginate()
        for page in pages:
            for summary in page.get("knowledgeBaseSummaries") or []:
                if summary.get("name") == name:
                    found = self.aws.agent.get_knowledge_base(knowledgeBaseId=summary["knowledgeBaseId"])
                    return found["knowledgeBase"]
        return None

    def _activate(self, client_id: str, state: dict[str, Any], kb_status: str | None, trace: Trace | None) -> None:
        """Base ``ACTIVE`` : sa source ``CUSTOM`` est créée et l'état passe à ``active``; ``FAILED`` : ``failed``."""
        if kb_status in ("FAILED", "DELETING", "DELETE_UNSUCCESSFUL"):
            self._fail(state, "failed", f"knowledge_base_{str(kb_status).lower()}", trace)
            return
        if kb_status != "ACTIVE":
            return  # CREATING ou UPDATING : le rapprochement suivant relira l'état
        if not state.get("data_source_id"):
            state["data_source_id"] = self._create_data_source(client_id, state["knowledge_base_id"])
        state.update(status="active", active_at=clock.iso(), retry_at=None)
        _add_step(
            trace,
            ("Knowledge Base du client active", "Client knowledge base active"),
            state["knowledge_base_id"],
            {"data_source_id": state["data_source_id"], "pending": len(state.get("pending") or [])},
        )

    def _create_data_source(self, client_id: str, kb_id: str) -> str:
        agent = self.aws.agent
        try:
            source = agent.create_data_source(
                knowledgeBaseId=kb_id,
                clientToken=self.config.token("ds", client_id),
                name=DATA_SOURCE_NAME,
                description="Documents OKF du client, ingeres un par un (identifiant = cle OKF).",
                dataSourceConfiguration={"type": "CUSTOM"},
                # RETAIN : supprimer la base (scripts/clean-client-kbs.sh) ne touche pas aux vecteurs, qui partent
                # avec l'index; avec DELETE, la suppression échoue si l'index ou le rôle n'existe plus. Un document
                # retiré sort toujours par DeleteKnowledgeBaseDocuments.
                dataDeletionPolicy="RETAIN",
                vectorIngestionConfiguration={"chunkingConfiguration": CHUNKING},
            )
            return source["dataSource"]["dataSourceId"]
        except Exception as exc:
            if error_code(exc) != "ConflictException":
                raise
        for page in agent.get_paginator("list_data_sources").paginate(knowledgeBaseId=kb_id):
            for summary in page.get("dataSourceSummaries") or []:
                if summary.get("name") == DATA_SOURCE_NAME:
                    return summary["dataSourceId"]
        raise LookupError(f"data source {DATA_SOURCE_NAME} not found")

    def _creation_error(self, state: dict[str, Any], exc: Exception, trace: Trace | None) -> None:
        code = error_code(exc)
        if code == "ServiceQuotaExceededException":
            self._fail(state, "quota", code, trace)
        elif code in TRANSIENT_CODES:
            state["error"] = {"code": code, "at": clock.iso()}
            _add_step(trace, ("Création de la Knowledge Base reportée", "Knowledge base creation deferred"), code, {})
        else:
            logger.warning("client knowledge base creation failed: %s", code)
            self._fail(state, "failed", code, trace)

    def _fail(self, state: dict[str, Any], status: str, code: str, trace: Trace | None) -> None:
        state.update(status=status, retry_at=_later(RETRY_AFTER[status]), error={"code": code, "at": clock.iso()})
        title = (
            ("Quota de Knowledge Bases atteint", "Knowledge base quota reached")
            if status == "quota"
            else ("Knowledge Base du client en échec", "Client knowledge base failed")
        )
        _add_step(trace, title, code, {"status": status, "retry_at": state["retry_at"]})

    # ------------------------------------------------------------------ ingestion
    def _send(
        self, client_id: str, state: dict[str, Any], written: dict[str, bytes], trace: Trace | None
    ) -> SendOutcome:
        """Envoie les documents notés et en attente si la base est active; sinon les garde en attente."""
        keys = set(written) | set(state.get("pending") or [])
        if not keys:
            return SendOutcome()
        if state.get("status") != "active":
            if written:
                _add_step(
                    trace,
                    ("Documents en attente de la Knowledge Base", "Documents waiting for the knowledge base"),
                    state.get("status"),
                    {"pending": len(keys), "keys": sorted(written)},
                )
            return SendOutcome(waiting=set(written))
        prepared = self._prepare(client_id, state, written, keys)
        outcome = SendOutcome(done=set(prepared.dropped))
        state["error"] = None  # un lot refusé l'écrit de nouveau
        self._ingest(state, prepared.documents, outcome)
        self._delete(state, prepared.removals, outcome)
        _add_step(
            trace,
            ("Documents indexés dans la Knowledge Base du client", "Documents indexed in the client knowledge base"),
            state.get("knowledge_base_id"),
            {
                "ingested": sorted(outcome.sent),
                "deleted": sorted(outcome.removed),
                "pending": sorted(outcome.waiting),
                "errors": outcome.errors,
            },
        )
        return outcome

    def _prepare(self, client_id: str, state: dict[str, Any], written: dict[str, bytes], keys: set[str]) -> Prepared:
        """Lit chaque document (corps noté, sinon le magasin) : à ingérer, à retirer (note retirée) ou à oublier."""
        indexed = set(state.get("indexed") or [])
        prepared = Prepared()
        for key in sorted(keys):
            body = written.get(key)
            if body is None:
                stored = self.store.get(key)
                body = stored.body if stored is not None else None
            text, summary, retired = (
                document_text(body.decode("utf-8", errors="replace")) if body is not None else ("", {}, True)
            )
            if not retired:
                prepared.documents.append(ingest_payload(key, text, summary, client_id))
            elif key in indexed:
                prepared.removals.append(key)  # note retirée (ou document absent) : elle sort de la base
            else:
                prepared.dropped.add(key)  # jamais indexée : rien à retirer
        return prepared

    def _ingest(self, state: dict[str, Any], documents: list[dict[str, Any]], outcome: SendOutcome) -> None:
        stopped = False
        for batch in _chunks(documents, BATCH_SIZE):
            keys = [item["content"]["custom"]["customDocumentIdentifier"]["id"] for item in batch]
            if stopped:
                outcome.waiting.update(keys)
                continue
            try:
                response = self.aws.agent.ingest_knowledge_base_documents(
                    knowledgeBaseId=state["knowledge_base_id"], dataSourceId=state["data_source_id"], documents=batch
                )
            except Exception as exc:
                stopped = self._batch_error(state, keys, exc, outcome)
                continue
            failed = {
                (detail.get("identifier") or {}).get("custom", {}).get("id"): detail.get("statusReason") or "FAILED"
                for detail in response.get("documentDetails") or []
                if detail.get("status") == "FAILED"
            }
            outcome.errors.update({key: str(reason)[:200] for key, reason in failed.items() if key})
            outcome.sent.update(key for key in keys if key not in failed)
            outcome.done.update(keys)

    def _delete(self, state: dict[str, Any], keys: list[str], outcome: SendOutcome) -> None:
        stopped = False
        for batch in _chunks(keys, BATCH_SIZE):
            if stopped:
                outcome.waiting.update(batch)
                continue
            try:
                self.aws.agent.delete_knowledge_base_documents(
                    knowledgeBaseId=state["knowledge_base_id"],
                    dataSourceId=state["data_source_id"],
                    documentIdentifiers=[_identifier(key) for key in batch],
                )
            except Exception as exc:
                stopped = self._batch_error(state, batch, exc, outcome)
                continue
            outcome.removed.update(batch)
            outcome.done.update(batch)

    def _batch_error(self, state: dict[str, Any], keys: list[str], exc: Exception, outcome: SendOutcome) -> bool:
        """Lot refusé : vrai s'il faut arrêter les lots suivants (les clés restent en attente)."""
        code = error_code(exc)
        state["error"] = {"code": code, "at": clock.iso()}
        if code == "ValidationException":
            # Document refusé tel quel : le renvoyer à chaque action n'y changerait rien.
            outcome.errors.update(dict.fromkeys(keys, code))
            outcome.done.update(keys)
            return False
        outcome.waiting.update(keys)
        if code == "ResourceNotFoundException":
            state.update(status="failed", retry_at=_later(RETRY_AFTER["failed"]))
        return True

    # ------------------------------------------------------------------ recherche
    def searcher(self, client_id: str) -> Callable[[str], dict[str, Any]] | None:
        """Recherche liée à la base du client de la session (outil d'A1); ``None`` quand la fonction est désactivée."""
        return partial(self.search, client_id) if self.enabled else None

    def search(self, client_id: str, query: str, limit: int = 4) -> dict[str, Any]:
        """Passages de la Knowledge Base de ``client_id`` (identifiant lu dans ``kb.json``, jamais donné par le
        modèle), chacun cité par sa clé OKF. Une base pas encore active le dit."""
        if not self.enabled:
            return {"results": [], "status": "disabled", "note": "client knowledge base not available"}
        state, _ = self._read(client_id)
        status = (state or {}).get("status") or "creating"
        if status != "active" or not query.strip():
            return {"results": [], "status": status, "note": "client knowledge base not active yet; use the context"}
        try:
            response = self.aws.runtime.retrieve(
                knowledgeBaseId=state["knowledge_base_id"],
                retrievalQuery={"text": query[:1000]},
                retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": max(1, min(limit, 8))}},
            )
        except Exception as exc:
            logger.warning("client knowledge base retrieve failed: %s", error_code(exc))
            return {"results": [], "status": status, "note": f"search failed ({error_code(exc)})"}
        results = [_passage(item, client_id) for item in response.get("retrievalResults") or []]
        return {"results": [item for item in results if item is not None][:limit], "status": status}


def _passage(item: dict[str, Any], client_id: str) -> dict[str, Any] | None:
    """Passage cité par sa clé OKF; un passage hors du dossier du client est écarté (défense en profondeur)."""
    location = item.get("location") or {}
    key = (location.get("customDocumentLocation") or {}).get("id")
    if not isinstance(key, str) or not key.startswith(f"clients/{client_id}/"):
        return None
    text = ((item.get("content") or {}).get("text") or "").strip()
    return {
        "key": key,
        "score": round(float(item.get("score") or 0), 3),
        "excerpt": text[:EXCERPT_CHARS] + ("…" if len(text) > EXCERPT_CHARS else ""),
    }


def _unchanged(state: dict[str, Any], outcome: SendOutcome) -> bool:
    """Vrai quand le rapprochement n'a rien envoyé ni changé aux clés en attente : ``kb.json`` n'est pas réécrit."""
    if outcome.sent or outcome.removed or outcome.errors:
        return False
    pending = set(state.get("pending") or [])
    return (pending | outcome.waiting) - outcome.done == pending
