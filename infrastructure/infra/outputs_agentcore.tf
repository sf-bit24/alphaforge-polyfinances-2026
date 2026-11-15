# =============================================================================
# Outputs specifiques au service AgentCore.
# =============================================================================
output "agentcore_runtime_arns" {
  description = "ARN des runtimes AgentCore, par role"
  value       = { for role, runtime in aws_bedrockagentcore_agent_runtime.this : role => runtime.agent_runtime_arn }
}

output "agentcore_runtime_names" {
  description = "Noms des runtimes : l'interface trouve <prefixe>_profile par ListAgentRuntimes"
  value       = { for role, runtime in aws_bedrockagentcore_agent_runtime.this : role => runtime.agent_runtime_name }
}

output "agentcore_code_key" {
  description = "Objet S3 du code deploye"
  value       = aws_s3_object.agents_code.key
}

output "agentcore_portfolio_code_key" {
  description = "Objet S3 du code du runtime portfolio (null si portfolio_enabled = false ou si le zip manque)"
  value       = one([for o in aws_s3_object.agents_portfolio_code : o.key])
}
