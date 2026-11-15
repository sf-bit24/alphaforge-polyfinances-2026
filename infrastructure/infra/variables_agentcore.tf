# =============================================================================
# Variables specifiques au service AgentCore.
# =============================================================================
variable "agentcore_model_id" {
  description = "Profil d'inference Bedrock de tous les agents (decision de l'equipe : Claude Opus 5.5 partout, effort regle par agent dans le code)."
  type        = string
  default     = "us.anthropic.claude-opus-5-5"
}

variable "sec_contact_email" {
  description = "Courriel ajoute au User-Agent pour la SEC seulement (acces equitable d'EDGAR). Vide : la SEC repond 403 et ses hotes sont declares bloques."
  type        = string
  default     = ""

  validation {
    condition     = var.sec_contact_email == "" || can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.sec_contact_email))
    error_message = "sec_contact_email doit etre vide ou un courriel."
  }
}

variable "agentcore_idle_session_timeout" {
  description = "Secondes d'inactivite avant qu'AgentCore libere la microVM d'une session."
  type        = number
  default     = 900
}

variable "agentcore_max_session_lifetime" {
  description = "Duree de vie maximale d'une session AgentCore, en secondes (8 h)."
  type        = number
  default     = 28800
}

variable "portfolio_enabled" {
  description = "Deploie le runtime AgentCore portfolio (A3, lentilles, Judge du volet finance), avec son zip runtime/agents-portfolio-<release>.zip construit par package.sh si ALPHAFORGE_PACKAGE_PORTFOLIO=1. Desactive par defaut tant que l'equipe n'a pas valide : une fusion dans master declenche un apply automatique (infra.yml)."
  type        = bool
  default     = false
}
