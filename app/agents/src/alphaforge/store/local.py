"""Magasin local : un fichier par clé sous ``ALPHAFORGE_LOCAL_DIR`` (développement seulement)."""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

from . import ConflictError, ObjectInfo, Store, StoredObject, StoreError, validate_key, validate_prefix

_LOCK = threading.RLock()


def _etag(body: bytes) -> str:
    return '"' + hashlib.md5(body, usedforsecurity=False).hexdigest() + '"'


class LocalStore(Store):
    name = "local"

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise StoreError(f"key escapes the store root: {key!r}")
        return path

    def get(self, key: str) -> StoredObject | None:
        path = self._path(key)
        with _LOCK:
            if not path.is_file():
                return None
            body = path.read_bytes()
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        return StoredObject(key=key, body=body, etag=_etag(body), last_modified=modified.strftime("%Y-%m-%dT%H:%M:%SZ"))

    def put(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str = "text/markdown; charset=utf-8",
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> str:
        path = self._path(key)
        with _LOCK:
            exists = path.is_file()
            if if_none_match and exists:
                raise ConflictError(key)
            if if_match is not None and (not exists or _etag(path.read_bytes()) != if_match):
                raise ConflictError(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(body)
                os.replace(tmp, path)
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        return _etag(body)

    def list(self, prefix: str, *, limit: int = 1000) -> list[ObjectInfo]:
        validate_prefix(prefix)
        base = self.root / prefix
        items: list[ObjectInfo] = []
        with _LOCK:
            if not base.is_dir():
                return []
            for path in sorted(base.rglob("*")):
                if not path.is_file() or path.name.startswith(".tmp-"):
                    continue
                key = path.relative_to(self.root).as_posix()
                stat = path.stat()
                modified = datetime.fromtimestamp(stat.st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                items.append(ObjectInfo(key=key, etag="", last_modified=modified, size=stat.st_size))
                if len(items) >= limit:
                    break
        return items
