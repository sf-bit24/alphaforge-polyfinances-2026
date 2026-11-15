# =============================================================================
# Service : tldoole, des videos courtes sur les concepts que l'investisseur
# ne comprend pas encore (app/CONTRACTS.md, section 8).
#
#   S3 (clients/*/journal.md ecrit) -> EventBridge -> Step Functions :
#     anti-rebond (le journal n'a plus bouge) -> A7 detect (runtime tldoole)
#     -> pour chaque video : A8 produce (scenario, ecrans, narration Polly)
#        -> MediaConvert (createJob.sync : MP4 1080x1920, sous-titres incrustes)
#        -> finalize (statut de la video dans la base du client)
#
# Le runtime AgentCore tldoole est la cinquieme entree de
# local.agentcore_runtimes (agentcore.tf) : meme zip, AGENT_ROLE=tldoole, et
# des motifs de cles exacts :
#   s3_read  = s3_list = clients/*/profil.md, clients/*/journal.md,
#              clients/*/portefeuille-existant.md, clients/*/tldoole/*
#   s3_write = clients/*/tldoole/*
#   knowledge_base = guardrail = true ; environnement : agentcore_profile_env
#   et local.tldoole_runtime_env.
# Ce fichier lui ajoute Polly et le lancement de la machine (request,
# feedback), et cree la machine, le role MediaConvert, le declencheur
# EventBridge et leurs journaux. Le declencheur reste DISABLED tant que
# var.tldoole_trigger_enabled vaut false (valeur par defaut) : seules les
# actions request et feedback lancent alors la machine.
#
# Comme les collecteurs, detect et produce acceptent leur tache aussitot et
# ecrivent un marqueur que la machine sonde par listObjectsV2 :
#   clients/<id>/tldoole/runs/<run_id>/detect.json
#   clients/<id>/tldoole/videos/<video_id>/_produced.json
# =============================================================================

locals {
  tldoole_name              = "${local.prefix}-tldoole"
  tldoole_state_machine_arn = "arn:${local.partition}:states:${var.aws_region}:${local.account_id}:stateMachine:${local.tldoole_name}"
  tldoole_runtime_arn       = aws_bedrockagentcore_agent_runtime.this["tldoole"].agent_runtime_arn

  # Variables d'environnement propres au runtime tldoole (fusionnees dans
  # agentcore.tf). L'ARN de la machine est construit a partir de son nom :
  # aucune reference circulaire entre le runtime et la machine qui l'appelle.
  tldoole_runtime_env = {
    ALPHAFORGE_TLDOOLE_STATE_MACHINE_ARN = local.tldoole_state_machine_arn
    ALPHAFORGE_TLDOOLE_MAX_PER_RUN       = tostring(var.tldoole_max_videos_per_run)
    ALPHAFORGE_TLDOOLE_MAX_PER_DAY       = tostring(var.tldoole_max_videos_per_day)
  }

  # Roles qui lisent ou ecrivent le bucket, a ajouter a la key policy KMS
  # (s3.tf, local.s3_kms_user_role_arns) : la cle ne delegue pas a IAM.
  tldoole_kms_user_role_arns = [aws_iam_role.tldoole_sfn.arn, aws_iam_role.tldoole_mediaconvert.arn]

  # Fichiers de montage (ecrans, police, narration, sous-titres, MP4). Les
  # telechargeurs d'incrustations et de polices de MediaConvert les lisent sans
  # TLS : la bucket policy (s3.tf) exempte ce seul role de DenyInsecureTransport,
  # et seulement sur ces objets.
  tldoole_media_objects_arn            = "${aws_s3_bucket.this.arn}/clients/*/tldoole/*"
  tldoole_insecure_transport_role_arns = [aws_iam_role.tldoole_mediaconvert.arn]

  tldoole_detect_max_polls  = ceil(var.tldoole_detect_timeout_seconds / var.tldoole_poll_seconds)
  tldoole_produce_max_polls = ceil(var.tldoole_produce_timeout_seconds / var.tldoole_poll_seconds)

  tldoole_invoke_retry = [{
    ErrorEquals     = ["BedrockAgentCore.ThrottlingException", "BedrockAgentCore.InternalServerException", "States.Timeout"]
    IntervalSeconds = 5
    MaxAttempts     = 3
    BackoffRate     = 2
  }]

  # Etats d'une video, executes par le Map (au plus var.tldoole_max_concurrency
  # en parallele). Toute erreur finit par "Finaliser - echec" : la video passe
  # a failed dans la base du client au lieu de rester en cours.
  tldoole_video_states = {
    "Video - preparer" = {
      Type   = "Pass"
      Assign = { cid = "{% $states.input.client_id %}", vid = "{% $states.input.video_id %}", videoPolls = 0, error = null }
      Next   = "A8 produire - lancer"
    }

    "A8 produire - lancer" = {
      Type     = "Task"
      Comment  = "A8 ecrit le scenario, le code dessine les ecrans, Polly dit la narration."
      Resource = "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime"
      Arguments = {
        AgentRuntimeArn  = local.tldoole_runtime_arn
        RuntimeSessionId = "{% $cid & '-' & $vid %}"
        ContentType      = "application/json"
        Accept           = "application/json"
        Payload          = "{% $string({'action': 'produce', 'client_id': $cid, 'video_id': $vid}) %}"
      }
      TimeoutSeconds = 120
      Retry          = local.tldoole_invoke_retry
      Catch = [{
        ErrorEquals = ["States.ALL"]
        Assign      = { error = "{% $string($states.errorOutput) %}" }
        Next        = "Finaliser - echec"
      }]
      Output = "{% $states.input %}"
      Next   = "A8 - attendre"
    }

    "A8 - attendre" = {
      Type    = "Wait"
      Seconds = var.tldoole_poll_seconds
      Next    = "A8 - sonder"
    }

    "A8 - sonder" = {
      Type     = "Task"
      Comment  = "Le marqueur n'existe qu'une fois les elements de la video ecrits."
      Resource = "arn:aws:states:::aws-sdk:s3:listObjectsV2"
      Arguments = {
        Bucket  = aws_s3_bucket.this.bucket
        Prefix  = "{% 'clients/' & $cid & '/tldoole/videos/' & $vid & '/_produced.json' %}"
        MaxKeys = 1
      }
      Assign = { videoPolls = "{% $videoPolls + 1 %}" }
      Output = "{% {'found': $states.result.KeyCount > 0} %}"
      Catch = [{
        ErrorEquals = ["States.ALL"]
        Assign      = { error = "{% $string($states.errorOutput) %}" }
        Next        = "Finaliser - echec"
      }]
      Next = "A8 - present"
    }

    "A8 - present" = {
      Type = "Choice"
      Choices = [
        { Condition = "{% $states.input.found %}", Next = "A8 - lire" },
        { Condition = "{% $videoPolls < ${local.tldoole_produce_max_polls} %}", Next = "A8 - attendre" },
      ]
      Default = "A8 - delai depasse"
    }

    "A8 - delai depasse" = {
      Type   = "Pass"
      Assign = { error = "marqueur _produced.json absent dans le delai" }
      Next   = "Finaliser - echec"
    }

    "A8 - lire" = {
      Type     = "Task"
      Resource = "arn:aws:states:::aws-sdk:s3:getObject"
      Arguments = {
        Bucket = aws_s3_bucket.this.bucket
        Key    = "{% 'clients/' & $cid & '/tldoole/videos/' & $vid & '/_produced.json' %}"
      }
      Output = "{% $parse($states.result.Body) %}"
      Catch = [{
        ErrorEquals = ["States.ALL"]
        Assign      = { error = "{% $string($states.errorOutput) %}" }
        Next        = "Finaliser - echec"
      }]
      Next = "A8 - verifier"
    }

    "A8 - verifier" = {
      Type    = "Choice"
      Choices = [{ Condition = "{% $states.input.status = 'ok' and $exists($states.input.settings) %}", Next = "Montage - MediaConvert" }]
      Default = "A8 - echec"
    }

    "A8 - echec" = {
      Type   = "Pass"
      Assign = { error = "{% $string($states.input.error) %}" }
      Next   = "Finaliser - echec"
    }

    # Integration optimisee .sync : la machine attend la fin du job
    # (evenements MediaConvert par la regle geree
    # StepFunctionsGetEventsForMediaConvertJobRule).
    "Montage - MediaConvert" = {
      Type     = "Task"
      Comment  = "MP4 1080x1920 : ecrans de la scene a l'instant ou Polly la dit, narration, sous-titres incrustes."
      Resource = "arn:aws:states:::mediaconvert:createJob.sync"
      Arguments = {
        Role                 = aws_iam_role.tldoole_mediaconvert.arn
        Settings             = "{% $states.input.settings %}"
        StatusUpdateInterval = "SECONDS_10"
        UserMetadata = {
          client_id = "{% $cid %}"
          video_id  = "{% $vid %}"
        }
      }
      TimeoutSeconds = var.tldoole_montage_timeout_seconds
      Retry = [{
        ErrorEquals     = ["MediaConvert.TooManyRequestsException", "MediaConvert.InternalServerErrorException"]
        IntervalSeconds = 10
        MaxAttempts     = 3
        BackoffRate     = 2
      }]
      Catch = [{
        ErrorEquals = ["States.ALL"]
        Assign      = { error = "{% $string($states.errorOutput) %}" }
        Next        = "Finaliser - echec"
      }]
      Output = "{% ($job := $exists($states.result.Job) ? $states.result.Job : $states.result; {'status': 'COMPLETE', 'id': $job.Id, 'duration_ms': $job.OutputGroupDetails[0].OutputDetails[0].DurationInMs}) %}"
      Next   = "Finaliser"
    }

    "Finaliser" = {
      Type     = "Task"
      Resource = "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime"
      Arguments = {
        AgentRuntimeArn  = local.tldoole_runtime_arn
        RuntimeSessionId = "{% $cid & '-' & $vid %}"
        ContentType      = "application/json"
        Accept           = "application/json"
        Payload          = "{% $string({'action': 'finalize', 'client_id': $cid, 'video_id': $vid, 'job': $states.input}) %}"
      }
      TimeoutSeconds = 60
      Retry          = local.tldoole_invoke_retry
      Output         = "{% {'video_id': $vid, 'status': 'ready', 'job': $states.input} %}"
      End            = true
    }

    "Finaliser - echec" = {
      Type     = "Task"
      Comment  = "La video passe a failed dans la base du client, avec la cause."
      Resource = "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime"
      Arguments = {
        AgentRuntimeArn  = local.tldoole_runtime_arn
        RuntimeSessionId = "{% $cid & '-' & $vid %}"
        ContentType      = "application/json"
        Accept           = "application/json"
        Payload          = "{% $string({'action': 'finalize', 'client_id': $cid, 'video_id': $vid, 'job': {'status': 'ERROR', 'error': $error}}) %}"
      }
      TimeoutSeconds = 60
      Retry          = local.tldoole_invoke_retry
      Catch = [{
        ErrorEquals = ["States.ALL"]
        Output      = "{% {'video_id': $vid, 'status': 'failed', 'error': $error, 'finalize_error': $states.errorOutput} %}"
        Next        = "Video - echec"
      }]
      Output = "{% {'video_id': $vid, 'status': 'failed', 'error': $error} %}"
      End    = true
    }

    "Video - echec" = {
      Type = "Pass"
      End  = true
    }
  }

  tldoole_definition = {
    Comment        = "tldoole : A7 detecte les lacunes dans le journal du profil, A8 et MediaConvert produisent une video par lacune."
    QueryLanguage  = "JSONata"
    TimeoutSeconds = var.tldoole_execution_timeout_seconds
    StartAt        = "Preparer"
    States = merge(
      {
        # Deux entrees : un evenement S3 "Object Created" sur
        # clients/<id>/journal.md (EventBridge), ou
        # {"source": "request"|"feedback", "client_id", "video_ids"} (runtime).
        "Preparer" = {
          Type = "Pass"
          Assign = {
            fromJournal = "{% $exists($states.input.detail.object.key) %}"
            clientId    = "{% $exists($states.input.detail.object.key) ? $split($states.input.detail.object.key, '/')[1] : $states.input.client_id %}"
            etag        = "{% $exists($states.input.detail.object.etag) ? $states.input.detail.object.etag : null %}"
            videoIds    = "{% $exists($states.input.video_ids) ? $states.input.video_ids : [] %}"
            runId       = "{% $states.context.Execution.Name %}"
            polls       = 0
          }
          Next = "Source"
        }

        "Source" = {
          Type = "Choice"
          Choices = [
            { Condition = "{% $fromJournal %}", Next = "Anti-rebond - attendre" },
            { Condition = "{% $count($videoIds) > 0 %}", Next = "Videos" },
          ]
          Default = "Rien a produire"
        }

        # Le journal est reecrit a chaque reponse : on attend qu'il se stabilise,
        # et seule l'execution de la derniere version continue.
        "Anti-rebond - attendre" = {
          Type    = "Wait"
          Seconds = var.tldoole_debounce_seconds
          Next    = "Anti-rebond - sonder"
        }

        "Anti-rebond - sonder" = {
          Type     = "Task"
          Resource = "arn:aws:states:::aws-sdk:s3:listObjectsV2"
          Arguments = {
            Bucket  = aws_s3_bucket.this.bucket
            Prefix  = "{% 'clients/' & $clientId & '/journal.md' %}"
            MaxKeys = 1
          }
          Output = "{% {'current': $replace($states.result.Contents[0].ETag, '\"', '')} %}"
          Next   = "Anti-rebond - derniere version"
        }

        "Anti-rebond - derniere version" = {
          Type    = "Choice"
          Choices = [{ Condition = "{% $states.input.current = $etag %}", Next = "A7 detecter - lancer" }]
          Default = "Remplacee"
        }

        "Remplacee" = {
          Type   = "Succeed"
          Output = "{% {'client_id': $clientId, 'superseded': true} %}"
        }

        "A7 detecter - lancer" = {
          Type     = "Task"
          Comment  = "A7 juge les signaux du journal et cree les videos a produire."
          Resource = "arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime"
          Arguments = {
            AgentRuntimeArn  = local.tldoole_runtime_arn
            RuntimeSessionId = "{% $clientId & '-detect' %}"
            ContentType      = "application/json"
            Accept           = "application/json"
            Payload          = "{% $string({'action': 'detect', 'client_id': $clientId, 'run_id': $runId}) %}"
          }
          TimeoutSeconds = 120
          Retry          = local.tldoole_invoke_retry
          Output         = "{% $states.input %}"
          Next           = "A7 - attendre"
        }

        "A7 - attendre" = {
          Type    = "Wait"
          Seconds = var.tldoole_poll_seconds
          Next    = "A7 - sonder"
        }

        "A7 - sonder" = {
          Type     = "Task"
          Resource = "arn:aws:states:::aws-sdk:s3:listObjectsV2"
          Arguments = {
            Bucket  = aws_s3_bucket.this.bucket
            Prefix  = "{% 'clients/' & $clientId & '/tldoole/runs/' & $runId & '/detect.json' %}"
            MaxKeys = 1
          }
          Assign = { polls = "{% $polls + 1 %}" }
          Output = "{% {'found': $states.result.KeyCount > 0} %}"
          Next   = "A7 - present"
        }

        "A7 - present" = {
          Type = "Choice"
          Choices = [
            { Condition = "{% $states.input.found %}", Next = "A7 - lire" },
            { Condition = "{% $polls < ${local.tldoole_detect_max_polls} %}", Next = "A7 - attendre" },
          ]
          Default = "A7 - delai depasse"
        }

        "A7 - delai depasse" = {
          Type  = "Fail"
          Error = "MarkerTimeout"
          Cause = "A7 n'a pas ecrit son marqueur dans le delai."
        }

        "A7 - lire" = {
          Type     = "Task"
          Resource = "arn:aws:states:::aws-sdk:s3:getObject"
          Arguments = {
            Bucket = aws_s3_bucket.this.bucket
            Key    = "{% 'clients/' & $clientId & '/tldoole/runs/' & $runId & '/detect.json' %}"
          }
          Output = "{% $parse($states.result.Body) %}"
          Next   = "A7 - verifier"
        }

        "A7 - verifier" = {
          Type = "Choice"
          Choices = [
            {
              Condition = "{% $states.input.status = 'ok' and $count($states.input.video_ids) > 0 %}"
              Assign    = { videoIds = "{% $states.input.video_ids %}", gaps = "{% $states.input.gaps %}" }
              Next      = "Videos"
            },
            { Condition = "{% $states.input.status = 'ok' %}", Next = "Rien a produire" },
          ]
          Default = "A7 - echec"
        }

        "A7 - echec" = {
          Type  = "Fail"
          Error = "AgentError"
          Cause = "{% $string($states.input.error) %}"
        }

        "Rien a produire" = {
          Type   = "Succeed"
          Output = "{% {'client_id': $clientId, 'videos': []} %}"
        }

        "Videos" = {
          Type           = "Map"
          Comment        = "Une iteration par video : A8, MediaConvert, finalisation."
          Items          = "{% $videoIds %}"
          ItemSelector   = { client_id = "{% $clientId %}", video_id = "{% $states.context.Map.Item.Value %}" }
          MaxConcurrency = var.tldoole_max_concurrency
          ItemProcessor = {
            ProcessorConfig = { Mode = "INLINE" }
            StartAt         = "Video - preparer"
            States          = local.tldoole_video_states
          }
          Output = "{% {'client_id': $clientId, 'videos': $states.result} %}"
          Next   = "Termine"
        }

        "Termine" = {
          Type = "Succeed"
        }
      },
    )
  }
}

# -----------------------------------------------------------------------------
# Runtime tldoole : Polly et lancement de la machine, en plus du role commun
# (agentcore.tf : journaux, modele, Knowledge Base, Guardrail, clients/).
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "tldoole_runtime" {
  # SynthesizeSpeech n'a pas de ressource propre (seuls les lexiques en ont).
  statement {
    sid       = "Narration"
    actions   = ["polly:SynthesizeSpeech"]
    resources = ["*"]
  }

  statement {
    sid       = "StartProduction"
    actions   = ["states:StartExecution"]
    resources = [local.tldoole_state_machine_arn]
  }
}

resource "aws_iam_role_policy" "tldoole_runtime" {
  name   = "tldoole"
  role   = aws_iam_role.agentcore["tldoole"].id
  policy = data.aws_iam_policy_document.tldoole_runtime.json
}

# -----------------------------------------------------------------------------
# Role MediaConvert : lit les elements d'une video et ecrit son MP4, sous
# clients/*/tldoole/ seulement.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "tldoole_mediaconvert_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["mediaconvert.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "tldoole_mediaconvert" {
  name               = "${local.prefix}-tldoole-mediaconvert"
  description        = "Role des jobs MediaConvert de tldoole."
  assume_role_policy = data.aws_iam_policy_document.tldoole_mediaconvert_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "tldoole_mediaconvert" {
  statement {
    sid       = "VideoAssets"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = [local.tldoole_media_objects_arn]
  }
}

resource "aws_iam_role_policy" "tldoole_mediaconvert" {
  name   = "video-assets"
  role   = aws_iam_role.tldoole_mediaconvert.id
  policy = data.aws_iam_policy_document.tldoole_mediaconvert.json
}

# -----------------------------------------------------------------------------
# Machine Step Functions et son role.
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "tldoole" {
  name              = "/aws/vendedlogs/states/${local.tldoole_name}"
  retention_in_days = 14
  kms_key_id        = aws_kms_key.logs.arn
  tags              = local.common_tags
}

resource "aws_iam_role" "tldoole_sfn" {
  name               = "${local.prefix}-tldoole-sfn"
  description        = "Role de la machine Step Functions de tldoole."
  assume_role_policy = data.aws_iam_policy_document.collecte_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "tldoole_sfn" {
  statement {
    sid       = "InvokeTldoole"
    actions   = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = [local.tldoole_runtime_arn, "${local.tldoole_runtime_arn}/*"]
  }

  # Anti-rebond (ETag du journal) et sonde des marqueurs, par listObjectsV2 :
  # motifs de cles exacts, comme les roles des runtimes (agentcore.tf).
  statement {
    sid       = "ListJournalAndMarkers"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.this.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["clients/*/journal.md", "clients/*/tldoole/*"]
    }
  }

  statement {
    sid       = "ReadMarkers"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.this.arn}/clients/*/tldoole/*"]
  }

  statement {
    sid       = "Montage"
    actions   = ["mediaconvert:CreateJob", "mediaconvert:GetJob", "mediaconvert:CancelJob"]
    resources = ["arn:${local.partition}:mediaconvert:${var.aws_region}:${local.account_id}:*"]
  }

  statement {
    sid       = "PassMediaConvertRole"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.tldoole_mediaconvert.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["mediaconvert.amazonaws.com"]
    }
  }

  # Regle geree par Step Functions pour l'integration createJob.sync.
  statement {
    sid       = "SyncRule"
    actions   = ["events:PutTargets", "events:PutRule", "events:DescribeRule"]
    resources = ["arn:${local.partition}:events:${var.aws_region}:${local.account_id}:rule/StepFunctionsGetEventsForMediaConvertJobRule"]
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

resource "aws_iam_role_policy" "tldoole_sfn" {
  name   = "tldoole"
  role   = aws_iam_role.tldoole_sfn.id
  policy = data.aws_iam_policy_document.tldoole_sfn.json
}

resource "aws_sfn_state_machine" "tldoole" {
  name       = local.tldoole_name
  role_arn   = aws_iam_role.tldoole_sfn.arn
  definition = jsonencode(local.tldoole_definition)

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.tldoole.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = local.common_tags

  depends_on = [aws_iam_role_policy.tldoole_sfn]
}

# -----------------------------------------------------------------------------
# Declencheur : chaque ecriture de clients/<id>/journal.md par le runtime
# profile (une par requete) lance la machine; l'anti-rebond ne garde que la
# derniere version. Seule notification du bucket : EventBridge.
# -----------------------------------------------------------------------------
resource "aws_s3_bucket_notification" "this" {
  bucket      = aws_s3_bucket.this.id
  eventbridge = true
}

resource "aws_cloudwatch_event_rule" "tldoole_journal" {
  name        = "${local.tldoole_name}-journal"
  description = "Journal du profil ecrit : tldoole cherche les concepts a expliquer."
  state       = var.tldoole_trigger_enabled ? "ENABLED" : "DISABLED"
  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [aws_s3_bucket.this.bucket] }
      object = { key = [{ wildcard = "clients/*/journal.md" }] }
    }
  })
  tags = local.common_tags
}

data "aws_iam_policy_document" "tldoole_events_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "tldoole_events" {
  name               = "${local.prefix}-tldoole-events"
  description        = "Role d'EventBridge : lance la machine tldoole."
  assume_role_policy = data.aws_iam_policy_document.tldoole_events_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "tldoole_events" {
  statement {
    sid       = "StartTldoole"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.tldoole.arn]
  }
}

resource "aws_iam_role_policy" "tldoole_events" {
  name   = "start-tldoole"
  role   = aws_iam_role.tldoole_events.id
  policy = data.aws_iam_policy_document.tldoole_events.json
}

resource "aws_cloudwatch_event_target" "tldoole_journal" {
  rule     = aws_cloudwatch_event_rule.tldoole_journal.name
  arn      = aws_sfn_state_machine.tldoole.arn
  role_arn = aws_iam_role.tldoole_events.arn

  retry_policy {
    maximum_event_age_in_seconds = 600
    maximum_retry_attempts       = 2
  }
}
