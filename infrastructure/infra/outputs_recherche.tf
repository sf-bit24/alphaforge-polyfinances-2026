# =============================================================================
# Outputs specifiques a la recherche par experts.
# =============================================================================
output "recherche_state_machine_arn" {
  description = "Machine de recherche par experts (l'interface la trouve par son nom)"
  value       = aws_sfn_state_machine.recherche.arn
}

output "recherche_state_machine_name" {
  description = "Nom de la machine de recherche par experts"
  value       = aws_sfn_state_machine.recherche.name
}

output "recherche_schedule_name" {
  description = "Planification de la veille des experts"
  value       = aws_scheduler_schedule.recherche.name
}
