# =============================================================================
# Variables specifiques au Scheduler.
# =============================================================================
variable "collecte_schedule_expression" {
  description = "Cadence de la veille (expression rate() ou cron() d'EventBridge Scheduler)."
  type        = string
  default     = "rate(6 hours)"
}

variable "collecte_schedule_enabled" {
  description = "Active la collecte periodique."
  type        = bool
  default     = true
}
