# =============================================================================
# Service : S3, magasin des bases OKF (bucket prive, versionne, chiffre par une
# cle KMS du projet).
#
#   general/    base generale (methodologie versionnee, actualites et donnees
#               ecrites par A6), seule source de la Knowledge Base
#   clients/    une base OKF par investisseur, ecrite par le runtime profile
#   staging/    collecte brute d'A4 et A5, marqueurs _done.json, expire
#   runtime/    zip du code des runtimes AgentCore, un objet par commit
#   scenarios/  code, entrees et sorties du job des scenarios (scenarios.tf),
#               hors general/ : jamais indexe par la Knowledge Base
#
# Rien n'y vit seulement : la base generale de depart est versionnee dans
# app/knowledge/, et les bases des clients s'exportent vers le poste avant la
# fermeture du compte (voir le README racine).
# =============================================================================

# Roles qui lisent ou ecrivent des objets : ils doivent figurer dans la key
# policy (la cle ne delegue pas a IAM, faute de principal root).
locals {
  s3_kms_user_role_arns = concat(
    [for role in aws_iam_role.agentcore : role.arn],
    [aws_iam_role.knowledge_base.arn, aws_iam_role.collecte.arn],
    local.tldoole_kms_user_role_arns,
    # Scenarios (scenarios.tf) : job SageMaker et machine Step Functions.
    aws_iam_role.scenarios_job[*].arn,
    aws_iam_role.scenarios[*].arn,
  )
}

data "aws_iam_policy_document" "s3_key" {
  statement {
    sid    = "KeyAdministration"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = local.kms_admin_principal_arns
    }
    actions   = local.kms_admin_actions
    resources = ["*"]
  }

  statement {
    sid    = "BucketUsersViaS3"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = local.s3_kms_user_role_arns
    }
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_kms_key" "s3" {
  description             = "${local.prefix} : objets du bucket des bases OKF"
  enable_key_rotation     = true
  deletion_window_in_days = local.kms_deletion_window_in_days
  policy                  = data.aws_iam_policy_document.s3_key.json
  tags                    = local.common_tags
}

resource "aws_kms_alias" "s3" {
  name          = "alias/${local.prefix}-s3"
  target_key_id = aws_kms_key.s3.key_id
}

resource "aws_s3_bucket" "this" {
  # Le nom d'un bucket est global : l'ID du compte le rend unique.
  bucket = "${local.prefix}-${var.s3_bucket_name}-${local.account_id}"
  # Compte jetable : un destroy vide le bucket au lieu d'echouer.
  force_destroy = true
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = var.s3_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
    bucket_key_enabled = true
  }
}

data "aws_iam_policy_document" "s3_bucket" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    resources = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id
  policy = data.aws_iam_policy_document.s3_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.this]
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    id     = "staging-expire"
    status = "Enabled"
    filter {
      prefix = "staging/"
    }
    expiration {
      days = var.s3_staging_expiration_days
    }
  }

  # Resultats des requetes Athena (scenarios.tf) : jetables. Seulement si
  # scenarios_enabled, pour que false laisse le bucket inchange.
  dynamic "rule" {
    for_each = var.scenarios_enabled ? ["athena-results-expire"] : []
    content {
      id     = rule.value
      status = "Enabled"
      filter {
        prefix = "scenarios/athena-results/"
      }
      expiration {
        days = 7
      }
    }
  }

  rule {
    id     = "noncurrent-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  depends_on = [aws_s3_bucket_versioning.this]
}

# Base generale de depart (methodologie, notions, societes), versionnee dans app/knowledge/general
# et copiee dans infra/build/knowledge/ par le job package_agents. Les
# documents ecrits par A6 vivent sous d'autres prefixes (actualites/,
# donnees/) et ne sont pas geres par Terraform.
resource "aws_s3_object" "knowledge_seed" {
  for_each = fileset("${path.module}/build/knowledge", "**/*.md")

  bucket       = aws_s3_bucket.this.id
  key          = "general/${each.value}"
  source       = "${path.module}/build/knowledge/${each.value}"
  source_hash  = filemd5("${path.module}/build/knowledge/${each.value}")
  content_type = "text/markdown; charset=utf-8"

  depends_on = [aws_s3_bucket_server_side_encryption_configuration.this]
}
