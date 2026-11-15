# =============================================================================
# Socle KMS (service-agnostique, aucune ressource).
# Chaque overlay qui chiffre cree SA cle, dont la politique nomme ses
# principaux : local.kms_admin_principal_arns administre (jamais le root du
# compte, jamais kms:*), les roles applicatifs ne font que chiffrer et
# dechiffrer via le service utile (kms:ViaService).
#
# Le compte Workshop du Datathon n'a pas de Landing Zone, donc pas de cle
# CloudWatch partagee : les journaux que la pile cree (Step Functions) sont
# chiffres par une cle du projet, dans stepfunctions.tf.
# =============================================================================

data "aws_caller_identity" "current" {}

# Role IAM qui execute Terraform (run role HCP Terraform), sans le suffixe de
# session.
data "aws_iam_session_context" "current" {
  arn = data.aws_caller_identity.current.arn
}

locals {
  kms_admin_principal_arns = distinct(concat(
    [data.aws_iam_session_context.current.issuer_arn],
    var.kms_admin_principal_arns,
  ))

  # Tout sauf kms:*.
  kms_admin_actions = [
    "kms:Create*",
    "kms:Describe*",
    "kms:Enable*",
    "kms:List*",
    "kms:Put*",
    "kms:Update*",
    "kms:Revoke*",
    "kms:Disable*",
    "kms:Get*",
    "kms:Delete*",
    "kms:TagResource",
    "kms:UntagResource",
    "kms:ScheduleKeyDeletion",
    "kms:CancelKeyDeletion",
    "kms:Encrypt",
    "kms:Decrypt",
    "kms:GenerateDataKey*",
  ]

  # Compte jetable (supprime le 2026-11-16) : fenetre minimale.
  kms_deletion_window_in_days = 7
}
