# =============================================================================
# Outputs specifiques a Bedrock.
# =============================================================================
output "knowledge_base_id" {
  description = "Knowledge Base de la base generale"
  value       = aws_bedrockagent_knowledge_base.general.id
}

output "knowledge_base_data_source_id" {
  description = "Source de donnees S3 (general/) de la Knowledge Base"
  value       = aws_bedrockagent_data_source.general.data_source_id
}

output "guardrail_id" {
  description = "Guardrail du cadre responsable"
  value       = aws_bedrock_guardrail.cadre.guardrail_id
}

output "guardrail_version" {
  description = "Version du guardrail lue par le runtime profile"
  value       = aws_bedrock_guardrail_version.cadre.version
}
