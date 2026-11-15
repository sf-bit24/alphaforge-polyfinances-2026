# =============================================================================
# Service : tracabilite du volet finance (journal LLM, rejeu, audit, traces).
#
#   - bucket de traces : Object Lock GOVERNANCE (les preuves ne se reecrivent
#     pas pendant la fenetre de retention), recoit le journal complet des
#     invocations Bedrock et les reponses enregistrees du rejeu LLM ;
#   - journal des invocations Bedrock (reglage du COMPTE, singleton) vers S3 et
#     CloudWatch Logs ;
#   - DynamoDB : index du rejeu LLM (cle sha256 canonique) et journal des
#     decisions chaine par hachage (en-tete head#<profil>), PITR actif ;
#   - X-Ray Transaction Search : les spans OTLP (GenAI) vont dans CloudWatch
#     Logs (aws/spans) et sont indexes a 100 %.
#
# Remplace research/finance/infra/provision.py (boto3, a retirer apres apply).
# Les journaux sont chiffres par la cle geree par AWS : la cle "logs" du projet
# est restreinte aux journaux Step Functions (stepfunctions.tf).
# =============================================================================

locals {
  trace_bucket_name = "${local.prefix}-traces-${local.account_id}"
  bedrock_source_conditions = {
    account = local.account_id
    arn     = "arn:${local.partition}:bedrock:${var.aws_region}:${local.account_id}:*"
  }
}

# -----------------------------------------------------------------------------
# Bucket de traces
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "traces" {
  bucket              = local.trace_bucket_name
  object_lock_enabled = true
  # Compte jetable : le provider contourne la retention GOVERNANCE au destroy.
  force_destroy = true
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "traces" {
  bucket                  = aws_s3_bucket.traces.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "traces" {
  bucket = aws_s3_bucket.traces.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "traces" {
  bucket = aws_s3_bucket.traces.id
  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = var.trace_retention_days
    }
  }
  depends_on = [aws_s3_bucket_versioning.traces]
}

# SSE-S3 : Bedrock ecrit le journal avec son principal de service, sans
# passer par une key policy KMS.
resource "aws_s3_bucket_server_side_encryption_configuration" "traces" {
  bucket = aws_s3_bucket.traces.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_iam_policy_document" "traces_bucket" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    resources = [aws_s3_bucket.traces.arn, "${aws_s3_bucket.traces.arn}/*"]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid     = "BedrockInvocationLogs"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    resources = ["${aws_s3_bucket.traces.arn}/bedrock-invocations/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.bedrock_source_conditions.account]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [local.bedrock_source_conditions.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "traces" {
  bucket     = aws_s3_bucket.traces.id
  policy     = data.aws_iam_policy_document.traces_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.traces]
}

# -----------------------------------------------------------------------------
# CloudWatch Logs
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "bedrock_invocations" {
  name              = "/${local.prefix}/bedrock/invocations"
  retention_in_days = 14
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "finance_app" {
  name              = "/${local.prefix}/finance"
  retention_in_days = 14
  tags              = local.common_tags
}

# -----------------------------------------------------------------------------
# Journal des invocations Bedrock (reglage du compte)
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "bedrock_logging_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.bedrock_source_conditions.account]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [local.bedrock_source_conditions.arn]
    }
  }
}

resource "aws_iam_role" "bedrock_logging" {
  name               = "${local.prefix}-bedrock-logging"
  description        = "Bedrock ecrit le journal des invocations dans CloudWatch Logs."
  assume_role_policy = data.aws_iam_policy_document.bedrock_logging_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "bedrock_logging" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.bedrock_invocations.arn}:log-stream:*"]
  }
}

resource "aws_iam_role_policy" "bedrock_logging" {
  name   = "write-invocation-logs"
  role   = aws_iam_role.bedrock_logging.id
  policy = data.aws_iam_policy_document.bedrock_logging.json
}

resource "aws_bedrock_model_invocation_logging_configuration" "this" {
  logging_config {
    text_data_delivery_enabled      = true
    image_data_delivery_enabled     = true
    embedding_data_delivery_enabled = true
    video_data_delivery_enabled     = true

    cloudwatch_config {
      log_group_name = aws_cloudwatch_log_group.bedrock_invocations.name
      role_arn       = aws_iam_role.bedrock_logging.arn
      large_data_delivery_s3_config {
        bucket_name = aws_s3_bucket.traces.id
        key_prefix  = "bedrock-invocations/large"
      }
    }

    s3_config {
      bucket_name = aws_s3_bucket.traces.id
      key_prefix  = "bedrock-invocations"
    }
  }

  depends_on = [aws_s3_bucket_policy.traces, aws_iam_role_policy.bedrock_logging]
}

# -----------------------------------------------------------------------------
# DynamoDB : rejeu LLM et journal des decisions
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "trace" {
  for_each = toset(["llm-replay", "decisions"])

  name         = "${local.prefix}-${each.key}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = local.common_tags
}

# Les runtimes AgentCore lisent et ajoutent (ecritures conditionnelles, jamais
# de suppression : le journal est en ajout seul).
data "aws_iam_policy_document" "agentcore_traces" {
  statement {
    sid = "ReplayAndAudit"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
      "dynamodb:ConditionCheckItem",
      "dynamodb:TransactWriteItems",
      "dynamodb:UpdateItem",
    ]
    resources = [for t in aws_dynamodb_table.trace : t.arn]
  }
  statement {
    sid       = "ReplayAndDecisionBlobs"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.traces.arn}/llm-replay/*", "${aws_s3_bucket.traces.arn}/decisions/*"]
  }
  statement {
    sid       = "AppLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.finance_app.arn}:log-stream:*"]
  }
}

resource "aws_iam_role_policy" "agentcore_traces" {
  for_each = aws_iam_role.agentcore

  name   = "finance-traces"
  role   = each.value.id
  policy = data.aws_iam_policy_document.agentcore_traces.json
}

# -----------------------------------------------------------------------------
# X-Ray Transaction Search (reglages du compte)
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "xray_spans" {
  statement {
    sid     = "TransactionSearchXRayAccess"
    actions = ["logs:PutLogEvents"]
    principals {
      type        = "Service"
      identifiers = ["xray.amazonaws.com"]
    }
    resources = [
      "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:aws/spans:*",
      "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/application-signals/data:*",
    ]
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:xray:${var.aws_region}:${local.account_id}:*"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_cloudwatch_log_resource_policy" "xray_spans" {
  policy_name     = "${local.prefix}-xray-transaction-search"
  policy_document = data.aws_iam_policy_document.xray_spans.json
}

resource "aws_xray_trace_segment_destination" "this" {
  destination = "CloudWatchLogs"
  depends_on  = [aws_cloudwatch_log_resource_policy.xray_spans]
}

resource "aws_xray_indexing_rule" "default" {
  name = "Default"
  rule {
    probabilistic {
      desired_sampling_percentage = var.xray_indexing_percentage
    }
  }
  depends_on = [aws_xray_trace_segment_destination.this]
}
