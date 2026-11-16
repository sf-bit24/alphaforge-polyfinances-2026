# =============================================================================
# Service : Amazon Bedrock, Knowledge Base et Guardrail.
#
# Knowledge Base : indexe la base generale OKF (general/ du bucket, et rien
# d'autre : elle reste sans aucune donnee client) dans S3 Vectors, avec
# Titan Text Embeddings V2. A1 l'interroge (Retrieve) pour expliquer un terme ;
# Step Functions relance l'ingestion apres chaque collecte.
#
# Chaque client a sa propre Knowledge Base, creee par le runtime profile et
# hors de l'etat Terraform, dans un bucket de vecteurs a part chiffre par une
# cle du projet (client_kb.tf) : memes reglages d'embedding et de decoupage.
#
# Guardrail : le cadre responsable de l'enonce (simulation seulement, aucune
# transaction reelle, aucun renseignement bancaire confidentiel), applique
# par le runtime profile aux entrees et sorties d'A1 et A2.
# =============================================================================

locals {
  bedrock_embedding_model_arn = "arn:${local.partition}:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model_id}"
}

# Les vecteurs ne portent que la base generale, publique : chiffrement SSE-S3
# par defaut, sans cle du projet.
resource "aws_s3vectors_vector_bucket" "general" {
  vector_bucket_name = "${local.prefix}-vectors"
  force_destroy      = true
  tags               = local.common_tags
}

resource "aws_s3vectors_index" "general" {
  index_name         = "general"
  vector_bucket_name = aws_s3vectors_vector_bucket.general.vector_bucket_name
  data_type          = "float32"
  dimension          = var.bedrock_embedding_dimensions
  distance_metric    = "cosine"

  # Bedrock range le texte des passages et leurs metadonnees dans ces cles ;
  # filtrables, elles depasseraient la limite de 2 Ko par vecteur.
  metadata_configuration {
    non_filterable_metadata_keys = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
  }

  tags = local.common_tags
}

data "aws_iam_policy_document" "knowledge_base_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:bedrock:${var.aws_region}:${local.account_id}:knowledge-base/*"]
    }
  }
}

resource "aws_iam_role" "knowledge_base" {
  name               = "${local.prefix}-knowledge-base"
  description        = "Role de la Knowledge Base de la base generale."
  assume_role_policy = data.aws_iam_policy_document.knowledge_base_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "knowledge_base" {
  statement {
    sid       = "Embeddings"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.bedrock_embedding_model_arn]
  }

  statement {
    sid       = "ListGeneral"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.this.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["general/*"]
    }
  }

  statement {
    sid       = "ReadGeneral"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.this.arn}/general/*"]
  }

  statement {
    sid = "Vectors"
    actions = [
      "s3vectors:DeleteVectors",
      "s3vectors:GetIndex",
      "s3vectors:GetVectors",
      "s3vectors:PutVectors",
      "s3vectors:QueryVectors",
    ]
    resources = [aws_s3vectors_index.general.index_arn]
  }
}

resource "aws_iam_role_policy" "knowledge_base" {
  name   = "knowledge-base"
  role   = aws_iam_role.knowledge_base.id
  policy = data.aws_iam_policy_document.knowledge_base.json
}

resource "aws_bedrockagent_knowledge_base" "general" {
  name        = "${local.prefix}-general"
  description = "Base generale OKF d'AlphaForge AI : methodologie, actualites et donnees datees par leur publication."
  role_arn    = aws_iam_role.knowledge_base.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = local.bedrock_embedding_model_arn
      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = var.bedrock_embedding_dimensions
          embedding_data_type = "FLOAT32"
        }
      }
    }
  }

  storage_configuration {
    type = "S3_VECTORS"
    s3_vectors_configuration {
      index_arn = aws_s3vectors_index.general.index_arn
    }
  }

  tags = local.common_tags

  # La Knowledge Base verifie l'acces de son role a la creation.
  depends_on = [aws_iam_role_policy.knowledge_base]
}

resource "aws_bedrockagent_data_source" "general" {
  name                 = "${local.prefix}-general-okf"
  description          = "Documents OKF sous general/ (frontmatter YAML puis Markdown)."
  knowledge_base_id    = aws_bedrockagent_knowledge_base.general.id
  data_deletion_policy = "DELETE"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn         = aws_s3_bucket.this.arn
      inclusion_prefixes = ["general/"]
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 400
        overlap_percentage = 15
      }
    }
  }
}

# -----------------------------------------------------------------------------
# Guardrail du cadre responsable (niveau CLASSIC : francais et anglais).
# -----------------------------------------------------------------------------
resource "aws_bedrock_guardrail" "cadre" {
  name        = "${local.prefix}-cadre"
  description = "Cadre responsable de l'enonce AlphaForge AI : simulation seulement, aucune transaction reelle, aucun renseignement bancaire confidentiel."

  blocked_input_messaging   = "Cette demande sort du cadre d'AlphaForge AI : simulation seulement, sans transaction réelle ni renseignement bancaire confidentiel. / This request is outside AlphaForge AI's scope: simulation only, no real transactions or confidential banking information."
  blocked_outputs_messaging = "Je ne peux pas fournir cette réponse dans le cadre d'AlphaForge AI (simulation seulement). / I can't provide this answer within AlphaForge AI (simulation only)."

  content_policy_config {
    filters_config {
      type            = "HATE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "SEXUAL"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "VIOLENCE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "MISCONDUCT"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    # Le filtre d'attaque de prompt ne s'applique qu'aux entrees.
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
    tier_config {
      tier_name = "CLASSIC"
    }
  }

  topic_policy_config {
    topics_config {
      name = "transactions-reelles"
      type = "DENY"
      # Niveau CLASSIC : 200 caracteres au plus.
      definition = "Demande d'executer ou de programmer un ordre reel d'achat ou de vente, ou un virement, sur un compte reel. Decrire des placements passes ou un scenario fictif n'en fait pas partie."
      examples = [
        "Achète 100 actions de NVDA dans mon compte de courtage.",
        "Passe un ordre de vente sur mes actions Shopify maintenant.",
        "Transfère 5 000 $ de mon compte bancaire vers mon CELI.",
        "Buy 10 shares of Tesla in my brokerage account for me.",
      ]
    }
    topics_config {
      name       = "garantie-rendement"
      type       = "DENY"
      definition = "Promettre ou garantir un rendement, un gain ou l'absence de perte sur un placement."
      examples = [
        "Ce portefeuille vous garantit 12 % par an sans aucun risque.",
        "Avec cette strategie, vous ne pouvez pas perdre d'argent.",
      ]
    }
    topics_config {
      name       = "conseil-personnalise-reel"
      type       = "DENY"
      definition = "Presenter une recommandation comme un conseil financier reel, reglemente et personnalise, a suivre tel quel."
      examples = [
        "C'est mon conseil officiel : achetez exactement 300 actions de TSLA demain.",
      ]
    }
    tier_config {
      tier_name = "CLASSIC"
    }
  }

  # Ancrage contextuel : evalue seulement quand une source d'ancrage est fournie (verification des
  # explications du volet finance) ; sans source, il ne s'applique pas (verifie le 2026-11-14).
  contextual_grounding_policy_config {
    filters_config {
      type      = "GROUNDING"
      threshold = 0.75
    }
    filters_config {
      type      = "RELEVANCE"
      threshold = 0.1
    }
  }

  # Un releve de courtage colle par l'investisseur contient souvent un numero
  # de compte : on ne bloque pas l'entree, mais une sortie ne le repete jamais.
  sensitive_information_policy_config {
    pii_entities_config {
      type           = "CA_SOCIAL_INSURANCE_NUMBER"
      action         = "BLOCK"
      input_action   = "BLOCK"
      output_action  = "BLOCK"
      input_enabled  = true
      output_enabled = true
    }
    # Le NAS ecrit avec espaces ou tirets (« 046 454 286 ») echappe au filtre gere : regex.
    # Separateurs obligatoires : sans eux, la regex bloquait les bornes du questionnaire
    # (« max: 100000000 ») dans le contexte d'A1 ; 9 chiffres colles restent au filtre gere.
    regexes_config {
      name           = "nas-canadien"
      description    = "NAS canadien ecrit en 3 groupes de 3 chiffres separes par espace ou tiret"
      pattern        = "\\b\\d{3}[ -]\\d{3}[ -]\\d{3}\\b"
      action         = "BLOCK"
      input_action   = "BLOCK"
      output_action  = "BLOCK"
      input_enabled  = true
      output_enabled = true
    }
    pii_entities_config {
      type           = "CA_HEALTH_NUMBER"
      action         = "BLOCK"
      input_action   = "BLOCK"
      output_action  = "BLOCK"
      input_enabled  = true
      output_enabled = true
    }
    pii_entities_config {
      type           = "CREDIT_DEBIT_CARD_NUMBER"
      action         = "BLOCK"
      input_action   = "BLOCK"
      output_action  = "BLOCK"
      input_enabled  = true
      output_enabled = true
    }
    pii_entities_config {
      type           = "PASSWORD"
      action         = "BLOCK"
      input_action   = "BLOCK"
      output_action  = "BLOCK"
      input_enabled  = true
      output_enabled = true
    }
    pii_entities_config {
      type           = "PIN"
      action         = "BLOCK"
      input_action   = "BLOCK"
      output_action  = "BLOCK"
      input_enabled  = true
      output_enabled = true
    }
    pii_entities_config {
      type           = "US_BANK_ACCOUNT_NUMBER"
      action         = "ANONYMIZE"
      input_action   = "NONE"
      output_action  = "ANONYMIZE"
      input_enabled  = false
      output_enabled = true
    }
    pii_entities_config {
      type           = "INTERNATIONAL_BANK_ACCOUNT_NUMBER"
      action         = "ANONYMIZE"
      input_action   = "NONE"
      output_action  = "ANONYMIZE"
      input_enabled  = false
      output_enabled = true
    }
    pii_entities_config {
      type           = "EMAIL"
      action         = "ANONYMIZE"
      input_action   = "NONE"
      output_action  = "ANONYMIZE"
      input_enabled  = false
      output_enabled = true
    }
    pii_entities_config {
      type           = "PHONE"
      action         = "ANONYMIZE"
      input_action   = "NONE"
      output_action  = "ANONYMIZE"
      input_enabled  = false
      output_enabled = true
    }
    pii_entities_config {
      type           = "ADDRESS"
      action         = "ANONYMIZE"
      input_action   = "NONE"
      output_action  = "ANONYMIZE"
      input_enabled  = false
      output_enabled = true
    }
  }

  tags = local.common_tags
}

# Version figee lue par le runtime ; une nouvelle version suit chaque
# modification du guardrail, l'ancienne reste pour les sessions en cours.
resource "aws_bedrock_guardrail_version" "cadre" {
  guardrail_arn = aws_bedrock_guardrail.cadre.guardrail_arn
  description   = "Version deployee par Terraform (${var.release_id})."
  skip_destroy  = true

  lifecycle {
    replace_triggered_by = [aws_bedrock_guardrail.cadre]
    ignore_changes       = [description]
  }
}
