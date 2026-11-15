# =============================================================================
# Outputs specifiques au service S3.
# =============================================================================
output "s3_bucket_name" {
  description = "Bucket des bases OKF"
  value       = aws_s3_bucket.this.bucket
}

output "s3_bucket_arn" {
  description = "ARN du bucket des bases OKF"
  value       = aws_s3_bucket.this.arn
}

output "s3_kms_key_arn" {
  description = "Cle KMS du bucket"
  value       = aws_kms_key.s3.arn
}
