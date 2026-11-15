"""Magasin des bases OKF : une interface, deux implémentations (S3 en AWS, répertoire local en développement).

Les écritures conditionnelles (``if_match`` sur l'ETag, ``if_none_match`` pour une création) servent la
concurrence optimiste : deux requêtes qui modifient le même profil ne s'écrasent pas, la seconde reçoit
``ConflictError`` (code d'erreur ``conflict``).
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]*$")
MAX_KEY_LENGTH = 512


class ConflictError(Exception):
    """L'objet a changé depuis sa lecture (précondition d'écriture non respectée)."""


class StoreError(Exception):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    body: bytes
    etag: str
    last_modified: str

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    etag: str
    last_modified: str
    size: int


def validate_key(key: str) -> str:
    if not isinstance(key, str) or not key or len(key) > MAX_KEY_LENGTH:
        raise StoreError("invalid key")
    if not KEY_PATTERN.match(key) or ".." in key or "//" in key or key.endswith("/"):
        raise StoreError(f"invalid key {key!r}")
    return key


def validate_prefix(prefix: str) -> str:
    if not isinstance(prefix, str) or not prefix.endswith("/"):
        raise StoreError("prefix must end with /")
    validate_key(prefix[:-1])
    return prefix


class Store(ABC):
    name = "store"

    @abstractmethod
    def get(self, key: str) -> StoredObject | None: ...

    @abstractmethod
    def put(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str = "text/markdown; charset=utf-8",
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> str:
        """Écrit l'objet et renvoie son ETag; lève ``ConflictError`` si la précondition échoue."""

    @abstractmethod
    def list(self, prefix: str, *, limit: int = 1000) -> list[ObjectInfo]: ...

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def get_text(self, key: str) -> StoredObject | None:
        return self.get(key)

    def put_text(self, key: str, text: str, **kwargs: Any) -> str:
        return self.put(key, text.encode("utf-8"), **kwargs)

    def get_json(self, key: str) -> Any | None:
        obj = self.get(key)
        if obj is None:
            return None
        return json.loads(obj.body.decode("utf-8"))

    def put_json(self, key: str, value: Any, **kwargs: Any) -> str:
        body = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        return self.put(key, body, content_type="application/json; charset=utf-8", **kwargs)


def make_store(settings: Any) -> Store:
    if settings.store == "s3":
        from .s3 import S3Store

        if not settings.bucket:
            raise StoreError("ALPHAFORGE_BUCKET is required when ALPHAFORGE_STORE=s3")
        return S3Store(settings.bucket, region=settings.region)
    if settings.store == "local":
        from .local import LocalStore

        return LocalStore(settings.local_dir)
    raise StoreError(f"unknown store {settings.store!r}")
