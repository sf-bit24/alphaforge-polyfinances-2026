# =============================================================================
# Outputs specifiques aux scenarios (null si scenarios_enabled = false).
# =============================================================================
output "scenarios_state_machine_arn" {
  description = "Machine des scenarios (StartExecution, app/CONTRACTS.md section 10)"
  value       = one(aws_sfn_state_machine.scenarios[*].arn)
}

output "scenarios_state_machine_name" {
  description = "Nom de la machine des scenarios"
  value       = one(aws_sfn_state_machine.scenarios[*].name)
}

output "scenarios_job_role_arn" {
  description = "Role d'execution du job SageMaker Processing"
  value       = one(aws_iam_role.scenarios_job[*].arn)
}

output "scenarios_code_prefix" {
  description = "Prefixe S3 du code du job pour ce release_id"
  value       = var.scenarios_enabled ? local.scenarios_code_prefix : null
}

output "scenarios_image_uri" {
  description = "Image SageMaker scikit-learn d'AWS utilisee par le job"
  value       = var.scenarios_enabled ? var.scenarios_image_uri : null
}

output "scenarios_glue_database" {
  description = "Base Glue de la table des scenarios"
  value       = one(aws_glue_catalog_database.scenarios[*].name)
}

output "scenarios_athena_workgroup" {
  description = "Groupe de travail Athena des scenarios"
  value       = one(aws_athena_workgroup.scenarios[*].name)
}
