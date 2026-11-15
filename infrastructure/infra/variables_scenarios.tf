# =============================================================================
# Variables specifiques aux scenarios probabilistes (SageMaker Processing,
# Step Functions, Glue, Athena). Voir scenarios.tf.
# =============================================================================
variable "scenarios_enabled" {
  description = "Deploie la chaine des scenarios (role SageMaker, machine Step Functions, table Glue, groupe Athena). false retire tout sauf les donnees deja ecrites dans le bucket. Desactive par defaut tant que l'equipe n'a pas valide : une fusion dans master declenche un apply automatique (infra.yml)."
  type        = bool
  default     = false
}

# Image scikit-learn publiee par AWS pour SageMaker (registre 683313688378,
# us-east-1), jamais une image du projet. Version complete, avec numero de
# build : les etiquettes courtes (1.4-2-py312, 1.4-2-py312-cpu-py3) bougent.
# 1.4-2-py312-1.0.3403.0 : scikit-learn 1.4.2, Python 3.12, linux/amd64,
# poussee le 2026-10-26, digest
# sha256:1888693b4727314ff4494f223e562dbac9719f6a94b4880e790387e1b229d250
# (aws ecr describe-images --registry-id 683313688378 --repository-name
# sagemaker-scikit-learn, lu le 2026-11-14). app/agents/scripts/package.sh
# installe les dependances du job pour cette version de Python.
variable "scenarios_image_uri" {
  description = "Image de traitement SageMaker scikit-learn d'AWS (etiquette complete avec numero de build, ou digest)."
  type        = string
  default     = "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.4-2-py312-1.0.3403.0"

  validation {
    condition     = can(regex("^683313688378\\.dkr\\.ecr\\.us-east-1\\.amazonaws\\.com/sagemaker-scikit-learn(:[0-9a-z.-]+-1\\.0\\.[0-9]+\\.0|@sha256:[0-9a-f]{64})$", var.scenarios_image_uri))
    error_message = "scenarios_image_uri doit etre l'image sagemaker-scikit-learn d'AWS en us-east-1, avec une etiquette de build complete (...-1.0.<n>.0) ou un digest, jamais une etiquette mobile."
  }
}

# Quotas lus le 2026-11-14 sur le compte Workshop (service-quotas, lecture
# seule) : ml.m5.4xlarge 2, ml.m5.2xlarge 4, ml.m5.xlarge 8, ml.c5.4xlarge 1,
# 10 instances au plus pour tous les jobs de traitement.
variable "scenarios_instance_type" {
  description = "Type d'instance du job de traitement."
  type        = string
  default     = "ml.m5.4xlarge"
}

variable "scenarios_instance_count" {
  description = "Nombre d'instances. Au-dela de 1, chaque instance recoit toutes les entrees (FullyReplicated) et le code doit se partager la grille (/opt/ml/config/resourceconfig.json)."
  type        = number
  default     = 1

  validation {
    condition     = var.scenarios_instance_count >= 1 && var.scenarios_instance_count <= 2
    error_message = "scenarios_instance_count doit valoir 1 ou 2 (quota ml.m5.4xlarge du compte Workshop)."
  }
}

variable "scenarios_volume_size_gb" {
  description = "Volume de stockage ML de chaque instance, en Go."
  type        = number
  default     = 30
}

variable "scenarios_max_runtime_seconds" {
  description = "Duree maximale du job de traitement (StoppingCondition), en secondes. 8 h : la config full est estimee a environ 3-4 h sur ml.m5.4xlarge avec --workers 8 (extrapolation du volet modeles, pas une mesure)."
  type        = number
  default     = 28800
}

variable "scenarios_athena_bytes_scanned_cutoff" {
  description = "Plafond d'octets lus par requete Athena dans le groupe de travail des scenarios (garde-fou de cout)."
  type        = number
  default     = 1073741824
}
