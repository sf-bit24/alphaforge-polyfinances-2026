# =============================================================================
# Service : Amazon EventBridge Scheduler, veille periodique.
# Lance la machine de collecte a intervalle regulier ; l'interface peut aussi
# la lancer a la demande.
# =============================================================================

data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.prefix}-scheduler"
  description        = "Role du Scheduler : lance la machine de collecte."
  assume_role_policy = data.aws_iam_policy_document.scheduler_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "StartCollecte"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.collecte.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "start-collecte"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "collecte" {
  name        = "${local.prefix}-collecte"
  description = "Veille : collecte A4-A5-A6 et ingestion de la base generale."

  schedule_expression          = var.collecte_schedule_expression
  schedule_expression_timezone = "America/Toronto"
  state                        = var.collecte_schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.collecte.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ source = "scheduler" })

    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}
