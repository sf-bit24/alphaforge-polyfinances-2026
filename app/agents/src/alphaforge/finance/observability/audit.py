"""Journal d'audit des décisions, chaîné par hash (inviolabilité vérifiable).

Chaque décision est sérialisée canoniquement ; ``record_hash = sha256(prev_hash + decision_hash)``.
Modifier une décision passée casse la chaîne de son profil (``verify_chain``).
Supports : JSONL local (toujours) ; S3 ``decisions/`` (Object Lock du bucket) et DynamoDB
``alphaforge-decisions`` (écriture conditionnelle) si ``outputs.json`` est fourni.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from ..contracts import Decision
from .telemetry import canonical_hash, current_ids, log_event, span

GENESIS = "0" * 64


def _local_path(root: str, profile_id: str) -> str:
    return os.path.join(root, f"{profile_id}.jsonl")


def _last(root: str, profile_id: str) -> dict | None:
    path = _local_path(root, profile_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    return json.loads(lines[-1]) if lines else None


def record_decision(decision: Decision, root: str, aws: dict | None = None) -> dict:
    payload = decision.model_dump(mode="json")
    d_hash = canonical_hash(payload)
    prev = _last(root, decision.profile_id)
    prev_hash = prev["record_hash"] if prev else GENESIS
    tid, sid = current_ids()
    entry = {"decision_id": decision.decision_id, "profile_id": decision.profile_id,
             "seq": (prev["seq"] + 1) if prev else 0, "recorded_utc": datetime.now(UTC).isoformat(),
             "decision_hash": d_hash, "prev_hash": prev_hash,
             "record_hash": canonical_hash({"prev": prev_hash, "decision": d_hash}),
             "otel_trace_id": tid, "otel_span_id": sid, "kind": decision.kind}
    with span("audit.record_decision", decision_id=decision.decision_id, record_hash=entry["record_hash"]):
        os.makedirs(root, exist_ok=True)
        with open(_local_path(root, decision.profile_id), "a", encoding="utf-8") as f:
            f.write(json.dumps({**entry, "decision": payload}, ensure_ascii=False, sort_keys=True) + "\n")
        if aws:
            import boto3
            s3 = boto3.client("s3", region_name=aws["region"])
            ddb = boto3.client("dynamodb", region_name=aws["region"])
            key = f"decisions/{decision.profile_id}/{entry['seq']:06d}-{decision.decision_id}.json"
            put = s3.put_object(Bucket=aws["bucket"], Key=key, ContentType="application/json",
                                Body=json.dumps({**entry, "decision": payload}, ensure_ascii=False).encode())
            ddb.put_item(TableName="alphaforge-decisions", ConditionExpression="attribute_not_exists(pk)",
                         Item={"pk": {"S": decision.decision_id}, "profile_id": {"S": decision.profile_id},
                               "seq": {"N": str(entry["seq"])}, "record_hash": {"S": entry["record_hash"]},
                               "prev_hash": {"S": prev_hash}, "s3_key": {"S": key},
                               "s3_version": {"S": put.get("VersionId", "null")},
                               "recorded_utc": {"S": entry["recorded_utc"]}, "kind": {"S": decision.kind}})
            entry["s3_key"] = key
        log_event("audit.decision_recorded", **{k: entry[k] for k in ("decision_id", "seq", "record_hash", "kind")})
    return entry


def verify_chain(root: str, profile_id: str) -> tuple[bool, int | None]:
    """(True, None) si la chaîne est intacte, sinon (False, seq du premier maillon altéré)."""
    prev = GENESIS
    with open(_local_path(root, profile_id), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["prev_hash"] != prev or canonical_hash(r["decision"]) != r["decision_hash"] or \
                    canonical_hash({"prev": prev, "decision": r["decision_hash"]}) != r["record_hash"]:
                return False, r["seq"]
            prev = r["record_hash"]
    return True, None
