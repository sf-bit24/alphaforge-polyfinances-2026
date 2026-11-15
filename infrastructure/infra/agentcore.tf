# =============================================================================
# Service : Bedrock AgentCore Runtime.
#
# Un seul zip de code Python (app/agents, linux/arm64, PYTHON_3_13), deploye
# directement depuis S3 sans image de conteneur, alimente quatre runtimes qui
# ne different que par AGENT_ROLE et par leur role IAM (moindre privilege) :
#
#   profile     questions de base deterministes, relances A1, portefeuille
#               existant A2 ; appele par l'interface locale
#   press       A4, specialiste de la presse ; appele par Step Functions
#   data        A5, specialiste des donnees ; appele par Step Functions
#   supervisor  A6, superviseur de la base generale ; appele par Step Functions
#   router      A0, routeur et redacteur des questions de recherche ; appele
#               par la machine recherche (recherche.tf)
#   expert      E1 a E7, experts de sujet ; appele par la machine recherche,
#               lance lui-meme ses chercheurs (InvokeAgentRuntime)
#   researcher  sous-agent de recherche, une session par mission ; appele par
#               les experts seulement
#
# Le contrat des requetes et des reponses est dans app/CONTRACTS.md.
# =============================================================================

locals {
  # Acces S3 de chaque role, en motifs de cles (app/CONTRACTS.md, section 1) :
  #   s3_read   GetObject (et HeadObject)
  #   s3_write  PutObject, ecritures conditionnelles comprises
  #   s3_list   valeurs permises de s3:prefix pour ListBucket. Le magasin
  #             Python liste aussi la cle exacte pour distinguer un objet
  #             absent d'un refus, S3 repondant 403 a un GetObject d'objet
  #             absent quand ListBucket est conditionne.
  # A6 n'ecrit jamais general/methodologie/, geree par Terraform.
  # Si scenarios_enabled, profile lit aussi la table precalculee des scenarios
  # (outil scenario_risk, scenarios.tf ; pas encore branche dans le runtime),
  # en lecture seule : scenarios/latest.json et scenarios/output/, jamais le
  # code ni les entrees du job. Sinon, aucun droit sous scenarios/.
  agentcore_profile_scenarios_keys = var.scenarios_enabled ? ["scenarios/latest.json", "scenarios/output/*"] : []

  agentcore_runtimes = {
    profile = {
      description    = "Profil investisseur : questions de base deterministes, relances A1, portefeuille existant A2."
      s3_read        = concat(["general/*", "clients/*"], local.agentcore_profile_scenarios_keys)
      s3_write       = ["clients/*"]
      s3_list        = concat(["general/*", "clients/*"], local.agentcore_profile_scenarios_keys)
      knowledge_base = true
      guardrail      = true
    }
    press = {
      description    = "A4, specialiste de la presse : collecte datee d'actualites dans staging/."
      s3_read        = ["staging/*/press/*"]
      s3_write       = ["staging/*/press/*"]
      s3_list        = ["staging/*/press/*"]
      knowledge_base = false
      guardrail      = false
    }
    data = {
      description    = "A5, specialiste des donnees : series et cours dates dans staging/."
      s3_read        = ["staging/*/data/*"]
      s3_write       = ["staging/*/data/*"]
      s3_list        = ["staging/*/data/*"]
      knowledge_base = false
      guardrail      = false
    }
    # A6 relit aussi archive/ : chaque valeur d'un expert y est verifiee avant
    # d'ecrire faits, signaux, depots et syntheses (recherche.tf).
    supervisor = {
      description = "A6, superviseur OKF : valide staging/ et ecrit la base generale."
      s3_read     = ["staging/*", "general/*", "archive/*"]
      s3_write = [
        "staging/*/supervisor/*", "general/actualites/*", "general/donnees/*", "general/index.md",
        "general/faits/*", "general/signaux/*", "general/depots/*", "general/recherches/*",
      ]
      s3_list        = ["staging/*", "general/*", "archive/*"]
      knowledge_base = false
      guardrail      = false
    }
    # Recherche par experts (recherche.tf, app/CONTRACTS.md section 11).
    router = {
      description    = "A0 : routage des questions de recherche et synthese finale."
      s3_read        = ["staging/*/router/*", "staging/*/experts/*"]
      s3_write       = ["staging/*/router/*"]
      s3_list        = ["staging/*/router/*", "staging/*/experts/*"]
      knowledge_base = false
      guardrail      = false
    }
    expert = {
      description    = "E1 a E7 : experts de sujet ; lancent n chercheurs, une session chacun."
      s3_read        = ["staging/*/experts/*", "staging/*/researchers/*"]
      s3_write       = ["staging/*/experts/*"]
      s3_list        = ["staging/*/experts/*", "staging/*/researchers/*"]
      knowledge_base = true
      guardrail      = false
    }
    researcher = {
      description    = "Chercheur : une mission par session, lit les hotes de ses paquets et archive chaque reponse."
      s3_read        = ["staging/*/researchers/*"]
      s3_write       = ["staging/*/researchers/*", "archive/*"]
      s3_list        = ["staging/*/researchers/*"]
      knowledge_base = false
      guardrail      = false
    }
  }

  # Profil d'inference inter-regions (us.) et modele de fondation qu'il route.
  agentcore_foundation_model_id = replace(var.agentcore_model_id, "/^(us|global)\\./", "")

  agentcore_common_env = {
    ALPHAFORGE_ENV      = var.environment
    ALPHAFORGE_RELEASE  = var.release_id
    ALPHAFORGE_REGION   = var.aws_region
    ALPHAFORGE_STORE    = "s3"
    ALPHAFORGE_BUCKET   = aws_s3_bucket.this.bucket
    ALPHAFORGE_MODEL_ID = var.agentcore_model_id
  }

  agentcore_profile_env = {
    ALPHAFORGE_KB_ID             = aws_bedrockagent_knowledge_base.general.id
    ALPHAFORGE_GUARDRAIL_ID      = aws_bedrock_guardrail.cadre.guardrail_id
    ALPHAFORGE_GUARDRAIL_VERSION = aws_bedrock_guardrail_version.cadre.version
  }

  # Variables propres a un role, fusionnees apres les variables communes.
  agentcore_role_env = {
    profile = local.agentcore_profile_env
    expert  = merge({ ALPHAFORGE_KB_ID = aws_bedrockagent_knowledge_base.general.id }, local.recherche_expert_env)
  }
}

# Code des runtimes. La cle porte le SHA du commit : un nouvel objet par
# commit, et la modification de agent_runtime_artifact met a jour les quatre
# runtimes.
resource "aws_s3_object" "agents_code" {
  bucket       = aws_s3_bucket.this.id
  key          = "runtime/agents-${var.release_id}.zip"
  source       = "${path.module}/build/agents.zip"
  content_type = "application/zip"

  depends_on = [aws_s3_bucket_server_side_encryption_configuration.this]

  # Nouveau zip d'abord, mise a jour des runtimes, puis suppression de
  # l'ancien : aucun runtime ne pointe vers un objet supprime.
  lifecycle {
    create_before_destroy = true
  }
}

data "aws_iam_policy_document" "agentcore_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:bedrock-agentcore:${var.aws_region}:${local.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "agentcore" {
  for_each = local.agentcore_runtimes

  name               = "${local.prefix}-agentcore-${each.key}"
  description        = "Role d'execution du runtime AgentCore ${each.key}."
  assume_role_policy = data.aws_iam_policy_document.agentcore_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "agentcore" {
  for_each = local.agentcore_runtimes

  statement {
    sid       = "RuntimeLogGroups"
    actions   = ["logs:CreateLogGroup", "logs:DescribeLogStreams"]
    resources = ["arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"]
  }

  # Present dans le role d'execution documente par AWS pour le deploiement
  # direct du code ; limite aux groupes du runtime.
  statement {
    sid       = "RuntimeLogResourcePolicy"
    actions   = ["logs:PutResourcePolicy"]
    resources = ["arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/bedrock-agentcore/runtimes/${local.name_snake}_${each.key}-*"]
  }

  statement {
    sid       = "DescribeLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:*"]
  }

  statement {
    sid       = "RuntimeLogStreams"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"]
  }

  statement {
    sid       = "Tracing"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"]
    resources = ["*"]
  }

  statement {
    sid       = "Metrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }

  statement {
    sid = "WorkloadIdentity"
    actions = [
      "bedrock-agentcore:GetWorkloadAccessToken",
      "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
      "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
    ]
    resources = [
      "arn:${local.partition}:bedrock-agentcore:${var.aws_region}:${local.account_id}:workload-identity-directory/default",
      "arn:${local.partition}:bedrock-agentcore:${var.aws_region}:${local.account_id}:workload-identity-directory/default/workload-identity/${local.name_snake}_${each.key}-*",
    ]
  }

  # Un seul modele pour tous les agents ; le profil us. route vers les regions
  # americaines, d'ou le joker de region sur le modele de fondation.
  statement {
    sid     = "InvokeModel"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [
      "arn:${local.partition}:bedrock:${var.aws_region}:${local.account_id}:inference-profile/${var.agentcore_model_id}",
      "arn:${local.partition}:bedrock:*::foundation-model/${local.agentcore_foundation_model_id}",
    ]
  }

  statement {
    sid       = "RuntimeCode"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.this.arn}/runtime/*"]
  }

  statement {
    sid       = "ListOwnPrefixes"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.this.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = each.value.s3_list
    }
  }

  statement {
    sid       = "ReadObjects"
    actions   = ["s3:GetObject"]
    resources = [for k in each.value.s3_read : "${aws_s3_bucket.this.arn}/${k}"]
  }

  statement {
    sid       = "WriteObjects"
    actions   = ["s3:PutObject"]
    resources = [for k in each.value.s3_write : "${aws_s3_bucket.this.arn}/${k}"]
  }

  dynamic "statement" {
    for_each = each.value.knowledge_base ? [1] : []
    content {
      sid       = "RetrieveGeneralKnowledge"
      actions   = ["bedrock:Retrieve"]
      resources = [aws_bedrockagent_knowledge_base.general.arn]
    }
  }

  dynamic "statement" {
    for_each = each.value.guardrail ? [1] : []
    content {
      sid       = "ApplyGuardrail"
      actions   = ["bedrock:ApplyGuardrail"]
      resources = [aws_bedrock_guardrail.cadre.guardrail_arn]
    }
  }
}

resource "aws_iam_role_policy" "agentcore" {
  for_each = local.agentcore_runtimes

  name   = "runtime"
  role   = aws_iam_role.agentcore[each.key].id
  policy = data.aws_iam_policy_document.agentcore[each.key].json
}

resource "aws_bedrockagentcore_agent_runtime" "this" {
  for_each = local.agentcore_runtimes

  agent_runtime_name = "${local.name_snake}_${each.key}"
  description        = each.value.description
  role_arn           = aws_iam_role.agentcore[each.key].arn

  agent_runtime_artifact {
    code_configuration {
      entry_point = ["main.py"]
      runtime     = "PYTHON_3_13"
      code {
        s3 {
          bucket = aws_s3_bucket.this.bucket
          prefix = aws_s3_object.agents_code.key
        }
      }
    }
  }

  environment_variables = merge(
    local.agentcore_common_env,
    { AGENT_ROLE = each.key },
    try(local.agentcore_role_env[each.key], {}),
  )

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  # Une session par investisseur : elle garde sa microVM tant qu'elle sert.
  # Les collecteurs travaillent en tache asynchrone (/ping HealthyBusy).
  lifecycle_configuration {
    idle_runtime_session_timeout = var.agentcore_idle_session_timeout
    max_lifetime                 = var.agentcore_max_session_lifetime
  }

  tags = local.common_tags

  # AgentCore verifie le role a la creation : ses permissions d'abord.
  depends_on = [aws_iam_role_policy.agentcore]
}
