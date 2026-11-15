# =============================================================================
# Variables specifiques au service AgentCore.
# =============================================================================
variable "agentcore_model_id" {
  description = "Profil d'inference Bedrock de tous les agents (decision de l'equipe : Claude Opus 5.5 partout, effort regle par agent dans le code)."
  type        = string
  default     = "us.anthropic.claude-opus-5-5"
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
