# =============================================================================
# Variables specifiques a la tracabilite du volet finance.
# =============================================================================
variable "trace_retention_days" {
  description = "Retention Object Lock (mode GOVERNANCE) des objets du bucket de traces, en jours."
  type        = number
  default     = 3

  validation {
    condition     = var.trace_retention_days >= 1 && var.trace_retention_days <= 30
    error_message = "trace_retention_days doit etre entre 1 et 30 (compte jetable)."
  }
}

variable "xray_indexing_percentage" {
  description = "Part des spans indexes par X-Ray Transaction Search (100 = toutes les traces consultables)."
  type        = number
  default     = 100

  validation {
    condition     = var.xray_indexing_percentage > 0 && var.xray_indexing_percentage <= 100
    error_message = "xray_indexing_percentage doit etre dans ]0, 100]."
  }
}

variable "finance_trace_runtimes" {
  description = "Runtimes AgentCore autorises a ecrire le rejeu LLM et le journal des decisions (les collecteurs press et data n'y ont pas acces)."
  type        = list(string)
  default     = ["supervisor"]
}
