# =============================================================================
# Locals SOCLE (service-agnostiques).
# =============================================================================
data "aws_partition" "current" {}

locals {
  prefix       = "${var.project_name}-${var.environment}"
  is_ephemeral = can(regex("^feat-", var.environment))

  # AgentCore refuse tirets et points dans les noms de runtimes :
  # alphaforge-sandbox -> alphaforge_sandbox.
  name_snake = replace(local.prefix, "-", "_")

  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Stack       = var.project_name
    },
    var.additional_tags,
  )
}
