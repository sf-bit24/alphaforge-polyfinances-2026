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

variable "portfolio_enabled" {
  description = "Deploie le runtime AgentCore portfolio (A3, lentilles, Judge du volet finance), avec son zip runtime/agents-portfolio-<release>.zip construit par package.sh si ALPHAFORGE_PACKAGE_PORTFOLIO=1. Desactive par defaut tant que l'equipe n'a pas valide : une fusion dans master declenche un apply automatique (infra.yml)."
  type        = bool
  default     = false
}

variable "portfolio_market_data_sha" {
  description = "Empreinte (data_sha256 de data_version.json) des donnees longues du moteur finance, deposees a la main sous runtime/market/long/<sha>/ du bucket des bases OKF : parquets prives (licences yfinance, Moody's, OCDE), jamais dans git ni dans le zip. Le runtime portfolio les telecharge au premier build."
  type        = string
  default     = "008f122d5da4f8f7"

  validation {
    condition     = can(regex("^[0-9a-f]{16}$", var.portfolio_market_data_sha))
    error_message = "portfolio_market_data_sha : 16 caracteres hexadecimaux (data_sha256 de data_version.json)."
  }
}
