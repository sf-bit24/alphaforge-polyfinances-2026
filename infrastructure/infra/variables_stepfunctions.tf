# =============================================================================
# Variables specifiques a Step Functions (collecte).
# =============================================================================
variable "collecte_poll_seconds" {
  description = "Intervalle entre deux sondages d'un marqueur ou de l'ingestion."
  type        = number
  default     = 15
}

variable "collecte_agent_timeout_seconds" {
  description = "Delai maximal d'un agent de collecte avant d'abandonner son marqueur."
  type        = number
  default     = 1200
}

variable "collecte_execution_timeout_seconds" {
  description = "Delai maximal d'une execution complete de la collecte."
  type        = number
  default     = 5400
}
