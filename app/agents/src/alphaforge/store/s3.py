"""Magasin S3 : le bucket chiffre par défaut en SSE-KMS, aucun en-tête de chiffrement n'est envoyé.

Envoyer ``ServerSideEncryption=aws:kms`` sans clé ferait utiliser la clé gérée ``aws/s3`` au lieu de la clé
par défaut du bucket; on laisse donc le chiffrement par défaut du bucket s'appliquer.

Clé absente : les rôles des runtimes n'ont ``s3:ListBucket`` que sous une condition ``s3:prefix``. Une requête
``GetObject`` ne porte pas de préfixe, donc S3 répond 403 (``AccessDenied``) au lieu de 404 pour un objet
absent. Sur un 403, on vérifie l'absence par ``ListObjectsV2`` avec ``Prefix=<clé>`` : aucune entrée égale à
la clé, l'objet est absent (``None``); sinon, ou si la liste échoue, l'erreur d'origine est relevée.
"""

from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from . import ConflictError, ObjectInfo, Store, StoredObject, validate_key, validate_prefix

_CONFLICT_CODES = {"PreconditionFailed", "ConditionalRequestConflict", "412", "409"}
_MISSING_CODES = {"NoSuchKey", "404", "NotFound"}
_DENIED_CODES = {"AccessDenied", "403", "Forbidden"}


def _error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


class S3Store(Store):
    name = "s3"

    def __init__(self, bucket: str, *, region: str, client: Any | None = None):
        self.bucket = bucket
        self.client = client or boto3.client(
            "s3",
            region_name=region,
            config=Config(retries={"max_attempts": 4, "mode": "standard"}, connect_timeout=5, read_timeout=20),
        )

    def _absent_after_denied(self, key: str) -> bool:
        """Vrai si ``ListObjectsV2`` confirme que la clé n'existe pas (aucune entrée égale à la clé)."""
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=key, MaxKeys=1)
        return not any(entry.get("Key") == key for entry in response.get("Contents", []))

    def _missing(self, exc: ClientError, key: str) -> bool:
        code = _error_code(exc)
        if code in _MISSING_CODES:
            return True
        if code in _DENIED_CODES:
            try:
                return self._absent_after_denied(key)
            except Exception:
                return False
        return False

    def get(self, key: str) -> StoredObject | None:
        validate_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if self._missing(exc, key):
                return None
            raise
        body = response["Body"].read()
        modified = response.get("LastModified")
        return StoredObject(
            key=key,
            body=body,
            etag=response.get("ETag", ""),
            last_modified=modified.strftime("%Y-%m-%dT%H:%M:%SZ") if modified else "",
        )

    def exists(self, key: str) -> bool:
        validate_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if self._missing(exc, key):
                return False
            raise
        return True

    def put(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str = "text/markdown; charset=utf-8",
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> str:
        validate_key(key)
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key, "Body": body, "ContentType": content_type}
        if if_match is not None:
            params["IfMatch"] = if_match
        elif if_none_match:
            params["IfNoneMatch"] = "*"
        try:
            response = self.client.put_object(**params)
        except ClientError as exc:
            if _error_code(exc) in _CONFLICT_CODES:
                raise ConflictError(key) from exc
            raise
        return response.get("ETag", "")

    def list(self, prefix: str, *, limit: int = 1000) -> list[ObjectInfo]:
        validate_prefix(prefix)
        items: list[ObjectInfo] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for entry in page.get("Contents", []):
                modified = entry.get("LastModified")
                items.append(
                    ObjectInfo(
                        key=entry["Key"],
                        etag=entry.get("ETag", ""),
                        last_modified=modified.strftime("%Y-%m-%dT%H:%M:%SZ") if modified else "",
                        size=int(entry.get("Size", 0)),
                    )
                )
                if len(items) >= limit:
                    return items
        return items
