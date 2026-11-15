# =============================================================================
# Variables specifiques au service S3.
# =============================================================================
variable "s3_bucket_name" {
  description = "Nom logique du bucket, entre le prefixe projet-env et l'ID du compte."
  type        = string
  default     = "kb"
}

variable "s3_versioning" {
  description = "Active le versioning du bucket (une base OKF garde l'historique de ses documents)."
  type        = bool
  default     = true
}

variable "s3_staging_expiration_days" {
  description = "Duree de vie des elements bruts de collecte sous staging/."
  type        = number
  default     = 14
}
