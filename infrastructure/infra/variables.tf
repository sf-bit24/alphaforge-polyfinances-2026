# =============================================================================
# Variables SOCLE (service-agnostiques). Les variables propres a un service
# vivent dans variables_<service>.tf.
# =============================================================================

# tfc_aws_run_role_arn est declare UNIQUEMENT pour pouvoir vivre dans
# deploy/envs/<env>.tfvars sans warning "value for undeclared variable".
# Aucune ressource ne le lit : scripts/init.sh et scripts/upload-config.sh
# l'extraient du tfvars et le posent sur le workspace comme variable
# d'environnement TFC_AWS_RUN_ROLE_ARN avant le run.
variable "tfc_aws_run_role_arn" {
  description = "ARN du role IAM assume par les runs HCP Terraform (cree par infrastructure/bootstrap/). Pose sur le workspace comme TFC_AWS_RUN_ROLE_ARN ; non lu par les ressources."
  type        = string
  default     = ""
}

variable "environment" {
  description = "Environnement de deploiement, fourni par deploy/envs/<env>.tfvars. Valeurs canoniques : sandbox|nprod|prod ; ephemeres : feat-<slug> (desactives pour ce projet)."
  type        = string

  validation {
    condition = (
      contains(["sandbox", "nprod", "prod"], var.environment) ||
      can(regex("^feat-[a-z0-9-]{1,14}$", var.environment))
    )
    error_message = "L'environnement doit etre sandbox, nprod, prod, ou un slug feat-<...> de 1-14 char alphanumeriques/tirets."
  }
}

variable "project_name" {
  description = "Nom du projet, prefixe de toutes les ressources."
  type        = string
  default     = "alphaforge"
}

variable "aws_region" {
  description = "Region AWS cible. Le compte Workshop du Datathon n'autorise que us-east-1."
  type        = string
  default     = "us-east-1"
}

# Seul artefact du run : le zip du code des runtimes AgentCore, construit par
# le job package_agents de .github/workflows/app.yml et televerse avec la
# configuration (infra/build/agents.zip). Son nom porte le SHA du commit, donc
# chaque commit deploie un objet immuable et met les runtimes a jour.
variable "release_id" {
  description = "SHA court du commit deploye (8 caracteres). Ecrit par scripts/write-release-tfvars.sh (artefact release-tfvars)."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{7,40}$", var.release_id))
    error_message = "release_id doit etre un SHA de commit hexadecimal (7 a 40 caracteres), pas un tag mobile."
  }
}

variable "kms_admin_principal_arns" {
  description = "Roles IAM administrateurs des cles KMS du projet, en plus du role qui execute Terraform (ex. le role du Workshop, pour lire les objets dans la console). ARN exacts : une key policy refuse les jokers dans Principal."
  type        = list(string)
  default     = []
}

variable "additional_tags" {
  description = "Tags additionnels (fusionnes avec local.common_tags)."
  type        = map(string)
  default     = {}
}
