# =============================================================================
# Outputs specifiques aux Knowledge Bases des clients.
# =============================================================================
output "client_kb_vector_bucket" {
  description = "Bucket S3 Vectors des index client-<client_id> (lu par scripts/clean-client-kbs.sh)"
  value       = aws_s3vectors_vector_bucket.clients.vector_bucket_name
}

output "client_kb_role_arn" {
  description = "Role de service des Knowledge Bases des clients"
  value       = aws_iam_role.client_knowledge_base.arn
}
