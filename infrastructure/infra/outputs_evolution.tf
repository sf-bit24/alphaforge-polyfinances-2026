# =============================================================================
# Outputs de l'evolution du portefeuille (null si la machine n'est pas deployee).
# =============================================================================
output "evolution_state_machine_arn" {
  description = "Machine d'evolution du portefeuille (tick mensuel et rejeu)"
  value       = one(aws_sfn_state_machine.evolution[*].arn)
}

output "evolution_role_arn" {
  description = "Role de la machine d'evolution (a ajouter a s3_kms_user_role_arns dans s3.tf)"
  value       = one(aws_iam_role.evolution[*].arn)
}

output "evolution_log_group_name" {
  description = "Groupe de journaux de la machine d'evolution"
  value       = one(aws_cloudwatch_log_group.evolution[*].name)
}
