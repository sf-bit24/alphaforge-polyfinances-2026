# =============================================================================
# Service : recherche par experts de sujet (app/CONTRACTS.md, section 11).
#
#   mode question : A0 route -> Map [expert E1..E7 choisis par A0]
#                   -> A0 compose -> A6 curate -> ingestion
#   mode sweep    : Map [experts demandes, tous par defaut] -> A6 curate
#                   -> ingestion
#
# Chaque expert lance lui-meme n chercheurs (InvokeAgentRuntime sur le runtime
# researcher, une session par chercheur, donc une microVM chacun), sonde leurs
# marqueurs, puis ecrit staging/<run_id>/experts/<sujet>/_done.json que la
# machine sonde. Le modele de l'expert choisit n et les missions ; le code
# applique les plafonds (n selon la profondeur, deux tours, 24 chercheurs par
# execution).
#
# Les runtimes router, expert et researcher sont des entrees de
# local.agentcore_runtimes (agentcore.tf) : meme zip, AGENT_ROLE propre, motifs
# de cles exacts. L'expert recoit le nom du runtime researcher et trouve son
# ARN par ListAgentRuntimes : l'ARN d'un runtime porte un suffixe aleatoire,
# et le referencer dans le meme for_each serait circulaire.
#
# Entree : {"mode"?: "sweep" | "question", "run_id"?, "question"?, "subjects"?,
#           "issuers"?, "themes"?, "as_of"?, "depth"?, "since"?}
# =============================================================================

locals {
  recherche_name            = "${local.prefix}-recherche"
  recherche_researcher_name = "${local.name_snake}_researcher"
  recherche_subjects        = ["E1", "E2", "E3", "E4", "E5", "E6", "E7"]
  recherche_max_polls       = ceil(var.recherche_agent_timeout_seconds / var.collecte_poll_seconds)

  # Variables propres au runtime expert (fusionnees dans agentcore.tf).
  recherche_expert_env = {
    ALPHAFORGE_RESEARCHER_NAME = local.recherche_researcher_name
  }

  # Etapes « lancer, attendre, sonder le marqueur, le lire » des runtimes
  # appeles une fois par execution. Toute erreur arrete l'execution.
  recherche_stages = {
    route = {
      label   = "A0 routage"
      runtime = "router"
      session = "{% $pad($runId & '-router-route', 48, '0') %}"
      payload = "{% $string($merge([{'action': 'route', 'run_id': $runId, 'question': $question, 'depth': $depth}, $issuers ? {'issuers': $issuers} : {}, $themes ? {'themes': $themes} : {}, $asOf ? {'as_of': $asOf} : {}, $since ? {'since': $since} : {}])) %}"
      marker  = "/router/_routed.json"
      assign  = { plan = "{% $states.input.plan %}" }
      next    = "Experts"
    }
    compose = {
      label   = "A0 synthese"
      runtime = "router"
      session = "{% $pad($runId & '-router-compose', 48, '0') %}"
      payload = "{% $string({'action': 'compose', 'run_id': $runId}) %}"
      marker  = "/router/_composed.json"
      assign  = { composed = "{% $states.input %}" }
      next    = "A6 superviseur - lancer"
    }
    curate = {
      label   = "A6 superviseur"
      runtime = "supervisor"
      session = "{% $pad($runId & '-supervisor', 48, '0') %}"
      payload = "{% $string({'action': 'curate', 'run_id': $runId}) %}"
      marker  = "/supervisor/_done.json"
      assign  = { curated = "{% $states.input %}" }
      next    = "Ingestion - lancer"
    }
  }

  recherche_stage_states = merge([
    for key, stage in local.recherche_stages : {
      "${stage.label} - lancer" = {
        Type     = "Task"
        Comment  = "Le runtime accepte la tache et travaille en arriere-plan."
        Resource = "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime"
        Arguments = {
          AgentRuntimeArn  = aws_bedrockagentcore_agent_runtime.this[stage.runtime].agent_runtime_arn
          RuntimeSessionId = stage.session
          ContentType      = "application/json"
          Accept           = "application/json"
          Payload          = stage.payload
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
        Next   = "${stage.label} - attendre"
      }
      "${stage.label} - attendre" = {
        Type    = "Wait"
        Seconds = var.collecte_poll_seconds
        Next    = "${stage.label} - sonder"
      }
      "${stage.label} - sonder" = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:s3:listObjectsV2"
        Arguments = {
          Bucket  = aws_s3_bucket.this.bucket
          Prefix  = "{% 'staging/' & $runId & '${stage.marker}' %}"
          MaxKeys = 1
        }
        Assign = { attempts = "{% $attempts + 1 %}" }
        Output = "{% {'found': $states.result.KeyCount > 0} %}"
        Next   = "${stage.label} - present"
      }
      "${stage.label} - present" = {
        Type = "Choice"
        Choices = [
          { Condition = "{% $states.input.found %}", Next = "${stage.label} - lire" },
          { Condition = "{% $attempts < ${local.recherche_max_polls} %}", Next = "${stage.label} - attendre" },
        ]
        Default = "${stage.label} - delai depasse"
      }
      "${stage.label} - lire" = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:s3:getObject"
        Arguments = {
          Bucket = aws_s3_bucket.this.bucket
          Key    = "{% 'staging/' & $runId & '${stage.marker}' %}"
        }
        Output = "{% $parse($states.result.Body) %}"
        Next   = "${stage.label} - verifier"
      }
      "${stage.label} - verifier" = {
        Type    = "Choice"
        Choices = [{ Condition = "{% $states.input.status = 'ok' %}", Next = "${stage.label} - termine" }]
        Default = "${stage.label} - echec"
      }
      "${stage.label} - termine" = {
        Type   = "Pass"
        Assign = stage.assign
        Next   = stage.next
      }
      "${stage.label} - delai depasse" = {
        Type  = "Fail"
        Error = "MarkerTimeout"
        Cause = "${stage.label} n'a pas ecrit son marqueur dans le delai."
      }
      "${stage.label} - echec" = {
        Type  = "Fail"
        Error = "AgentError"
        Cause = "{% $string($states.input) %}"
      }
    }
  ]...)

  # Une iteration du Map : un expert. Un expert en echec n'arrete pas les
  # autres ; A6 traite ce qui est arrive, comme pour A4 et A5.
  recherche_expert_states = {
    "Expert - lancer" = {
      Type     = "Task"
      Comment  = "L'expert accepte sa tache, lance ses chercheurs et travaille en arriere-plan."
      Resource = "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime"
      Arguments = {
        AgentRuntimeArn  = aws_bedrockagentcore_agent_runtime.this["expert"].agent_runtime_arn
        RuntimeSessionId = "{% $pad($states.input.run_id & '-' & $states.input.payload.subject, 48, '0') %}"
        ContentType      = "application/json"
        Accept           = "application/json"
        Payload          = "{% $string($states.input.payload) %}"
      }
      TimeoutSeconds = 120
      Retry = [{
        ErrorEquals     = ["BedrockAgentCore.ThrottlingException", "BedrockAgentCore.InternalServerException", "States.Timeout"]
        IntervalSeconds = 10
        MaxAttempts     = 3
        BackoffRate     = 2
      }]
      Assign = {
        expertRunId    = "{% $states.input.run_id %}"
        subject        = "{% $states.input.payload.subject %}"
        expertAttempts = 0
      }
      Output = "{% $states.input %}"
      Catch = [{
        ErrorEquals = ["States.ALL"]
        Output      = "{% {'status': 'error', 'subject': $states.input.payload.subject, 'error': $states.errorOutput} %}"
        Next        = "Expert - echec"
      }]
      Next = "Expert - attendre"
    }
    "Expert - attendre" = {
      Type    = "Wait"
      Seconds = var.collecte_poll_seconds
      Next    = "Expert - sonder"
    }
    "Expert - sonder" = {
      Type     = "Task"
      Resource = "arn:aws:states:::aws-sdk:s3:listObjectsV2"
      Arguments = {
        Bucket  = aws_s3_bucket.this.bucket
        Prefix  = "{% 'staging/' & $expertRunId & '/experts/' & $subject & '/_done.json' %}"
        MaxKeys = 1
      }
      Assign = { expertAttempts = "{% $expertAttempts + 1 %}" }
      Output = "{% {'found': $states.result.KeyCount > 0} %}"
      Catch = [{
        ErrorEquals = ["States.ALL"]
        Output      = "{% {'status': 'error', 'subject': $subject, 'error': $states.errorOutput} %}"
        Next        = "Expert - echec"
      }]
      Next = "Expert - present"
    }
    "Expert - present" = {
      Type = "Choice"
      Choices = [
        { Condition = "{% $states.input.found %}", Next = "Expert - lire" },
        { Condition = "{% $expertAttempts < ${local.recherche_max_polls} %}", Next = "Expert - attendre" },
      ]
      Default = "Expert - delai depasse"
    }
    "Expert - lire" = {
      Type     = "Task"
      Resource = "arn:aws:states:::aws-sdk:s3:getObject"
      Arguments = {
        Bucket = aws_s3_bucket.this.bucket
        Key    = "{% 'staging/' & $expertRunId & '/experts/' & $subject & '/_done.json' %}"
      }
      Output = "{% $parse($states.result.Body) %}"
      Catch = [{
        ErrorEquals = ["States.ALL"]
        Output      = "{% {'status': 'error', 'subject': $subject, 'error': $states.errorOutput} %}"
        Next        = "Expert - echec"
      }]
      Next = "Expert - verifier"
    }
    "Expert - verifier" = {
      Type    = "Choice"
      Choices = [{ Condition = "{% $states.input.status = 'ok' %}", Next = "Expert - termine" }]
      Default = "Expert - marqueur en erreur"
    }
    "Expert - marqueur en erreur" = {
      Type   = "Pass"
      Output = "{% {'status': 'error', 'subject': $subject, 'error': $states.input.error} %}"
      End    = true
    }
    "Expert - termine" = {
      Type   = "Pass"
      Output = "{% {'status': 'ok', 'subject': $subject, 'spawned': $states.input.spawned, 'rounds': $states.input.rounds, 'items': $states.input.items, 'gaps': $states.input.gaps} %}"
      End    = true
    }
    "Expert - delai depasse" = {
      Type   = "Pass"
      Output = "{% {'status': 'error', 'subject': $subject, 'error': 'marqueur absent dans le delai'} %}"
      End    = true
    }
    "Expert - echec" = {
      Type   = "Pass"
      Output = "{% {'status': 'error', 'subject': $states.input.subject, 'error': $states.input.error} %}"
      End    = true
    }
  }

  recherche_definition = {
    Comment        = "Recherche par experts de sujet : chaque expert lance n chercheurs (une session AgentCore chacun), A6 relit et ecrit, puis ingestion."
    QueryLanguage  = "JSONata"
    TimeoutSeconds = var.recherche_execution_timeout_seconds
    StartAt        = "Preparer"
    States = merge(
      {
        "Preparer" = {
          Type = "Pass"
          Assign = {
            runId    = "{% $exists($states.input.run_id) ? $states.input.run_id : $states.context.Execution.Name %}"
            mode     = "{% $exists($states.input.mode) ? $states.input.mode : 'sweep' %}"
            question = "{% $exists($states.input.question) ? $states.input.question : null %}"
            subjects = "{% $exists($states.input.subjects) ? $states.input.subjects : ${jsonencode(local.recherche_subjects)} %}"
            issuers  = "{% $exists($states.input.issuers) ? $states.input.issuers : null %}"
            themes   = "{% $exists($states.input.themes) ? $states.input.themes : null %}"
            asOf     = "{% $exists($states.input.as_of) ? $states.input.as_of : null %}"
            since    = "{% $exists($states.input.since) ? $states.input.since : null %}"
            depth    = "{% $exists($states.input.depth) ? $states.input.depth : ($exists($states.input.question) ? 'standard' : 'quick') %}"
            plan     = null
            composed = null
          }
          Next = "Mode"
        }

        "Mode" = {
          Type    = "Choice"
          Choices = [{ Condition = "{% $mode = 'question' %}", Next = "A0 routage - lancer" }]
          Default = "Experts"
        }

        # Une iteration par sujet : les variables de l'execution entrent dans
        # chaque element par ItemSelector, evalue dans la portee exterieure.
        "Experts" = {
          Type           = "Map"
          Comment        = "Un expert par sujet, en parallele ; chaque expert lance lui-meme ses chercheurs."
          MaxConcurrency = 7
          Items          = "{% $mode = 'question' ? $plan.subjects : $append([], $map($subjects, function($s) { {'subject': $s} })) %}"
          ItemSelector = {
            run_id  = "{% $runId %}"
            payload = "{% $merge([{'action': 'research', 'run_id': $runId, 'subject': $states.context.Map.Item.Value.subject, 'mode': $mode, 'depth': $depth}, $mode = 'question' ? {'question': $question, 'sub_question': $states.context.Map.Item.Value.sub_question, 'max_researchers': $states.context.Map.Item.Value.max_researchers} : {}, $issuers ? {'issuers': $issuers} : {}, $themes ? {'themes': $themes} : {}, $asOf ? {'as_of': $asOf} : {}, $since ? {'since': $since} : {}]) %}"
          }
          ItemProcessor = {
            ProcessorConfig = { Mode = "INLINE" }
            StartAt         = "Expert - lancer"
            States          = local.recherche_expert_states
          }
          Assign = { experts = "{% $states.result %}" }
          Next   = "Apres les experts"
        }

        "Apres les experts" = {
          Type    = "Choice"
          Choices = [{ Condition = "{% $mode = 'question' %}", Next = "A0 synthese - lancer" }]
          Default = "A6 superviseur - lancer"
        }

        "Ingestion - lancer" = {
          Type     = "Task"
          Comment  = "Resynchronise general/ : documents ecrits par A6."
          Resource = "arn:aws:states:::aws-sdk:bedrockagent:startIngestionJob"
          Arguments = {
            KnowledgeBaseId = aws_bedrockagent_knowledge_base.general.id
            DataSourceId    = aws_bedrockagent_data_source.general.data_source_id
            Description     = "{% 'Recherche ' & $runId %}"
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
          Output = "{% {'run_id': $runId, 'mode': $mode, 'plan': $plan, 'experts': $experts, 'composed': $composed, 'curated': {'written': $curated.written, 'rejected': $count($curated.rejected), 'quarantined': $curated.quarantined}, 'ingestion': {'job_id': $ingestionJobId, 'status': $states.input.Status}} %}"
        }
      },
      local.recherche_stage_states,
    )
  }
}

# -----------------------------------------------------------------------------
# L'expert lance ses chercheurs : InvokeAgentRuntime sur le runtime researcher
# seulement, et ListAgentRuntimes pour trouver son ARN par son nom.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "expert_researchers" {
  statement {
    sid     = "InvokeResearchers"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = [
      aws_bedrockagentcore_agent_runtime.this["researcher"].agent_runtime_arn,
      "${aws_bedrockagentcore_agent_runtime.this["researcher"].agent_runtime_arn}/*",
    ]
  }

  statement {
    sid       = "FindResearcherRuntime"
    actions   = ["bedrock-agentcore:ListAgentRuntimes"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "expert_researchers" {
  name   = "researchers"
  role   = aws_iam_role.agentcore["expert"].id
  policy = data.aws_iam_policy_document.expert_researchers.json
}

# -----------------------------------------------------------------------------
# Machine de recherche, son role et ses journaux.
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "recherche" {
  name              = "/aws/vendedlogs/states/${local.recherche_name}"
  retention_in_days = 14
  kms_key_id        = aws_kms_key.logs.arn
  tags              = local.common_tags
}

resource "aws_iam_role" "recherche" {
  name               = "${local.prefix}-recherche"
  description        = "Role de la machine Step Functions de recherche par experts."
  assume_role_policy = data.aws_iam_policy_document.collecte_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "recherche" {
  statement {
    sid     = "InvokeResearchRuntimes"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = flatten([
      for role in ["router", "expert", "supervisor"] : [
        aws_bedrockagentcore_agent_runtime.this[role].agent_runtime_arn,
        "${aws_bedrockagentcore_agent_runtime.this[role].agent_runtime_arn}/*",
      ]
    ])
  }

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

resource "aws_iam_role_policy" "recherche" {
  name   = "recherche"
  role   = aws_iam_role.recherche.id
  policy = data.aws_iam_policy_document.recherche.json
}

resource "aws_sfn_state_machine" "recherche" {
  name       = local.recherche_name
  role_arn   = aws_iam_role.recherche.arn
  definition = jsonencode(local.recherche_definition)

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.recherche.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = local.common_tags

  depends_on = [aws_iam_role_policy.recherche]
}

# -----------------------------------------------------------------------------
# Veille des experts : un passage quotidien en mode sweep, desactive par defaut
# (var.recherche_schedule_enabled) tant que l'equipe ne l'a pas valide.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "scheduler_recherche" {
  statement {
    sid       = "StartRecherche"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.recherche.arn]
  }
}

resource "aws_iam_role_policy" "scheduler_recherche" {
  name   = "start-recherche"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_recherche.json
}

resource "aws_scheduler_schedule" "recherche" {
  name        = "${local.prefix}-recherche"
  description = "Veille des experts de sujet : chaque expert lance ses chercheurs, A6 ecrit, ingestion."

  schedule_expression          = var.recherche_schedule_expression
  schedule_expression_timezone = "America/Toronto"
  state                        = var.recherche_schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.recherche.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ mode = "sweep", source = "scheduler" })

    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}
