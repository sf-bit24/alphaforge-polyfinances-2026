# =============================================================================
# Outputs specifiques a Step Functions.
# =============================================================================
output "collecte_state_machine_arn" {
  description = "Machine de collecte (l'interface la trouve par son nom)"
  value       = aws_sfn_state_machine.collecte.arn
}

output "collecte_state_machine_name" {
  description = "Nom de la machine de collecte"
  value       = aws_sfn_state_machine.collecte.name
}
