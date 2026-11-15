# =============================================================================
# Variables specifiques a la recherche par experts (recherche.tf).
# =============================================================================
variable "recherche_agent_timeout_seconds" {
  description = "Delai maximal d'un expert (chercheurs compris) ou d'A0 avant d'abandonner son marqueur."
  type        = number
  default     = 1800
}

variable "recherche_execution_timeout_seconds" {
  description = "Delai maximal d'une execution complete de la recherche."
  type        = number
  default     = 7200
}

variable "recherche_schedule_expression" {
  description = "Cadence de la veille des experts (expression rate() ou cron() d'EventBridge Scheduler)."
  type        = string
  default     = "cron(30 17 ? * MON-FRI *)"
}

variable "recherche_schedule_enabled" {
  description = "Active la veille quotidienne des experts (desactivee tant que l'equipe ne l'a pas validee)."
  type        = bool
  default     = false
}
