# =============================================================================
# Service : Knowledge Base de chaque client (une par investisseur).
#
# La base OKF clients/<id>/ reste la source de verite : le code y lit toujours
# les valeurs exactes. La Knowledge Base du client n'est qu'un index de
# recherche construit a partir de ses documents, propre au client (une base et
# un index S3 Vectors chacun : aucun filtre de metadonnees a oublier).
#
# Les Knowledge Bases et les index des clients ne sont pas dans l'etat
# Terraform : le runtime profile les cree a la premiere action d'un client
# (app/agents/src/alphaforge/profile/client_kb.py), etiquetes
# alphaforge:scope=client, et scripts/clean-client-kbs.sh les liste et les
# supprime (--dry-run par defaut). Terraform pose le socle commun :
#   - le bucket de vecteurs des clients, chiffre par une cle du projet : les
#     vecteurs portent le texte des passages, donc des donnees client ;
#   - le role de service des Knowledge Bases des clients ;
#   - les droits des runtimes profile (creation, ingestion, recherche) et
#     portfolio (ingestion et recherche seulement), dans agentcore.tf.
#
# Ingestion directe (IngestKnowledgeBaseDocuments, source CUSTOM, document en
# ligne) : pas de StartIngestionJob, limite a 0,1 requete par seconde pour le
# compte et deja pris par la collecte ; pas de lecture S3 pour ce role.
#
# Quota du compte : 100 Knowledge Bases, non ajustable, dont une prise par la
# base generale. Au-dela, le runtime range l'etat quota et le questionnaire
# continue sans base de recherche.
# =============================================================================

locals {
  client_kb_vector_bucket_name = "${local.prefix}-client-vectors"
  client_kb_index_arn_pattern  = "arn:${local.partition}:s3vectors:${var.aws_region}:${local.account_id}:bucket/${local.client_kb_vector_bucket_name}/index/client-*"
  client_kb_arn_pattern        = "arn:${local.partition}:bedrock:${var.aws_region}:${local.account_id}:knowledge-base/*"

  # Runtimes qui creent les Knowledge Bases des clients, et ceux qui y ingerent
  # et y cherchent (agentcore.tf).
  client_kb_creator_roles = ["profile"]
  client_kb_user_roles    = ["profile", "portfolio"]

  # Variables lues par alphaforge/config.py ; vides, la fonction est desactivee
  # et le runtime se comporte comme avant (aucun appel, aucun kb.json).
  client_kb_env = var.client_kb_enabled ? {
    ALPHAFORGE_CLIENT_KB_VECTOR_BUCKET        = aws_s3vectors_vector_bucket.clients.vector_bucket_name
    ALPHAFORGE_CLIENT_KB_ROLE_ARN             = aws_iam_role.client_knowledge_base.arn
    ALPHAFORGE_CLIENT_KB_PREFIX               = local.prefix
    ALPHAFORGE_CLIENT_KB_EMBEDDING_MODEL_ARN  = local.bedrock_embedding_model_arn
    ALPHAFORGE_CLIENT_KB_EMBEDDING_DIMENSIONS = tostring(var.bedrock_embedding_dimensions)
  } : {}
}

# -----------------------------------------------------------------------------
# Cle KMS des vecteurs des clients. Comme les autres cles du projet (kms.tf),
# sa politique nomme ses principaux et ne delegue pas a IAM : le role des
# Knowledge Bases des clients et le runtime profile (creation des index) par
# S3 Vectors seulement, et le principal de service de S3 Vectors, qui
# maintient les index en tache de fond.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "client_vectors_key" {
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
    sid    = "VectorUsersViaS3Vectors"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.client_knowledge_base.arn, aws_iam_role.agentcore["profile"].arn]
    }
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3vectors.${var.aws_region}.amazonaws.com"]
    }
  }

  statement {
    sid    = "S3VectorsIndexing"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["indexing.s3vectors.amazonaws.com"]
    }
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:s3vectors:${var.aws_region}:${local.account_id}:bucket/${local.client_kb_vector_bucket_name}*"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ForAnyValue:StringEquals"
      variable = "kms:EncryptionContextKeys"
      values   = ["aws:s3vectors:arn", "aws:s3vectors:resource-id"]
    }
  }
}

resource "aws_kms_key" "client_vectors" {
  description             = "${local.prefix} : vecteurs des Knowledge Bases des clients"
  enable_key_rotation     = true
  deletion_window_in_days = local.kms_deletion_window_in_days
  policy                  = data.aws_iam_policy_document.client_vectors_key.json
  tags                    = local.common_tags
}

resource "aws_kms_alias" "client_vectors" {
  name          = "alias/${local.prefix}-client-vectors"
  target_key_id = aws_kms_key.client_vectors.key_id
}

# Un index client-<client_id> par investisseur, cree par le runtime profile ;
# il herite du chiffrement du bucket. force_destroy : compte jetable, un
# destroy emporte les index restants (lancer d'abord clean-client-kbs.sh pour
# supprimer aussi les Knowledge Bases qui les lisent).
resource "aws_s3vectors_vector_bucket" "clients" {
  vector_bucket_name = local.client_kb_vector_bucket_name
  force_destroy      = true

  encryption_configuration = [{
    sse_type    = "aws:kms"
    kms_key_arn = aws_kms_key.client_vectors.arn
  }]

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# Role de service des Knowledge Bases des clients : memes conditions de
# confiance que celui de la base generale (bedrock.tf), embeddings et vecteurs
# des seuls index client-* de ce bucket. KMS : accorde par la politique de la
# cle ci-dessus. Aucune lecture S3 : les documents arrivent en ligne.
# -----------------------------------------------------------------------------
resource "aws_iam_role" "client_knowledge_base" {
  name               = "${local.prefix}-client-knowledge-base"
  description        = "Role de service des Knowledge Bases des clients (une par investisseur)."
  assume_role_policy = data.aws_iam_policy_document.knowledge_base_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "client_knowledge_base" {
  statement {
    sid       = "Embeddings"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.bedrock_embedding_model_arn]
  }

  statement {
    sid = "ClientVectors"
    actions = [
      "s3vectors:DeleteVectors",
      "s3vectors:GetIndex",
      "s3vectors:GetVectors",
      "s3vectors:PutVectors",
      "s3vectors:QueryVectors",
    ]
    resources = [local.client_kb_index_arn_pattern]
  }
}

resource "aws_iam_role_policy" "client_knowledge_base" {
  name   = "client-knowledge-base"
  role   = aws_iam_role.client_knowledge_base.id
  policy = data.aws_iam_policy_document.client_knowledge_base.json
}
