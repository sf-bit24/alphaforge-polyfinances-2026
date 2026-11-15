"""Journal d'audit des décisions, chaîné par hash (inviolabilité vérifiable).

Chaque décision est sérialisée canoniquement ; ``record_hash = sha256(prev_hash + decision_hash)``.
Modifier une décision passée casse la chaîne de son profil (``verify_chain``).
Supports : JSONL local (toujours) ; S3 ``decisions/`` (Object Lock du bucket) et DynamoDB
(écriture conditionnelle) si ``aws`` est fourni. Noms : ``aws["decisions_table"]``, sinon
``ALPHAFORGE_DECISIONS_TABLE`` (output Terraform ``decisions_table``), sinon ``alphaforge-decisions``.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime

from ..contracts import Decision
from .telemetry import canonical_hash, current_ids, log_event, span

GENESIS = "0" * 64
TABLE = os.environ.get("ALPHAFORGE_DECISIONS_TABLE", "alphaforge-decisions")


def _local_path(root: str, profile_id: str) -> str:
    return os.path.join(root, f"{profile_id}.jsonl")


def _last(root: str, profile_id: str) -> dict | None:
    path = _local_path(root, profile_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as journal:
        lines = [line for line in journal if line.strip()]
    return json.loads(lines[-1]) if lines else None


def _local_head(root: str, profile_id: str) -> tuple[str, int]:
    """(record_hash, seq) du dernier maillon du journal local, ou la genèse."""
    last = _last(root, profile_id)
    return (last["record_hash"], last["seq"]) if last else (GENESIS, -1)


@contextmanager
def _profile_lock(root: str, profile_id: str):
    """Verrou exclusif par profil : lire la tête et ajouter le maillon forment une seule opération."""
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, f".{profile_id}.lock"), "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


class _DynamoChain:
    """Chaîne sur AWS : la tête du profil vit dans DynamoDB (``head#<profil>``), le corps des décisions dans S3."""

    def __init__(self, aws: dict):
        import boto3

        self.aws = aws
        self.table = aws.get("decisions_table", TABLE)
        self.ddb = boto3.client("dynamodb", region_name=aws["region"])
        self.s3 = boto3.client("s3", region_name=aws["region"])

    @property
    def conflict_error(self) -> type[Exception]:
        return self.ddb.exceptions.TransactionCanceledException

    def head(self, profile_id: str) -> tuple[str, int]:
        key = {"pk": {"S": f"head#{profile_id}"}}
        item = self.ddb.get_item(TableName=self.table, Key=key, ConsistentRead=True).get("Item")
        if not item:
            return GENESIS, -1
        return item["record_hash"]["S"], int(item["seq"]["N"])

    def publish(self, entry: dict, payload: dict) -> None:
        """Corps dans S3, puis une transaction qui insère la décision et avance la tête, à condition que la tête
        n'ait pas bougé (sinon ``conflict_error``)."""
        key = f"decisions/{entry['profile_id']}/{entry['seq']:06d}-{entry['decision_id']}.json"
        put = self.s3.put_object(
            Bucket=self.aws["bucket"],
            Key=key,
            ContentType="application/json",
            Body=json.dumps({**entry, "decision": payload}, ensure_ascii=False).encode(),
        )
        self.ddb.transact_write_items(TransactItems=[self._decision_item(entry, key, put), self._head_item(entry)])
        entry["s3_key"] = key

    def _decision_item(self, entry: dict, key: str, put: dict) -> dict:
        item = {
            "pk": {"S": entry["decision_id"]},
            "profile_id": {"S": entry["profile_id"]},
            "seq": {"N": str(entry["seq"])},
            "record_hash": {"S": entry["record_hash"]},
            "prev_hash": {"S": entry["prev_hash"]},
            "s3_key": {"S": key},
            "s3_version": {"S": put.get("VersionId", "null")},
            "recorded_utc": {"S": entry["recorded_utc"]},
            "kind": {"S": entry["kind"]},
        }
        return {"Put": {"TableName": self.table, "ConditionExpression": "attribute_not_exists(pk)", "Item": item}}

    def _head_item(self, entry: dict) -> dict:
        previous_seq = entry["seq"] - 1
        condition = "attribute_not_exists(pk)" if previous_seq < 0 else "record_hash = :prev"
        values = {} if previous_seq < 0 else {":prev": {"S": entry["prev_hash"]}}
        item = {
            "pk": {"S": f"head#{entry['profile_id']}"},
            "record_hash": {"S": entry["record_hash"]},
            "seq": {"N": str(entry["seq"])},
            "decision_id": {"S": entry["decision_id"]},
        }
        return {
            "Put": {
                "TableName": self.table,
                "ConditionExpression": condition,
                **({"ExpressionAttributeValues": values} if values else {}),
                "Item": item,
            }
        }


def _chain_entry(
    decision: Decision, decision_hash: str, head: tuple[str, int], otel_ids: tuple[str | None, str | None]
) -> dict:
    prev_hash, prev_seq = head
    otel_trace_id, otel_span_id = otel_ids
    return {
        "decision_id": decision.decision_id,
        "profile_id": decision.profile_id,
        "seq": prev_seq + 1,
        "recorded_utc": datetime.now(UTC).isoformat(),
        "decision_hash": decision_hash,
        "prev_hash": prev_hash,
        "record_hash": canonical_hash({"prev": prev_hash, "decision": decision_hash}),
        "otel_trace_id": otel_trace_id,
        "otel_span_id": otel_span_id,
        "kind": decision.kind,
    }


def record_decision(decision: Decision, root: str, aws: dict | None = None, max_retries: int = 3) -> dict:
    """Ajoute la décision à la chaîne de son profil.

    Local : verrou par profil autour de « lire la tête + ajouter ». AWS : la tête du profil vit dans
    DynamoDB (``head#<profil>``) et n'avance que par une transaction qui insère aussi la décision,
    à condition que la tête n'ait pas bougé. En cas de conflit, on relit et on réessaie.
    Quand AWS est actif, sa tête fait foi ; le journal local en est le miroir.
    """
    payload = decision.model_dump(mode="json")
    decision_hash = canonical_hash(payload)
    otel_ids = current_ids()
    with span("audit.record_decision", decision_id=decision.decision_id), _profile_lock(root, decision.profile_id):
        chain = _DynamoChain(aws) if aws else None
        for attempt in range(max_retries):
            head = chain.head(decision.profile_id) if chain else _local_head(root, decision.profile_id)
            entry = _chain_entry(decision, decision_hash, head, otel_ids)
            if chain is None:
                break
            try:
                chain.publish(entry, payload)
                break
            except chain.conflict_error:
                if attempt == max_retries - 1:
                    raise
        with open(_local_path(root, decision.profile_id), "a", encoding="utf-8") as journal:
            journal.write(json.dumps({**entry, "decision": payload}, ensure_ascii=False, sort_keys=True) + "\n")
        log_event("audit.decision_recorded", **{k: entry[k] for k in ("decision_id", "seq", "record_hash", "kind")})
    return entry


def _is_intact(record: dict, prev_hash: str) -> bool:
    return (
        record["prev_hash"] == prev_hash
        and canonical_hash(record["decision"]) == record["decision_hash"]
        and canonical_hash({"prev": prev_hash, "decision": record["decision_hash"]}) == record["record_hash"]
    )


def verify_chain(root: str, profile_id: str) -> tuple[bool, int | None]:
    """(True, None) si la chaîne est intacte, sinon (False, seq du premier maillon altéré)."""
    prev_hash = GENESIS
    with open(_local_path(root, profile_id), encoding="utf-8") as journal:
        for line in journal:
            record = json.loads(line)
            if not _is_intact(record, prev_hash):
                return False, record["seq"]
            prev_hash = record["record_hash"]
    return True, None
