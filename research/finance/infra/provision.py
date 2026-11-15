"""Infrastructure de traçabilité AlphaForge AI (idempotent, rejouable dans un nouveau compte).

    python research/finance/infra/provision.py            # crée ou met à jour
    python research/finance/infra/provision.py --teardown # supprime ce que ce script a créé

Ressources (préfixe ``alphaforge-``, région us-east-1) :
- S3 ``alphaforge-trace-<compte>`` : versioning, Object Lock (GOVERNANCE, 3 jours), accès public bloqué.
  Préfixes : bedrock-invocations/ (journal Bedrock), llm-replay/ (réponses rejouables), decisions/, otel/.
- CloudWatch Logs : /alphaforge/bedrock/invocations, /alphaforge/app (événements structurés).
- IAM : rôle ``alphaforge-bedrock-logging`` que Bedrock assume pour écrire dans CloudWatch Logs.
- Bedrock : model invocation logging (requêtes et réponses complètes → S3 + CloudWatch). Réglage du COMPTE.
- DynamoDB : ``alphaforge-llm-replay`` (index du rejeu) et ``alphaforge-decisions`` (journal), PITR activé.
- Bedrock Guardrail ``alphaforge-finance`` + version numérotée (sujets interdits, données personnelles,
  attaques de prompt, ancrage contextuel), tier Classic (français).
- X-Ray Transaction Search : spans OpenTelemetry → CloudWatch (déjà ACTIVE dans ce compte).
Aucun secret n'est écrit : outputs.json ne contient que des noms et des ARN.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
TAGS = {"project": "alphaforge", "owner": "larpathon", "purpose": "tracabilite"}
OUT = Path(__file__).with_name("outputs.json")

LOG_GROUPS = {"/alphaforge/bedrock/invocations": 14, "/alphaforge/app": 14}
TABLES = {"alphaforge-llm-replay": "pk", "alphaforge-decisions": "pk"}
GUARDRAIL = "alphaforge-finance"
LOGGING_ROLE = "alphaforge-bedrock-logging"


def _exists(fn, *codes):
    try:
        fn()
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in codes:
            return False
        raise


def provision() -> dict:
    sess = boto3.Session(region_name=REGION)
    acct = sess.client("sts").get_caller_identity()["Account"]
    s3, logs, iam = sess.client("s3"), sess.client("logs"), sess.client("iam")
    ddb, bedrock = sess.client("dynamodb"), sess.client("bedrock")
    bucket = f"alphaforge-trace-{acct}"
    out: dict = {"region": REGION, "bucket": bucket}

    # --- S3 : versioning + Object Lock (doit être activé à la création)
    if not _exists(lambda: s3.head_bucket(Bucket=bucket), "404", "NoSuchBucket", "NotFound"):
        s3.create_bucket(Bucket=bucket, ObjectLockEnabledForBucket=True)
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    s3.put_object_lock_configuration(Bucket=bucket, ObjectLockConfiguration={
        "ObjectLockEnabled": "Enabled", "Rule": {"DefaultRetention": {"Mode": "GOVERNANCE", "Days": 3}}})
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in TAGS.items()]})
    s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps({"Version": "2012-10-17", "Statement": [{
        "Sid": "BedrockInvocationLogs", "Effect": "Allow", "Principal": {"Service": "bedrock.amazonaws.com"},
        "Action": "s3:PutObject", "Resource": f"arn:aws:s3:::{bucket}/bedrock-invocations/AWSLogs/{acct}/BedrockModelInvocationLogs/*",
        "Condition": {"StringEquals": {"aws:SourceAccount": acct},
                      "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{REGION}:{acct}:*"}}}]}))

    # --- CloudWatch Logs
    for name, days in LOG_GROUPS.items():
        try:
            logs.create_log_group(logGroupName=name, tags=TAGS)
        except logs.exceptions.ResourceAlreadyExistsException:
            pass
        logs.put_retention_policy(logGroupName=name, retentionInDays=days)
    out["log_groups"] = list(LOG_GROUPS)

    # --- IAM : rôle de journalisation Bedrock → CloudWatch
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "bedrock.amazonaws.com"},
             "Action": "sts:AssumeRole", "Condition": {"StringEquals": {"aws:SourceAccount": acct},
             "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{REGION}:{acct}:*"}}}]}
    try:
        role_arn = iam.create_role(RoleName=LOGGING_ROLE, AssumeRolePolicyDocument=json.dumps(trust),
                                   Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()])["Role"]["Arn"]
        time.sleep(10)   # propagation IAM
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName=LOGGING_ROLE)["Role"]["Arn"]
    iam.put_role_policy(RoleName=LOGGING_ROLE, PolicyName="write-invocation-logs", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
        "Resource": f"arn:aws:logs:{REGION}:{acct}:log-group:/alphaforge/bedrock/invocations:log-stream:*"}]}))
    out["logging_role_arn"] = role_arn

    # --- Bedrock : journal complet des invocations (réglage du compte)
    for attempt in range(6):
        try:
            bedrock.put_model_invocation_logging_configuration(loggingConfig={
                "cloudWatchConfig": {"logGroupName": "/alphaforge/bedrock/invocations", "roleArn": role_arn,
                                     "largeDataDeliveryS3Config": {"bucketName": bucket, "keyPrefix": "bedrock-invocations/large"}},
                "s3Config": {"bucketName": bucket, "keyPrefix": "bedrock-invocations"},
                "textDataDeliveryEnabled": True, "imageDataDeliveryEnabled": True,
                "embeddingDataDeliveryEnabled": True, "videoDataDeliveryEnabled": True})
            break
        except ClientError as e:
            if attempt == 5 or e.response["Error"]["Code"] not in ("ValidationException", "AccessDeniedException"):
                raise
            time.sleep(10)   # le rôle IAM peut mettre quelques secondes à être assumable
    out["invocation_logging"] = "s3+cloudwatch"

    # --- DynamoDB : index du rejeu et journal des décisions
    for name, pk in TABLES.items():
        try:
            ddb.create_table(TableName=name, BillingMode="PAY_PER_REQUEST",
                             AttributeDefinitions=[{"AttributeName": pk, "AttributeType": "S"}],
                             KeySchema=[{"AttributeName": pk, "KeyType": "HASH"}],
                             Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()])
        except ddb.exceptions.ResourceInUseException:
            pass
        ddb.get_waiter("table_exists").wait(TableName=name)
        ddb.update_continuous_backups(TableName=name, PointInTimeRecoverySpecification={
            "PointInTimeRecoveryEnabled": True})
    out["tables"] = list(TABLES)

    # --- Transaction Search : spans OTLP → CloudWatch Logs (aws/spans), indexés à 100 % dans X-Ray
    out.update(_transaction_search(sess, acct))

    # --- Guardrail + version numérotée
    out.update(_guardrail(bedrock))
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return out


def _transaction_search(sess, acct) -> dict:
    """L'endpoint OTLP de X-Ray exige la destination CloudWatch Logs (sinon 400 Bad Request)."""
    logs, xray = sess.client("logs"), sess.client("xray")
    logs.put_resource_policy(policyName="alphaforge-xray-transaction-search", policyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Sid": "TransactionSearchXRayAccess", "Effect": "Allow",
        "Principal": {"Service": "xray.amazonaws.com"}, "Action": "logs:PutLogEvents",
        "Resource": [f"arn:aws:logs:{REGION}:{acct}:log-group:aws/spans:*",
                     f"arn:aws:logs:{REGION}:{acct}:log-group:/aws/application-signals/data:*"],
        "Condition": {"ArnLike": {"aws:SourceArn": f"arn:aws:xray:{REGION}:{acct}:*"},
                      "StringEquals": {"aws:SourceAccount": acct}}}]}))
    if xray.get_trace_segment_destination()["Destination"] != "CloudWatchLogs":
        xray.update_trace_segment_destination(Destination="CloudWatchLogs")
    xray.update_indexing_rule(Name="Default", Rule={"Probabilistic": {"DesiredSamplingPercentage": 100.0}})
    return {"transaction_search": "CloudWatchLogs", "xray_indexing_percent": 100}


# Sans ces champs explicites, le filtre de données personnelles reste inactif (constaté le 2026-11-14).
_IO = {"inputAction": "ANONYMIZE", "outputAction": "ANONYMIZE", "inputEnabled": True, "outputEnabled": True}


def _guardrail(bedrock) -> dict:
    spec = dict(
        name=GUARDRAIL,
        description="AlphaForge AI : simulation éducative, aucun conseil personnalisé ni transaction réelle.",
        topicPolicyConfig={"topicsConfig": [
            {"name": "conseil-personnalise-reel", "type": "DENY",
             "definition": "Recommandation d'investissement personnalisée présentée comme un conseil financier réel et réglementé.",
             "examples": ["Achetez exactement 300 actions de TSLA demain matin, c'est mon conseil officiel."]},
            {"name": "execution-ordres", "type": "DENY",
             "definition": "Passer, transmettre ou exécuter un ordre d'achat ou de vente réel, ou demander des identifiants de courtage.",
             "examples": ["Passe l'ordre d'achat sur mon compte de courtage avec mon mot de passe."]},
            {"name": "garantie-rendement", "type": "DENY",
             "definition": "Promettre ou garantir un rendement, un gain ou l'absence de perte sur un placement.",
             "examples": ["Ce portefeuille vous garantit 12 % par an sans aucun risque."]}]},
        contentPolicyConfig={"filtersConfig": [
            {"type": t, "inputStrength": "HIGH", "outputStrength": "HIGH"} for t in
            ("SEXUAL", "VIOLENCE", "HATE", "INSULTS", "MISCONDUCT")] +
            [{"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"}]},
        sensitiveInformationPolicyConfig={"piiEntitiesConfig": [
            {"type": t, "action": "ANONYMIZE", **_IO} for t in
            ("EMAIL", "PHONE", "NAME", "ADDRESS", "CA_SOCIAL_INSURANCE_NUMBER", "CA_HEALTH_NUMBER",
             "CREDIT_DEBIT_CARD_NUMBER", "PASSWORD", "US_BANK_ACCOUNT_NUMBER")],
            # Le NAS écrit avec espaces ou tirets (« 046 454 286 ») n'est pas reconnu par le filtre géré.
            "regexesConfig": [{"name": "nas-canadien", "action": "ANONYMIZE", **_IO,
                               "description": "Numéro d'assurance sociale canadien, 9 chiffres groupés par 3",
                               "pattern": r"\b\d{3}[ -]?\d{3}[ -]?\d{3}\b"}]},
        contextualGroundingPolicyConfig={"filtersConfig": [
            {"type": "GROUNDING", "threshold": 0.75}, {"type": "RELEVANCE", "threshold": 0.1}]},  # pertinence = indicateur
        blockedInputMessaging="Demande hors du cadre de la simulation AlphaForge (aucun conseil réel, aucun ordre).",
        blockedOutputsMessaging="Réponse retenue : elle sortait du cadre de la simulation ou n'était pas ancrée dans les données.",
        tags=[{"key": k, "value": v} for k, v in TAGS.items()])
    import hashlib
    spec_hash = hashlib.sha256(json.dumps({k: v for k, v in spec.items() if k != "tags"}, sort_keys=True,
                                          ensure_ascii=False).encode()).hexdigest()[:16]
    existing = [g for g in bedrock.list_guardrails()["guardrails"] if g["name"] == GUARDRAIL]
    if existing:
        gid = existing[0]["id"]
        versions = [g for g in bedrock.list_guardrails(guardrailIdentifier=gid)["guardrails"] if g["version"] != "DRAFT"]
        same = [v for v in versions if f"spec={spec_hash}" in (v.get("description") or "")]
        if same:                                            # configuration inchangée : on garde la version
            return {"guardrail_id": gid, "guardrail_version": max(same, key=lambda v: int(v["version"]))["version"]}
        bedrock.update_guardrail(guardrailIdentifier=gid, **{k: v for k, v in spec.items() if k != "tags"})
    else:
        gid = bedrock.create_guardrail(**spec)["guardrailId"]
    for _ in range(30):
        if bedrock.get_guardrail(guardrailIdentifier=gid)["status"] == "READY":
            break
        time.sleep(2)
    ver = bedrock.create_guardrail_version(
        guardrailIdentifier=gid, description=f"spec={spec_hash} {time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime())}")["version"]
    return {"guardrail_id": gid, "guardrail_version": ver}


def teardown():
    sess = boto3.Session(region_name=REGION)
    acct = sess.client("sts").get_caller_identity()["Account"]
    bedrock, ddb, logs, iam = (sess.client(x) for x in ("bedrock", "dynamodb", "logs", "iam"))
    bedrock.delete_model_invocation_logging_configuration()
    for g in bedrock.list_guardrails()["guardrails"]:
        if g["name"] == GUARDRAIL:
            bedrock.delete_guardrail(guardrailIdentifier=g["id"])
    for t in TABLES:
        with __import__("contextlib").suppress(ddb.exceptions.ResourceNotFoundException):
            ddb.delete_table(TableName=t)
    for name in LOG_GROUPS:
        with __import__("contextlib").suppress(logs.exceptions.ResourceNotFoundException):
            logs.delete_log_group(logGroupName=name)
    with __import__("contextlib").suppress(iam.exceptions.NoSuchEntityException):
        iam.delete_role_policy(RoleName=LOGGING_ROLE, PolicyName="write-invocation-logs")
        iam.delete_role(RoleName=LOGGING_ROLE)
    print(f"Le bucket alphaforge-trace-{acct} est conservé (Object Lock, 3 jours) : il disparaîtra avec le compte.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--teardown", action="store_true")
    a = ap.parse_args()
    if a.teardown:
        teardown()
    else:
        print(json.dumps(provision(), indent=2, ensure_ascii=False))
