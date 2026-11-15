# =============================================================================
# Service : scenarios probabilistes (simulation seulement).
#
# Un job SageMaker Processing calcule hors du poste la table des scenarios
# (schema 0.2 de alphaforge/scenarios/schema.py, app/CONTRACTS.md section 10) :
# distributions de resultats par melange d'actifs, horizon et modele, avec
# intervalles de confiance. Le code
# calcule ; les agents ne font que lire et expliquer la table precalculee.
#
#   Preparer -> Requete (S3) -> Calcul (SageMaker Processing, .sync)
#            -> Marqueur _done.json -> Pointeur scenarios/latest.json
#
# Pourquoi chaque service (le jury penalise l'empilement) :
#   SageMaker Processing  calcul lourd (bootstrap, HMM, 10^5 trajectoires)
#                         reproductible : image AWS figee, code fige par
#                         release_id, entrees et sorties tracees dans S3.
#   Step Functions        orchestre le job sans serveur (integration .sync)
#                         et ecrit le marqueur et le pointeur ; meme modele que
#                         la collecte, un graphe lisible dans la demo.
#   Glue + Athena         la table devient interrogeable en SQL (validation,
#                         demo, audit) sans base de donnees a gerer.
#
# Disposition S3 (bucket existant, hors general/ : la Knowledge Base ne
# l'indexe pas) :
#   scenarios/code/<release_id>/            run.sh et scenarios.zip (Terraform)
#   scenarios/input/requests/<run_id>/      request.json (Step Functions)
#   scenarios/output/<run_id>/              sorties du job : manifest.json,
#                                           request.json, runtime/ (JSON et CSV
#                                           compacts lus par l'outil
#                                           scenario_risk), rapports
#   scenarios/output/<run_id>/table/        scenarios.parquet, seul lu par Athena
#   scenarios/output/<run_id>/_done.json    marqueur (Step Functions)
#   scenarios/latest.json                   dernier run reussi (Step Functions)
#   scenarios/athena-results/               resultats des requetes Athena
#
# Reseau : configuration SageMaker par defaut (pas de VPC, pas d'isolation
# reseau), donc acces Internet sortant. Le job en a besoin : il reconstruit
# les donnees mensuelles 1926-2026 depuis les sources publiques (FRED, Ken
# French, Shiller, or, Yahoo Finance) par alphaforge.finance.backtest.build_data.
# Ces donnees ne sont ni versionnees ni dans le bundle de code (licences
# Yahoo, Moody's, OCDE) : elles vivent seulement dans le volume du job.
#
# Desactivable par scenarios_enabled = false.
# =============================================================================

locals {
  scenarios_count = var.scenarios_enabled ? 1 : 0

  scenarios_name     = "${local.prefix}-scenarios"
  scenarios_job_stem = "${local.prefix}-scn-"
  scenarios_bucket   = aws_s3_bucket.this.bucket
  scenarios_s3       = "s3://${aws_s3_bucket.this.bucket}/scenarios"

  scenarios_code_prefix = "scenarios/code/${var.release_id}/"

  # Bundle construit par app/agents/scripts/package.sh (artefact
  # agents-package) seulement si ALPHAFORGE_PACKAGE_SCENARIOS=1.
  scenarios_code_files = var.scenarios_enabled ? fileset("${path.module}/build/scenarios", "{run.sh,scenarios.zip}") : toset([])

  # Chemins dans le conteneur (contrat avec le code du job).
  scenarios_paths = {
    code    = "/opt/ml/processing/input/code"
    request = "/opt/ml/processing/input/request"
    output  = "/opt/ml/processing/output"
  }

  scenarios_ecr_repository_arn = "arn:${local.partition}:ecr:${var.aws_region}:683313688378:repository/sagemaker-scikit-learn"
  scenarios_log_group_name     = "/aws/sagemaker/ProcessingJobs"

  # Lu par la politique de la cle des journaux (stepfunctions.tf).
  scenarios_kms_log_group_arns = var.scenarios_enabled ? ["arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:${local.scenarios_log_group_name}"] : []

  # Entrees du job : le code (fige par release_id) et la requete du run.
  scenarios_input_code = {
    InputName  = "code"
    AppManaged = false
    S3Input = {
      S3Uri                  = "${local.scenarios_s3}/code/${var.release_id}/"
      LocalPath              = local.scenarios_paths.code
      S3DataType             = "S3Prefix"
      S3InputMode            = "File"
      S3DataDistributionType = "FullyReplicated"
    }
  }

  # Les tags par defaut du fournisseur ne s'appliquent pas aux jobs crees par
  # Step Functions : on les passe explicitement.
  scenarios_job_tags = [for k, v in local.common_tags : { Key = k, Value = v }]

  # Miroir de schema.COLUMNS (app/agents/src/alphaforge/scenarios/schema.py,
  # schema 0.2), a garder synchronise. Types parquet -> Athena : int32 -> int,
  # int64 -> bigint, float64 -> double, bool -> boolean.
  scenarios_columns = [
    { name = "schema_version", type = "string", comment = "Version du schema de la table" },
    { name = "model_id", type = "string", comment = "Generateur : bootstrap par blocs, HMM, bootstrap des parametres" },
    { name = "family", type = "string", comment = "Famille de donnees : CAD77, CAD71, USD1926" },
    { name = "currency", type = "string", comment = "Devise de la famille" },
    { name = "mix_id", type = "string", comment = "Poids arrondis a 5 %, ex. ca15-us25-bd45-cs10-gd05" },
    { name = "horizon_years", type = "int", comment = "Horizon en annees" },
    { name = "basis", type = "string", comment = "nominal ou real" },
    { name = "metric", type = "string", comment = "ret_ann_p05..p90, wealth_p10, mdd_p50|p90, cvar95_12m, p_loss_gt_*, p_mdd_gt_*" },
    { name = "value", type = "double", comment = "Estimation ponctuelle (fraction)" },
    { name = "ci_lo", type = "double", comment = "Borne basse de l'IC a 90 %" },
    { name = "ci_hi", type = "double", comment = "Borne haute de l'IC a 90 %" },
    { name = "n_paths", type = "int", comment = "Trajectoires simulees" },
    { name = "n_boot", type = "int", comment = "Reechantillonnages des parametres (IC)" },
    { name = "seed", type = "bigint", comment = "Graine du generateur" },
    { name = "fitted_through", type = "string", comment = "Dernier mois utilise (AAAA-MM)" },
    { name = "window_start", type = "string", comment = "Premier mois de la fenetre (AAAA-MM)" },
    { name = "n_hist_months", type = "int", comment = "Mois d'historique de la fenetre" },
    { name = "hypothese", type = "boolean", comment = "Ligne fondee sur une hypothese (crypto 2014+)" },
    { name = "data_sha256", type = "string", comment = "Empreinte des donnees d'entree" },
    { name = "code_sha", type = "string", comment = "release_id du code du job" },
  ]

  scenarios_definition = {
    Comment        = "Scenarios probabilistes AlphaForge AI (simulation) : job SageMaker Processing, marqueur, pointeur latest.json."
    QueryLanguage  = "JSONata"
    TimeoutSeconds = var.scenarios_max_runtime_seconds + 1800
    StartAt        = "Preparer"
    States = {
      "Preparer" = {
        Type = "Pass"
        Assign = {
          runId  = "{% $exists($states.input.run_id) ? $states.input.run_id : $states.context.Execution.Name %}"
          params = "{% $exists($states.input.params) ? $states.input.params : {} %}"
        }
        Next = "Verifier run_id"
      }

      # Le run_id entre dans les cles S3 et dans le nom du job SageMaker
      # (ni point ni souligne, 63 caracteres au plus) ; un UUID passe.
      "Verifier run_id" = {
        Type = "Choice"
        Choices = [{
          Condition = "{% $type($runId) = 'string' and $contains($runId, /^[A-Za-z0-9-]{1,36}$/) %}"
          Next      = "Requete - ecrire"
        }]
        Default = "run_id invalide"
      }

      "run_id invalide" = {
        Type  = "Fail"
        Error = "BadRunId"
        Cause = "run_id doit suivre ^[A-Za-z0-9-]{1,36}$ (le nom de l'execution, un UUID, par defaut)."
      }

      # Les parametres de l'execution deviennent une entree tracee du job.
      # Ecriture conditionnelle (IfNoneMatch "*") : un run_id deja utilise
      # (request.json present) fait echouer l'execution ici, avant tout
      # calcul et sans rien reecrire (S3 repond 412 PreconditionFailed).
      # Atomique, et sans droit de plus que s3:PutObject (pas de ListBucket).
      "Requete - ecrire" = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:s3:putObject"
        Arguments = {
          Bucket      = local.scenarios_bucket
          Key         = "{% 'scenarios/input/requests/' & $runId & '/request.json' %}"
          IfNoneMatch = "*"
          ContentType = "application/json"
          Body        = "{% $string({'schema': 'scenarios-request/v0.1', 'run_id': $runId, 'release': '${var.release_id}', 'execution': $states.context.Execution.Id, 'requested_at': $now(), 'params': $params}) %}"
        }
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Output      = "{% {'status': 'error', 'run_id': $runId, 'error': $states.errorOutput} %}"
          Next        = "Requete refusee"
        }]
        Next = "Calcul"
      }

      # Le plus souvent : run_id deja utilise (PreconditionFailed). Aucun
      # marqueur n'est ecrit, les sorties du run existant restent intactes.
      "Requete refusee" = {
        Type  = "Fail"
        Error = "RunIdAlreadyUsed"
        Cause = "{% 'request.json non ecrit (run_id deja utilise si PreconditionFailed) : ' & $string($states.input.error) %}"
      }

      "Calcul" = {
        Type           = "Task"
        Comment        = "Job SageMaker Processing, suivi jusqu'a sa fin (.sync)."
        Resource       = "arn:aws:states:::sagemaker:createProcessingJob.sync"
        TimeoutSeconds = var.scenarios_max_runtime_seconds + 900
        Arguments = {
          ProcessingJobName = "{% $substring('${local.scenarios_job_stem}' & $runId, 0, 63) %}"
          RoleArn           = one(aws_iam_role.scenarios_job[*].arn)
          AppSpecification = {
            ImageUri            = var.scenarios_image_uri
            ContainerEntrypoint = ["/bin/sh", "${local.scenarios_paths.code}/run.sh"]
            ContainerArguments = [
              "--request", "${local.scenarios_paths.request}/request.json",
              "--output", local.scenarios_paths.output,
            ]
          }
          Environment = {
            ALPHAFORGE_RUN_ID       = "{% $runId %}"
            ALPHAFORGE_RELEASE      = var.release_id
            ALPHAFORGE_ENV          = var.environment
            ALPHAFORGE_REGION       = var.aws_region
            ALPHAFORGE_IMAGE        = var.scenarios_image_uri
            PYTHONUNBUFFERED        = "1"
            PYTHONDONTWRITEBYTECODE = "1"
          }
          ProcessingInputs = [
            local.scenarios_input_code,
            {
              InputName  = "request"
              AppManaged = false
              S3Input = {
                S3Uri                  = "{% '${local.scenarios_s3}/input/requests/' & $runId & '/' %}"
                LocalPath              = local.scenarios_paths.request
                S3DataType             = "S3Prefix"
                S3InputMode            = "File"
                S3DataDistributionType = "FullyReplicated"
              }
            },
          ]
          # Pas de KmsKeyId : le chiffrement par defaut du bucket (cle du
          # projet) s'applique, sans kms:Encrypt a accorder au role du job.
          ProcessingOutputConfig = {
            Outputs = [{
              OutputName = "run"
              AppManaged = false
              S3Output = {
                S3Uri        = "{% '${local.scenarios_s3}/output/' & $runId & '/' %}"
                LocalPath    = local.scenarios_paths.output
                S3UploadMode = "EndOfJob"
              }
            }]
          }
          ProcessingResources = {
            ClusterConfig = {
              InstanceCount  = var.scenarios_instance_count
              InstanceType   = var.scenarios_instance_type
              VolumeSizeInGB = var.scenarios_volume_size_gb
            }
          }
          StoppingCondition = {
            MaxRuntimeInSeconds = var.scenarios_max_runtime_seconds
          }
          Tags = local.scenarios_job_tags
        }
        Assign = {
          job = "{% {'name': $states.result.ProcessingJobName, 'arn': $states.result.ProcessingJobArn, 'status': $states.result.ProcessingJobStatus, 'started_at': $states.result.ProcessingStartTime, 'ended_at': $states.result.ProcessingEndTime} %}"
        }
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Output      = "{% {'status': 'error', 'run_id': $runId, 'error': $states.errorOutput} %}"
          Next        = "Marqueur d'echec - ecrire"
        }]
        Next = "Marqueur - ecrire"
      }

      "Marqueur - ecrire" = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:s3:putObject"
        Arguments = {
          Bucket      = local.scenarios_bucket
          Key         = "{% 'scenarios/output/' & $runId & '/_done.json' %}"
          IfNoneMatch = "*"
          ContentType = "application/json"
          Body        = "{% $string({'status': 'ok', 'run_id': $runId, 'release': '${var.release_id}', 'image': '${var.scenarios_image_uri}', 'processing_job': $job, 'output_prefix': 'scenarios/output/' & $runId & '/', 'table_prefix': 'scenarios/output/' & $runId & '/table/', 'finished_at': $now()}) %}"
        }
        Next = "Pointeur - ecrire"
      }

      # Ecrit en dernier : latest.json ne designe qu'un run complet.
      "Pointeur - ecrire" = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:s3:putObject"
        Arguments = {
          Bucket      = local.scenarios_bucket
          Key         = "scenarios/latest.json"
          ContentType = "application/json"
          Body        = "{% $string({'run_id': $runId, 'release': '${var.release_id}', 'marker': 'scenarios/output/' & $runId & '/_done.json', 'output_prefix': 'scenarios/output/' & $runId & '/', 'manifest': 'scenarios/output/' & $runId & '/manifest.json', 'updated_at': $now()}) %}"
        }
        Next = "Termine"
      }

      "Termine" = {
        Type   = "Succeed"
        Output = "{% {'run_id': $runId, 'processing_job': $job, 'latest': 'scenarios/latest.json'} %}"
      }

      # Echec du job : marqueur status=error, latest.json inchange. Les deux
      # marqueurs sont ecrits sous condition (IfNoneMatch "*") : un marqueur
      # existant, celui d'un run reussi par exemple, n'est jamais reecrit.
      "Marqueur d'echec - ecrire" = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:s3:putObject"
        Arguments = {
          Bucket      = local.scenarios_bucket
          Key         = "{% 'scenarios/output/' & $runId & '/_done.json' %}"
          IfNoneMatch = "*"
          ContentType = "application/json"
          Body        = "{% $string($merge([$states.input, {'release': '${var.release_id}', 'finished_at': $now()}])) %}"
        }
        Output = "{% $states.input %}"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Output      = "{% $states.input %}"
          Next        = "Echec"
        }]
        Next = "Echec"
      }

      "Echec" = {
        Type  = "Fail"
        Error = "ScenariosJobFailed"
        Cause = "{% $string($states.input) %}"
      }
    }
  }
}

# -----------------------------------------------------------------------------
# Code du job : un prefixe par commit, comme runtime/agents-<sha>.zip.
# -----------------------------------------------------------------------------
resource "aws_s3_object" "scenarios_code" {
  for_each = local.scenarios_code_files

  bucket       = aws_s3_bucket.this.id
  key          = "${local.scenarios_code_prefix}${each.value}"
  source       = "${path.module}/build/scenarios/${each.value}"
  content_type = each.value == "run.sh" ? "text/x-shellscript" : "application/zip"

  depends_on = [aws_s3_bucket_server_side_encryption_configuration.this]

  lifecycle {
    create_before_destroy = true
  }
}

# Avertissement (pas une erreur) : la chaine est deployee mais le bundle du
# job manque, donc une execution echouera au demarrage du job.
check "scenarios_code_bundle" {
  assert {
    condition     = !var.scenarios_enabled || length(local.scenarios_code_files) == 2
    error_message = "scenarios_enabled = true mais infra/build/scenarios/{run.sh,scenarios.zip} est absent : package.sh doit tourner avec ALPHAFORGE_PACKAGE_SCENARIOS=1 (variable de depot GitHub du meme nom pour la CI). Une execution de ${local.scenarios_name} echouera."
  }
}

# -----------------------------------------------------------------------------
# Role d'execution du job SageMaker : lit son code et ses entrees, ecrit
# seulement sous scenarios/output/ (jamais le marqueur _done.json, reserve a
# Step Functions), journalise. Pas de Bedrock, aucun autre prefixe du bucket.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "scenarios_job_trust" {
  count = local.scenarios_count

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scenarios_job" {
  count = local.scenarios_count

  name               = "${local.prefix}-scenarios-job"
  description        = "Role d'execution du job SageMaker Processing des scenarios."
  assume_role_policy = data.aws_iam_policy_document.scenarios_job_trust[0].json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "scenarios_job" {
  count = local.scenarios_count

  statement {
    sid       = "BucketLocation"
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.this.arn]
  }

  statement {
    sid       = "ListInputs"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.this.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["scenarios/code/*", "scenarios/input/requests/*"]
    }
  }

  statement {
    sid       = "ReadInputs"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.this.arn}/scenarios/code/*", "${aws_s3_bucket.this.arn}/scenarios/input/requests/*"]
  }

  statement {
    sid       = "WriteOutputs"
    actions   = ["s3:PutObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.this.arn}/scenarios/output/*"]
  }

  statement {
    sid       = "NeverWriteMarker"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this.arn}/scenarios/output/*/_done.json"]
  }

  statement {
    sid       = "PullAwsImage"
    actions   = ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [local.scenarios_ecr_repository_arn]
  }

  statement {
    sid       = "EcrToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid       = "JobLogs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = ["arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:${local.scenarios_log_group_name}:*"]
  }

  statement {
    sid       = "Metrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["/aws/sagemaker/ProcessingJobs"]
    }
  }
}

resource "aws_iam_role_policy" "scenarios_job" {
  count = local.scenarios_count

  name   = "scenarios-job"
  role   = aws_iam_role.scenarios_job[0].id
  policy = data.aws_iam_policy_document.scenarios_job[0].json
}

# Journaux du job, chiffres par la cle des journaux du projet (stepfunctions.tf)
# et purges apres 14 jours. Le nom est impose par SageMaker et unique dans le
# compte : il n'existait pas le 2026-11-14 (describe-log-groups).
resource "aws_cloudwatch_log_group" "scenarios_job" {
  count = local.scenarios_count

  name              = local.scenarios_log_group_name
  retention_in_days = 14
  kms_key_id        = aws_kms_key.logs.arn
  tags              = local.common_tags
}

# -----------------------------------------------------------------------------
# Machine Step Functions des scenarios et son role.
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "scenarios" {
  count = local.scenarios_count

  name              = "/aws/vendedlogs/states/${local.scenarios_name}"
  retention_in_days = 14
  kms_key_id        = aws_kms_key.logs.arn
  tags              = local.common_tags
}

# Meme confiance que la collecte (machines ${local.prefix}-*) : on reutilise
# data.aws_iam_policy_document.collecte_trust de stepfunctions.tf.
resource "aws_iam_role" "scenarios" {
  count = local.scenarios_count

  name               = local.scenarios_name
  description        = "Role de la machine Step Functions des scenarios."
  assume_role_policy = data.aws_iam_policy_document.collecte_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "scenarios" {
  count = local.scenarios_count

  statement {
    sid     = "WriteRequestMarkerPointer"
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.this.arn}/scenarios/input/requests/*",
      "${aws_s3_bucket.this.arn}/scenarios/output/*/_done.json",
      "${aws_s3_bucket.this.arn}/scenarios/latest.json",
    ]
  }

  statement {
    sid = "ProcessingJobs"
    actions = [
      "sagemaker:CreateProcessingJob",
      "sagemaker:DescribeProcessingJob",
      "sagemaker:StopProcessingJob",
      "sagemaker:AddTags",
      "sagemaker:ListTags",
    ]
    resources = ["arn:${local.partition}:sagemaker:${var.aws_region}:${local.account_id}:processing-job/${local.scenarios_job_stem}*"]
  }

  # Regle EventBridge geree par Step Functions pour l'integration .sync.
  statement {
    sid       = "SyncRule"
    actions   = ["events:PutTargets", "events:PutRule", "events:DescribeRule"]
    resources = ["arn:${local.partition}:events:${var.aws_region}:${local.account_id}:rule/StepFunctionsGetEventsForSageMakerProcessingJobsRule"]
  }

  statement {
    sid       = "PassJobRole"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.scenarios_job[0].arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["sagemaker.amazonaws.com"]
    }
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

resource "aws_iam_role_policy" "scenarios" {
  count = local.scenarios_count

  name   = "scenarios"
  role   = aws_iam_role.scenarios[0].id
  policy = data.aws_iam_policy_document.scenarios[0].json
}

resource "aws_sfn_state_machine" "scenarios" {
  count = local.scenarios_count

  name       = local.scenarios_name
  role_arn   = aws_iam_role.scenarios[0].arn
  definition = jsonencode(local.scenarios_definition)

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.scenarios[0].arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = local.common_tags

  depends_on = [aws_iam_role_policy.scenarios]
}

# -----------------------------------------------------------------------------
# Catalogue Glue et groupe de travail Athena : la table parquet en SQL.
# Projection de partition "injected" sur run_id : aucune partition a ajouter
# apres un run, mais chaque requete nomme son run_id (WHERE run_id = '...'),
# lu dans scenarios/latest.json.
# -----------------------------------------------------------------------------
resource "aws_glue_catalog_database" "scenarios" {
  count = local.scenarios_count

  name        = "${local.name_snake}_scenarios"
  description = "Scenarios probabilistes AlphaForge AI (simulation) : sorties du job SageMaker."
  tags        = local.common_tags
}

resource "aws_glue_catalog_table" "scenarios" {
  count = local.scenarios_count

  name          = "scenarios"
  database_name = aws_glue_catalog_database.scenarios[0].name
  description   = "Table des scenarios, schema 0.2 (app/CONTRACTS.md section 10). Une ligne par model_id, family, mix_id, horizon_years, basis, metric."
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification"            = "parquet"
    "EXTERNAL"                  = "TRUE"
    "projection.enabled"        = "true"
    "projection.run_id.type"    = "injected"
    "storage.location.template" = "${local.scenarios_s3}/output/$${run_id}/table/"
  }

  partition_keys {
    name    = "run_id"
    type    = "string"
    comment = "Execution Step Functions qui a produit la table"
  }

  storage_descriptor {
    location      = "${local.scenarios_s3}/output/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    dynamic "columns" {
      for_each = local.scenarios_columns
      content {
        name    = columns.value.name
        type    = columns.value.type
        comment = columns.value.comment
      }
    }
  }
}

resource "aws_athena_workgroup" "scenarios" {
  count = local.scenarios_count

  name          = local.scenarios_name
  description   = "Requetes sur la table des scenarios ; resultats chiffres par la cle du bucket."
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.scenarios_athena_bytes_scanned_cutoff

    result_configuration {
      output_location = "${local.scenarios_s3}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_KMS"
        kms_key_arn       = aws_kms_key.s3.arn
      }
    }
  }

  tags = local.common_tags
}
