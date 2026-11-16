# =============================================================================
# Variables specifiques au Scheduler.
# =============================================================================
variable "collecte_schedule_expression" {
  description = "Cadence de la collecte (expression rate() ou cron() d'EventBridge Scheduler, heure de Toronto) : chaque jour a 6 h par defaut."
  type        = string
  default     = "cron(0 6 * * ? *)"
}

variable "collecte_schedule_enabled" {
  description = "Active la collecte periodique."
  type        = bool
  default     = true
}
