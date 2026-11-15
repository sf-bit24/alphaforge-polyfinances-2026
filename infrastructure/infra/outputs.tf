# =============================================================================
# Outputs SOCLE (service-agnostiques)
# Les outputs specifiques a un service vivent dans services/<svc>/outputs_*.tf.
# =============================================================================
output "environment" {
  description = "Environnement deploye"
  value       = var.environment
}

output "project_name" {
  description = "Nom du projet (prefixe des ressources)"
  value       = var.project_name
}
