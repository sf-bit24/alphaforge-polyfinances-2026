# =============================================================================
# Outputs specifiques au Scheduler.
# =============================================================================
output "collecte_schedule_name" {
  description = "Planification de la veille"
  value       = aws_scheduler_schedule.collecte.name
}
