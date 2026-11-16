# =============================================================================
# Variables specifiques aux Knowledge Bases des clients (client_kb.tf).
# =============================================================================
variable "client_kb_enabled" {
  description = "Pose les variables ALPHAFORGE_CLIENT_KB_* sur les runtimes profile et portfolio : chaque client recoit sa Knowledge Base. Faux : le bucket, la cle et le role restent, les runtimes ne creent ni n'ingerent rien (comportement d'avant)."
  type        = bool
  default     = true
}
