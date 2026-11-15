# =============================================================================
# Variables specifiques a l'evolution du portefeuille dans le temps (tick
# mensuel et rejeu, issue #29). Voir evolution.tf.
# =============================================================================
variable "evolution_enabled" {
  description = "Deploie la machine d'evolution du portefeuille (tick mensuel et rejeu). Desactive par defaut tant que l'equipe n'a pas valide : une fusion dans master declenche un apply automatique (infra.yml). Il faut aussi evolution_portfolio_runtime_arn."
  type        = bool
  default     = false
}

variable "evolution_portfolio_runtime_arn" {
  description = "ARN du runtime AgentCore 'portfolio' du moteur financier (issue #29), qui traite les actions evolution.tick et evolution.replay. Vide : rien n'est deploye."
  type        = string
  default     = ""

  validation {
    condition     = var.evolution_portfolio_runtime_arn == "" || can(regex("^arn:aws[a-z-]*:bedrock-agentcore:[a-z0-9-]+:[0-9]{12}:runtime/[A-Za-z0-9_-]+$", var.evolution_portfolio_runtime_arn))
    error_message = "evolution_portfolio_runtime_arn doit etre vide ou un ARN de runtime AgentCore (arn:aws:bedrock-agentcore:<region>:<compte>:runtime/<id>)."
  }
}

variable "evolution_marker_max_polls" {
  description = "Nombre maximal de sondages (un toutes les 10 s) du marqueur _done.json d'un mois ou d'un rejeu avant echec MarkerTimeout. 60 = 10 minutes."
  type        = number
  default     = 60

  validation {
    condition     = var.evolution_marker_max_polls >= 1 && var.evolution_marker_max_polls <= 500
    error_message = "evolution_marker_max_polls doit etre entre 1 et 500."
  }
}

variable "evolution_demo_schedule" {
  description = "Cree le Schedule de demonstration (une execution = un mois simule). Exige aussi evolution_enabled et evolution_portfolio_runtime_arn."
  type        = bool
  default     = false
}

variable "evolution_demo_schedule_state" {
  description = "Etat du Schedule de demonstration : DISABLED par defaut, ENABLED seulement pendant la demo."
  type        = string
  default     = "DISABLED"

  validation {
    condition     = contains(["ENABLED", "DISABLED"], var.evolution_demo_schedule_state)
    error_message = "evolution_demo_schedule_state doit valoir ENABLED ou DISABLED."
  }
}

variable "evolution_demo_client_id" {
  description = "Client fictif (persona de test) dont le Schedule de demonstration fait avancer le portefeuille. Obligatoire si evolution_demo_schedule = true."
  type        = string
  default     = ""
}

variable "evolution_demo_month" {
  description = "Mois simule (AAAA-MM) envoye par le Schedule de demonstration a chaque declenchement."
  type        = string
  default     = "2026-10"

  validation {
    condition     = can(regex("^\\d{4}-\\d{2}$", var.evolution_demo_month))
    error_message = "evolution_demo_month doit etre au format AAAA-MM."
  }
}
