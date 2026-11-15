# =============================================================================
# Outputs specifiques a tldoole.
# =============================================================================
output "tldoole_state_machine_arn" {
  description = "Machine tldoole (detection A7, production A8, montage MediaConvert)"
  value       = aws_sfn_state_machine.tldoole.arn
}

output "tldoole_state_machine_name" {
  description = "Nom de la machine tldoole"
  value       = aws_sfn_state_machine.tldoole.name
}

output "tldoole_mediaconvert_role_arn" {
  description = "Role des jobs MediaConvert de tldoole"
  value       = aws_iam_role.tldoole_mediaconvert.arn
}

output "tldoole_journal_rule_name" {
  description = "Regle EventBridge qui lance tldoole quand un journal de profil change"
  value       = aws_cloudwatch_event_rule.tldoole_journal.name
}
