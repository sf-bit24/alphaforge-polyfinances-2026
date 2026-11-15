# =============================================================================
# Variables specifiques a tldoole (valeurs par defaut : aucune n'est dans
# deploy/envs/sandbox.tfvars).
# =============================================================================
variable "tldoole_trigger_enabled" {
  description = "Lance la machine tldoole a chaque ecriture du journal d'un profil (regle EventBridge). Desactive par defaut : seules les actions request et feedback lancent la machine."
  type        = bool
  default     = false
}

variable "tldoole_debounce_seconds" {
  description = "Attente avant la detection : seule la derniere version du journal est jugee."
  type        = number
  default     = 45
}

variable "tldoole_poll_seconds" {
  description = "Intervalle entre deux sondages d'un marqueur detect.json ou _produced.json."
  type        = number
  default     = 10
}

variable "tldoole_detect_timeout_seconds" {
  description = "Delai maximal d'A7 avant d'abandonner son marqueur."
  type        = number
  default     = 300
}

variable "tldoole_produce_timeout_seconds" {
  description = "Delai maximal d'A8 (scenario, ecrans, narration) avant d'abandonner son marqueur."
  type        = number
  default     = 600
}

variable "tldoole_montage_timeout_seconds" {
  description = "Delai maximal d'un job MediaConvert."
  type        = number
  default     = 900
}

variable "tldoole_execution_timeout_seconds" {
  description = "Delai maximal d'une execution complete de la machine tldoole."
  type        = number
  default     = 3600
}

variable "tldoole_max_concurrency" {
  description = "Videos produites en parallele par execution."
  type        = number
  default     = 2
}

variable "tldoole_max_videos_per_run" {
  description = "Videos creees au plus par une detection."
  type        = number
  default     = 2
}

variable "tldoole_max_videos_per_day" {
  description = "Videos creees au plus par investisseur et par jour (UTC)."
  type        = number
  default     = 6
}
