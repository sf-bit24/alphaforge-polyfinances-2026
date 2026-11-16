# =============================================================================
# Variables specifiques a la connexion des investisseurs (Cognito). Voir auth.tf.
# =============================================================================
variable "auth_enabled" {
  description = "Cree le User Pool Cognito, son domaine de connexion geree et le client de l'interface, et passe la tache ECS en AUTH_MODE=cognito. Faux : l'interface garde AUTH_MODE=off (client_id du navigateur)."
  type        = bool
  default     = false
}

variable "auth_local_urls" {
  description = "Origines de next dev autorisees en plus de CloudFront (retour /api/auth/callback, deconnexion /). Cognito n'accepte le HTTP que sur localhost."
  type        = list(string)
  default     = ["http://localhost:3000"]

  validation {
    condition     = alltrue([for url in var.auth_local_urls : can(regex("^(https://[a-z0-9.-]+|http://localhost)(:[0-9]+)?$", url))])
    error_message = "Chaque origine est https://<hote> ou http://localhost[:port], sans chemin ni barre finale."
  }
}

variable "auth_session_hours" {
  description = "Duree de l'ID token et de la session de l'interface (heures, 1 a 24). A l'expiration, l'investisseur se reconnecte."
  type        = number
  default     = 8

  validation {
    condition     = var.auth_session_hours >= 1 && var.auth_session_hours <= 24 && floor(var.auth_session_hours) == var.auth_session_hours
    error_message = "auth_session_hours est un nombre entier d'heures entre 1 et 24."
  }
}
