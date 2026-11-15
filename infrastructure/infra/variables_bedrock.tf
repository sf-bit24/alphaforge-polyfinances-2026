# =============================================================================
# Variables specifiques a Bedrock (Knowledge Base, Guardrail).
# =============================================================================
variable "bedrock_embedding_model_id" {
  description = "Modele d'embeddings de la Knowledge Base."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "bedrock_embedding_dimensions" {
  description = "Dimension des vecteurs (Titan Text Embeddings V2 : 256, 512 ou 1024)."
  type        = number
  default     = 1024
}
