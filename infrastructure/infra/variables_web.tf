# =============================================================================
# Variables specifiques a l'interface deployee (ECS Fargate, ALB, CloudFront).
# Voir web.tf.
# =============================================================================
variable "web_enabled" {
  description = "Deploie l'interface Next.js (app/web) sur ECS Fargate derriere un ALB et CloudFront. L'image <web_ecr_repository>:<release_id> doit exister : le job build_web de app.yml la pousse avant l'apply."
  type        = bool
  default     = false
}

variable "web_ecr_repository" {
  description = "Depot ECR de l'image de l'interface, cree par infrastructure/bootstrap/github.tf."
  type        = string
  default     = "alphaforge-web"
}

variable "web_vpc_id" {
  description = "VPC de l'ALB et des taches (VPC par defaut du compte Workshop)."
  type        = string
  default     = ""
}

variable "web_subnet_ids" {
  description = "Sous-reseaux PUBLICS (route 0.0.0.0/0 vers une Internet Gateway) de l'ALB et des taches, au moins deux zones. Les taches y prennent une IP publique pour joindre ECR et les API AWS sans NAT Gateway ; leur groupe de securite n'accepte que l'ALB."
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.web_subnet_ids) == 0 || length(var.web_subnet_ids) >= 2
    error_message = "Un ALB exige au moins deux sous-reseaux, dans deux zones differentes."
  }
}

variable "web_allowed_cidrs" {
  description = "CIDR autorises a joindre l'ALB en HTTP (acces direct, sans la limite de 60 s de CloudFront). CloudFront passe toujours, par la liste de prefixes geree par AWS."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "web_cpu" {
  description = "CPU de la tache Fargate (unites ECS : 1024 = 1 vCPU)."
  type        = number
  default     = 512
}

variable "web_memory" {
  description = "Memoire de la tache Fargate (Mio)."
  type        = number
  default     = 1024
}

variable "web_desired_count" {
  description = "Nombre de taches. Une seule suffit pour la demo : le serveur ne garde qu'un cache (ARN des runtimes)."
  type        = number
  default     = 1
}

variable "web_idle_timeout_seconds" {
  description = "Delai d'inactivite de l'ALB. Doit depasser le build du portefeuille (PORTFOLIO_TIMEOUT_MS = 600 s dans app/web/src/lib/server/gateway.ts) et les flux SSE de /api/agent."
  type        = number
  default     = 900
}
