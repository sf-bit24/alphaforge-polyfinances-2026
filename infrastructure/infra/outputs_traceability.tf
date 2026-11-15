# =============================================================================
# Outputs de la tracabilite (lus par le volet finance via variables d'env).
# =============================================================================
output "trace_bucket" {
  description = "Bucket de traces (Object Lock) : journal Bedrock et blobs du rejeu LLM (ALPHAFORGE_TRACE_BUCKET)"
  value       = aws_s3_bucket.traces.id
}

output "llm_replay_table" {
  description = "Table DynamoDB du rejeu LLM (ALPHAFORGE_REPLAY_TABLE)"
  value       = aws_dynamodb_table.trace["llm-replay"].name
}

output "decisions_table" {
  description = "Table DynamoDB du journal des decisions chaine (ALPHAFORGE_DECISIONS_TABLE)"
  value       = aws_dynamodb_table.trace["decisions"].name
}

output "bedrock_invocation_log_group" {
  description = "Groupe CloudWatch du journal des invocations Bedrock"
  value       = aws_cloudwatch_log_group.bedrock_invocations.name
}

output "finance_log_group" {
  description = "Groupe CloudWatch des evenements applicatifs du volet finance (ALPHAFORGE_LOG_GROUP)"
  value       = aws_cloudwatch_log_group.finance_app.name
}
