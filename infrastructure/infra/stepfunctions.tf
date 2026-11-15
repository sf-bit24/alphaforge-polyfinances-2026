# =============================================================================
# Service : AWS Step Functions, collecte de la base generale.
#
#   Preparer -> Parallele [A4 presse | A5 donnees] -> A6 superviseur
#            -> Ingestion de la Knowledge Base -> Termine
#
# Chaque agent est un runtime AgentCore qui accepte sa tache aussitot, travaille
# en arriere-plan, puis ecrit staging/<run_id>/<role>/_done.json : la machine
# lance le runtime, puis sonde ce marqueur. Un appel synchrone serait borne
# par le delai d'attente des integrations SDK, alors qu'un agent de collecte
# travaille plusieurs minutes. Un collecteur en echec n'arrete pas la collecte
# (A6 traite ce qui est arrive) mais reste visible dans le graphe et la sortie.
#
# Entree : {"run_id"?: string, "since"?: "AAAA-MM-JJ", "tickers"?: [string]}
# (app/CONTRACTS.md, section 6). run_id vaut par defaut le nom de l'execution.
# =============================================================================

locals {
  collecte_name = "${local.prefix}-collecte"

  collecte_labels = {
    press      = "A4 presse"
    data       = "A5 donnees"
    supervisor = "A6 superviseur"
  }

  collecte_payloads = {
    press      = "{% $string($merge([{'action': 'collect', 'run_id': $runId}, $since ? {'since': $since} : {}, $tickers ? {'tickers': $tickers} : {}])) %}"
    data       = "{% $string($merge([{'action': 'collect', 'run_id': $runId}, $since ? {'since': $since} : {}, $tickers ? {'tickers': $tickers} : {}])) %}"
    supervisor = "{% $string({'action': 'curate', 'run_id': $runId}) %}"
  }

  collecte_max_polls = ceil(var.collecte_agent_timeout_seconds / var.collecte_poll_seconds)

  # A4 et A5 n'arretent pas la collecte : toute erreur d'une de leurs taches
  # finit leur branche par "<label> - echec", avec status=error. A6 est
  # indispensable : ses erreurs arretent l'execution, d'ou aucun Catch.
  # (jsonencode/jsondecode : HCL refuse un ?: entre deux objets de formes
  # differentes.)
  collecte_catch = {
    for role, label in local.collecte_labels : role => jsondecode(role == "supervisor" ? jsonencode({}) : jsonencode({
      Catch = [{
        ErrorEquals = ["States.ALL"]
        Output      = "{% {'status': 'error', 'role': '${role}', 'error': $states.errorOutput} %}"
        Next        = "${label} - echec"
      }]
    }))
  }

  # Etats "lancer le runtime, attendre, sonder le marqueur, le lire" d'un role.
  collecte_role_states = {
    for role, label in local.collecte_labels : role => {
      "${label} - lancer" = merge({
        Type     = "Task"
        Comment  = "Le runtime accepte la tache et travaille en arriere-plan."
        Resource = "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime"
        Arguments = {
          AgentRuntimeArn  = aws_bedrockagentcore_agent_runtime.this[role].agent_runtime_arn
          RuntimeSessionId = "{% $pad($runId & '-${role}', 48, '0') %}"
          ContentType      = "application/json"
          Accept           = "application/json"
          Payload          = local.collecte_payloads[role]
        }
        TimeoutSeconds = 120
        Retry = [{
          ErrorEquals     = ["BedrockAgentCore.ThrottlingException", "BedrockAgentCore.InternalServerException", "States.Timeout"]
          IntervalSeconds = 10
          MaxAttempts     = 3
          BackoffRate     = 2
        }]
        Assign = { attempts = 0 }
        Output = "{% $states.input %}"
        Next   = "${label} - attendre"
      }, local.collecte_catch[role])

      "${label} - attendre" = {
        Type    = "Wait"
        Seconds = var.collecte_poll_seconds
        Next    = "${label} - sonder"
      }

      # Lister plutot que lire : pour un objet absent, S3 ne repond NoSuchKey
      # qu'a qui detient ListBucket sans condition. Avec ListBucket limite a
      # staging/ (moindre privilege), un GetObject repondrait AccessDenied.
      "${label} - sonder" = merge({
        Type     = "Task"
        Comment  = "Le marqueur n'existe qu'une fois le travail fini."
        Resource = "arn:aws:states:::aws-sdk:s3:listObjectsV2"
        Arguments = {
          Bucket  = aws_s3_bucket.this.bucket
          Prefix  = "{% 'staging/' & $runId & '/${role}/_done.json' %}"
          MaxKeys = 1
        }
        Assign = { attempts = "{% $attempts + 1 %}" }
        Output = "{% {'found': $states.result.KeyCount > 0} %}"
        Next   = "${label} - present"
      }, local.collecte_catch[role])

      "${label} - present" = {
        Type = "Choice"
        Choices = [
          { Condition = "{% $states.input.found %}", Next = "${label} - lire" },
          { Condition = "{% $attempts < ${local.collecte_max_polls} %}", Next = "${label} - attendre" },
        ]
        Default = "${label} - delai depasse"
      }

      "${label} - lire" = merge({
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:s3:getObject"
        Arguments = {
          Bucket = aws_s3_bucket.this.bucket
          Key    = "{% 'staging/' & $runId & '/${role}/_done.json' %}"
        }
        Output = "{% $parse($states.result.Body) %}"
        Next   = "${label} - verifier"
      }, local.collecte_catch[role])

      "${label} - verifier" = {
        Type    = "Choice"
        Choices = [{ Condition = "{% $states.input.status = 'ok' %}", Next = "${label} - termine" }]
        Default = "${label} - echec"
      }

      "${label} - delai depasse" = jsondecode(role == "supervisor" ? jsonencode({
        Type  = "Fail"
        Error = "MarkerTimeout"
        Cause = "A6 n'a pas ecrit son marqueur dans le delai."
        }) : jsonencode({
        Type   = "Pass"
        Output = "{% {'status': 'error', 'role': '${role}', 'error': 'marqueur absent dans le delai'} %}"
        End    = true
      }))

      "${label} - echec" = jsondecode(role == "supervisor" ? jsonencode({
        Type  = "Fail"
        Error = "AgentError"
        Cause = "{% $string($states.input) %}"
        }) : jsonencode({
        Type   = "Pass"
        Output = "{% $states.input %}"
        End    = true
      }))

      "${label} - termine" = jsondecode(role == "supervisor" ? jsonencode({
        Type   = "Pass"
        Assign = { curated = "{% $states.input %}" }
        Next   = "Ingestion - lancer"
        }) : jsonencode({
        Type = "Pass"
        End  = true
      }))
    }
  }

  collecte_definition = {
    Comment        = "Collecte de la base generale AlphaForge AI : A4 et A5 en parallele, A6 valide et ecrit, puis ingestion de la Knowledge Base."
    QueryLanguage  = "JSONata"
    TimeoutSeconds = var.collecte_execution_timeout_seconds
    StartAt        = "Preparer"
    States = merge(
      {
        "Preparer" = {
          Type = "Pass"
          Assign = {
            runId   = "{% $exists($states.input.run_id) ? $states.input.run_id : $states.context.Execution.Name %}"
            since   = "{% $exists($states.input.since) ? $states.input.since : null %}"
            tickers = "{% $exists($states.input.tickers) ? $states.input.tickers : null %}"
          }
          Next = "Collecte"
        }

        "Collecte" = {
          Type    = "Parallel"
          Comment = "A4 et A5 collectent en meme temps, chacun dans sa session AgentCore."
          Branches = [
            { StartAt = "A4 presse - lancer", States = local.collecte_role_states.press },
            { StartAt = "A5 donnees - lancer", States = local.collecte_role_states.data },
          ]
          Assign = { collected = "{% {'press': $states.result[0], 'data': $states.result[1]} %}" }
          Next   = "A6 superviseur - lancer"
        }

        "Ingestion - lancer" = {
          Type     = "Task"
          Comment  = "Resynchronise general/ : documents d'A6 et methodologie poussee par Terraform."
          Resource = "arn:aws:states:::aws-sdk:bedrockagent:startIngestionJob"
          Arguments = {
            KnowledgeBaseId = aws_bedrockagent_knowledge_base.general.id
            DataSourceId    = aws_bedrockagent_data_source.general.data_source_id
            Description     = "{% 'Collecte ' & $runId %}"
          }
          Retry = [{
            ErrorEquals     = ["BedrockAgent.ConflictException", "BedrockAgent.ThrottlingException"]
            IntervalSeconds = 30
            MaxAttempts     = 10
            BackoffRate     = 1.5
          }]
          Assign = { ingestionJobId = "{% $states.result.IngestionJob.IngestionJobId %}" }
          Next   = "Ingestion - attendre"
        }

        "Ingestion - attendre" = {
          Type    = "Wait"
          Seconds = var.collecte_poll_seconds
          Next    = "Ingestion - sonder"
        }

        "Ingestion - sonder" = {
          Type     = "Task"
          Resource = "arn:aws:states:::aws-sdk:bedrockagent:getIngestionJob"
          Arguments = {
            KnowledgeBaseId = aws_bedrockagent_knowledge_base.general.id
            DataSourceId    = aws_bedrockagent_data_source.general.data_source_id
            IngestionJobId  = "{% $ingestionJobId %}"
          }
          Output = "{% $states.result.IngestionJob %}"
          Next   = "Ingestion - verifier"
        }

        "Ingestion - verifier" = {
          Type = "Choice"
          Choices = [
            { Condition = "{% $states.input.Status = 'COMPLETE' %}", Next = "Termine" },
            { Condition = "{% $states.input.Status in ['FAILED', 'STOPPED'] %}", Next = "Ingestion - echec" },
          ]
          Default = "Ingestion - attendre"
        }

        "Ingestion - echec" = {
          Type  = "Fail"
          Error = "IngestionFailed"
          Cause = "{% $string($states.input.FailureReasons) %}"
        }

        "Termine" = {
          Type   = "Succeed"
          Output = "{% {'run_id': $runId, 'collected': $collected, 'curated': $curated, 'ingestion': {'job_id': $ingestionJobId, 'status': $states.input.Status, 'statistics': $states.input.Statistics}} %}"
        }
      },
      local.collecte_role_states.supervisor,
    )
  }
}

# -----------------------------------------------------------------------------
# Journaux d'execution, chiffres par une cle du projet.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "logs_key" {
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
    sid    = "CloudWatchLogs"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["logs.${var.aws_region}.amazonaws.com"]
    }
    actions   = ["kms:Encrypt*", "kms:Decrypt*", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
    resources = ["*"]
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      # Plus le groupe des jobs SageMaker des scenarios (scenarios.tf).
      values = concat(
        ["arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/aws/vendedlogs/states/${local.prefix}-*"],
        local.scenarios_kms_log_group_arns,
      )
    }
  }
}

resource "aws_kms_key" "logs" {
  description             = "${local.prefix} : journaux CloudWatch de la pile"
  enable_key_rotation     = true
  deletion_window_in_days = local.kms_deletion_window_in_days
  policy                  = data.aws_iam_policy_document.logs_key.json
  tags                    = local.common_tags
}

resource "aws_kms_alias" "logs" {
  name          = "alias/${local.prefix}-logs"
  target_key_id = aws_kms_key.logs.key_id
}

resource "aws_cloudwatch_log_group" "collecte" {
  name              = "/aws/vendedlogs/states/${local.collecte_name}"
  retention_in_days = 14
  kms_key_id        = aws_kms_key.logs.arn
  tags              = local.common_tags
}

# -----------------------------------------------------------------------------
# Role de la machine : appeler les trois collecteurs, lire leurs marqueurs,
# lancer et suivre l'ingestion, journaliser.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "collecte_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:states:${var.aws_region}:${local.account_id}:stateMachine:${local.prefix}-*"]
    }
  }
}

resource "aws_iam_role" "collecte" {
  name               = "${local.prefix}-collecte"
  description        = "Role de la machine Step Functions de collecte."
  assume_role_policy = data.aws_iam_policy_document.collecte_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "collecte" {
  statement {
    sid     = "InvokeCollectors"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = flatten([
      for role in keys(local.collecte_labels) : [
        aws_bedrockagentcore_agent_runtime.this[role].agent_runtime_arn,
        "${aws_bedrockagentcore_agent_runtime.this[role].agent_runtime_arn}/*",
      ]
    ])
  }

  # Sonde des marqueurs (listObjectsV2), limitee a staging/.
  statement {
    sid       = "ListStaging"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.this.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["staging/*"]
    }
  }

  statement {
    sid       = "ReadMarkers"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.this.arn}/staging/*"]
  }

  statement {
    sid       = "Ingestion"
    actions   = ["bedrock:StartIngestionJob", "bedrock:GetIngestionJob"]
    resources = [aws_bedrockagent_knowledge_base.general.arn]
  }

  statement {
    sid = "LogDelivery"
    actions = [
      "logs:CreateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:DescribeLogGroups",
      "logs:DescribeResourcePolicies",
      "logs:GetLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:UpdateLogDelivery",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "Tracing"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "collecte" {
  name   = "collecte"
  role   = aws_iam_role.collecte.id
  policy = data.aws_iam_policy_document.collecte.json
}

resource "aws_sfn_state_machine" "collecte" {
  name       = local.collecte_name
  role_arn   = aws_iam_role.collecte.arn
  definition = jsonencode(local.collecte_definition)

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.collecte.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = local.common_tags

  depends_on = [aws_iam_role_policy.collecte]
}
