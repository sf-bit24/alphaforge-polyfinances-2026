# =============================================================================
# Service : AWS Step Functions, evolution du portefeuille dans le temps
# (simulation seulement, issue #29).
#
#   Preparer -> Mode
#     mode replay : Rejeu (runtime portfolio, action evolution.replay)
#                   -> sonde staging/<run_id>/evolution/replay/_done.json
#     mode tick   : Mois (Map INLINE, MaxConcurrency 1 : le mois m+1 part du
#                   portefeuille du mois m) ; pour chaque mois, runtime
#                   portfolio (action evolution.tick) -> sonde
#                   staging/<run_id>/evolution/<AAAA-MM>/_done.json
#   -> Synthese -> Termine
#
# Meme modele que la collecte (stepfunctions.tf) : le runtime accepte la tache,
# travaille en arriere-plan puis ecrit son marqueur, que la machine sonde
# (listObjectsV2, puis getObject une fois present). Le moteur calcule ; la
# machine ne fait qu'enchainer les mois et rendre le graphe visible.
#
# Entree : {"client_id": string, "mode": "tick" | "replay",
#           "start"?: "AAAA-MM", "end"?: "AAAA-MM", "months"?: ["AAAA-MM"],
#           "run_id"?: string}. run_id vaut par defaut le nom de l'execution.
#
# L'ARN du runtime vient de var.evolution_portfolio_runtime_arn, sinon du
# runtime portfolio de agentcore.tf (portfolio_enabled). Rien n'est deploye tant
# que evolution_enabled = false ou que l'ARN est vide. Le role de la machine est
# dans local.s3_kms_user_role_arns (s3.tf) : elle lit des marqueurs chiffres.
# =============================================================================

locals {
  # ARN du runtime : variable explicite, sinon le runtime portfolio de agentcore.tf (s'il est deploye)
  evolution_runtime_arn = var.evolution_portfolio_runtime_arn != "" ? var.evolution_portfolio_runtime_arn : try(
  aws_bedrockagentcore_agent_runtime.this["portfolio"].agent_runtime_arn, "")
  # count ne depend que de variables (pas de l'ARN, attribut d'une ressource) : sinon cycle via la cle KMS du bucket
  evolution_count = var.evolution_enabled && (var.evolution_portfolio_runtime_arn != "" || var.portfolio_enabled) ? 1 : 0

  evolution_name         = "${local.prefix}-evolution"
  evolution_poll_seconds = 10
  # Plafond d'une execution : 6 h, soit environ 36 mois au delai maximal de
  # sondage par defaut (60 x 10 s) ; une liste plus longue se decoupe.
  evolution_execution_timeout_seconds = 21600

  evolution_month_regex = "/^[0-9]{4}-[0-9]{2}$/"

  evolution_invoke_retry = [{
    ErrorEquals     = ["BedrockAgentCore.ThrottlingException", "BedrockAgentCore.InternalServerException", "States.Timeout"]
    IntervalSeconds = 10
    MaxAttempts     = 3
    BackoffRate     = 2
  }]

  # Une iteration du Map : un mois simule. Les variables de l'execution
  # entrent par ItemSelector ; une erreur arrete le Map et l'execution (le
  # mois suivant depend du precedent).
  evolution_tick_states = {
    "Mois - lancer" = {
      Type     = "Task"
      Comment  = "Le runtime portfolio accepte le tick du mois et travaille en arriere-plan."
      Resource = "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime"
      Arguments = {
        AgentRuntimeArn  = local.evolution_runtime_arn
        RuntimeSessionId = "{% $pad($states.input.run_id & '-evolution-' & $states.input.month, 48, '0') %}"
        ContentType      = "application/json"
        Accept           = "application/json"
        Payload          = "{% $string({'action': 'evolution.tick', 'client_id': $states.input.client_id, 'month': $states.input.month, 'run_id': $states.input.run_id}) %}"
      }
      TimeoutSeconds = 120
      Retry          = local.evolution_invoke_retry
      Assign = {
        tickRunId    = "{% $states.input.run_id %}"
        month        = "{% $states.input.month %}"
        tickAttempts = 0
      }
      Output = "{% $states.input %}"
      Next   = "Mois - attendre"
    }
    "Mois - attendre" = {
      Type    = "Wait"
      Seconds = local.evolution_poll_seconds
      Next    = "Mois - sonder"
    }
    "Mois - sonder" = {
      Type     = "Task"
      Comment  = "Le marqueur n'existe qu'une fois le mois calcule."
      Resource = "arn:aws:states:::aws-sdk:s3:listObjectsV2"
      Arguments = {
        Bucket  = aws_s3_bucket.this.bucket
        Prefix  = "{% 'staging/' & $tickRunId & '/evolution/' & $month & '/_done.json' %}"
        MaxKeys = 1
      }
      Assign = { tickAttempts = "{% $tickAttempts + 1 %}" }
      Output = "{% {'found': $states.result.KeyCount > 0} %}"
      Next   = "Mois - present"
    }
    "Mois - present" = {
      Type = "Choice"
      Choices = [
        { Condition = "{% $states.input.found %}", Next = "Mois - lire" },
        { Condition = "{% $tickAttempts < ${var.evolution_marker_max_polls} %}", Next = "Mois - attendre" },
      ]
      Default = "Mois - delai depasse"
    }
    "Mois - lire" = {
      Type     = "Task"
      Resource = "arn:aws:states:::aws-sdk:s3:getObject"
      Arguments = {
        Bucket = aws_s3_bucket.this.bucket
        Key    = "{% 'staging/' & $tickRunId & '/evolution/' & $month & '/_done.json' %}"
      }
      Output = "{% $parse($states.result.Body) %}"
      Next   = "Mois - verifier"
    }
    "Mois - verifier" = {
      Type    = "Choice"
      Choices = [{ Condition = "{% $states.input.status = 'ok' %}", Next = "Mois - termine" }]
      Default = "Mois - echec"
    }
    "Mois - termine" = {
      Type   = "Pass"
      Output = "{% {'month': $month, 'status': 'ok', 'marker': $states.input} %}"
      End    = true
    }
    "Mois - delai depasse" = {
      Type  = "Fail"
      Error = "MarkerTimeout"
      Cause = "Le runtime portfolio n'a pas ecrit le marqueur du mois dans le delai."
    }
    "Mois - echec" = {
      Type  = "Fail"
      Error = "AgentError"
      Cause = "{% $string($states.input) %}"
    }
  }

  evolution_definition = {
    Comment        = "Evolution du portefeuille (simulation) : un tick par mois, en sequence, ou un rejeu complet ; le runtime portfolio calcule et ecrit un marqueur par etape."
    QueryLanguage  = "JSONata"
    TimeoutSeconds = local.evolution_execution_timeout_seconds
    StartAt        = "Preparer"
    States = merge(
      {
        "Preparer" = {
          Type = "Pass"
          Assign = {
            runId      = "{% $exists($states.input.run_id) ? $states.input.run_id : $states.context.Execution.Name %}"
            clientId   = "{% $exists($states.input.client_id) ? $states.input.client_id : null %}"
            mode       = "{% $exists($states.input.mode) ? $states.input.mode : null %}"
            startMonth = "{% $exists($states.input.start) ? $states.input.start : null %}"
            endMonth   = "{% $exists($states.input.end) ? $states.input.end : null %}"
            months     = "{% $exists($states.input.months) ? $append([], $states.input.months) : [] %}"
            ticks      = null
            replay     = null
          }
          Next = "Mode"
        }

        "Mode" = {
          Type = "Choice"
          Choices = [
            { Condition = "{% $type($clientId) != 'string' or $clientId = '' %}", Next = "Entree invalide" },
            { Condition = "{% $mode = 'replay' and ($startMonth = null or $contains($startMonth, ${local.evolution_month_regex})) and ($endMonth = null or $contains($endMonth, ${local.evolution_month_regex})) %}", Next = "Rejeu - lancer" },
            { Condition = "{% $mode = 'tick' and $count($months) > 0 and $count($filter($months, function($m) { $type($m) != 'string' or $not($contains($m, ${local.evolution_month_regex})) })) = 0 %}", Next = "Mois" },
          ]
          Default = "Entree invalide"
        }

        "Entree invalide" = {
          Type  = "Fail"
          Error = "InvalidInput"
          Cause = "Attendu : client_id non vide, mode 'tick' avec months [AAAA-MM, ...] non vide, ou mode 'replay' avec start/end AAAA-MM facultatifs."
        }

        # ---------------------------------------------------------------- tick
        "Mois" = {
          Type           = "Map"
          Comment        = "Un mois simule par iteration, en sequence : chaque tick part du portefeuille laisse par le precedent."
          MaxConcurrency = 1
          Items          = "{% $months %}"
          ItemSelector = {
            run_id    = "{% $runId %}"
            client_id = "{% $clientId %}"
            month     = "{% $states.context.Map.Item.Value %}"
          }
          ItemProcessor = {
            ProcessorConfig = { Mode = "INLINE" }
            StartAt         = "Mois - lancer"
            States          = local.evolution_tick_states
          }
          Assign = { ticks = "{% $states.result %}" }
          Next   = "Synthese"
        }

        # -------------------------------------------------------------- replay
        "Rejeu - lancer" = {
          Type     = "Task"
          Comment  = "Le runtime portfolio accepte le rejeu de la periode et travaille en arriere-plan."
          Resource = "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime"
          Arguments = {
            AgentRuntimeArn  = local.evolution_runtime_arn
            RuntimeSessionId = "{% $pad($runId & '-evolution-replay', 48, '0') %}"
            ContentType      = "application/json"
            Accept           = "application/json"
            Payload          = "{% $string($merge([{'action': 'evolution.replay', 'client_id': $clientId, 'run_id': $runId}, $startMonth ? {'start': $startMonth} : {}, $endMonth ? {'end': $endMonth} : {}])) %}"
          }
          TimeoutSeconds = 120
          Retry          = local.evolution_invoke_retry
          Assign         = { attempts = 0 }
          Output         = "{% $states.input %}"
          Next           = "Rejeu - attendre"
        }

        "Rejeu - attendre" = {
          Type    = "Wait"
          Seconds = local.evolution_poll_seconds
          Next    = "Rejeu - sonder"
        }

        "Rejeu - sonder" = {
          Type     = "Task"
          Comment  = "Le marqueur n'existe qu'une fois le rejeu fini."
          Resource = "arn:aws:states:::aws-sdk:s3:listObjectsV2"
          Arguments = {
            Bucket  = aws_s3_bucket.this.bucket
            Prefix  = "{% 'staging/' & $runId & '/evolution/replay/_done.json' %}"
            MaxKeys = 1
          }
          Assign = { attempts = "{% $attempts + 1 %}" }
          Output = "{% {'found': $states.result.KeyCount > 0} %}"
          Next   = "Rejeu - present"
        }

        "Rejeu - present" = {
          Type = "Choice"
          Choices = [
            { Condition = "{% $states.input.found %}", Next = "Rejeu - lire" },
            { Condition = "{% $attempts < ${var.evolution_marker_max_polls} %}", Next = "Rejeu - attendre" },
          ]
          Default = "Rejeu - delai depasse"
        }

        "Rejeu - lire" = {
          Type     = "Task"
          Resource = "arn:aws:states:::aws-sdk:s3:getObject"
          Arguments = {
            Bucket = aws_s3_bucket.this.bucket
            Key    = "{% 'staging/' & $runId & '/evolution/replay/_done.json' %}"
          }
          Output = "{% $parse($states.result.Body) %}"
          Next   = "Rejeu - verifier"
        }

        "Rejeu - verifier" = {
          Type    = "Choice"
          Choices = [{ Condition = "{% $states.input.status = 'ok' %}", Next = "Rejeu - termine" }]
          Default = "Rejeu - echec"
        }

        "Rejeu - termine" = {
          Type   = "Pass"
          Assign = { replay = "{% $states.input %}" }
          Next   = "Synthese"
        }

        "Rejeu - delai depasse" = {
          Type  = "Fail"
          Error = "MarkerTimeout"
          Cause = "Le runtime portfolio n'a pas ecrit le marqueur du rejeu dans le delai."
        }

        "Rejeu - echec" = {
          Type  = "Fail"
          Error = "AgentError"
          Cause = "{% $string($states.input) %}"
        }

        # ------------------------------------------------------------- commun
        "Synthese" = {
          Type   = "Pass"
          Output = "{% {'run_id': $runId, 'client_id': $clientId, 'mode': $mode, 'months': $ticks, 'replay': $replay} %}"
          Next   = "Termine"
        }

        "Termine" = {
          Type   = "Succeed"
          Output = "{% $states.input %}"
        }
      },
    )
  }
}

# -----------------------------------------------------------------------------
# Journaux d'execution (cle aws_kms_key.logs : sa politique n'admet que
# /aws/vendedlogs/states/${local.prefix}-*).
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "evolution" {
  count = local.evolution_count

  name              = "/aws/vendedlogs/states/${local.evolution_name}"
  retention_in_days = 14
  kms_key_id        = aws_kms_key.logs.arn
  tags              = local.common_tags
}

# -----------------------------------------------------------------------------
# Role de la machine : appeler le runtime portfolio, lire ses marqueurs,
# journaliser. Meme confiance que la collecte (machines ${local.prefix}-*).
# Le dechiffrement KMS des marqueurs passe par la politique de cle du bucket
# (s3.tf, s3_kms_user_role_arns : coordination).
# -----------------------------------------------------------------------------
resource "aws_iam_role" "evolution" {
  count = local.evolution_count

  name               = local.evolution_name
  description        = "Role de la machine Step Functions d'evolution du portefeuille."
  assume_role_policy = data.aws_iam_policy_document.collecte_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "evolution" {
  count = local.evolution_count

  statement {
    sid     = "InvokePortfolio"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = [
      local.evolution_runtime_arn,
      "${local.evolution_runtime_arn}/*",
    ]
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

resource "aws_iam_role_policy" "evolution" {
  count = local.evolution_count

  name   = "evolution"
  role   = aws_iam_role.evolution[0].id
  policy = data.aws_iam_policy_document.evolution[0].json
}

resource "aws_sfn_state_machine" "evolution" {
  count = local.evolution_count

  name       = local.evolution_name
  role_arn   = aws_iam_role.evolution[0].arn
  definition = jsonencode(local.evolution_definition)

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.evolution[0].arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = local.common_tags

  depends_on = [aws_iam_role_policy.evolution]
}

# -----------------------------------------------------------------------------
# Schedule de demonstration : toutes les 5 minutes, une execution en mode tick
# sur un seul mois (var.evolution_demo_month) pour un client fictif. Une
# execution = un mois simule ; le temps simule n'avance pas tout seul : pour
# enchainer plusieurs mois, lancer la machine avec months = [...]. Cree
# seulement si evolution_demo_schedule = true, et DISABLED tant que
# evolution_demo_schedule_state != "ENABLED".
# -----------------------------------------------------------------------------
locals {
  evolution_demo_count = local.evolution_count == 1 && var.evolution_demo_schedule ? 1 : 0
}

data "aws_iam_policy_document" "scheduler_evolution" {
  count = local.evolution_demo_count

  statement {
    sid       = "StartEvolution"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.evolution[0].arn]
  }
}

resource "aws_iam_role_policy" "scheduler_evolution" {
  count = local.evolution_demo_count

  name   = "start-evolution"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_evolution[0].json
}

resource "aws_scheduler_schedule" "evolution_demo" {
  count = local.evolution_demo_count

  name        = "${local.prefix}-evolution-demo"
  description = "Demo : un tick d'evolution du portefeuille (un mois simule) par declenchement. Simulation seulement."

  schedule_expression          = "rate(5 minutes)"
  schedule_expression_timezone = "America/Toronto"
  state                        = var.evolution_demo_schedule_state == "ENABLED" ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.evolution[0].arn
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      client_id = var.evolution_demo_client_id
      mode      = "tick"
      months    = [var.evolution_demo_month]
      source    = "scheduler"
    })

    retry_policy {
      maximum_retry_attempts = 0
    }
  }

  lifecycle {
    precondition {
      condition     = var.evolution_demo_client_id != ""
      error_message = "evolution_demo_client_id doit etre renseigne quand evolution_demo_schedule = true."
    }
  }

  depends_on = [aws_iam_role_policy.scheduler_evolution]
}
