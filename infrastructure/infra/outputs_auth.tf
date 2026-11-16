# =============================================================================
# Outputs specifiques a la connexion (null si auth_enabled = false). Ils
# remplissent aussi app/web/.env.local pour tester la connexion avec next dev.
# =============================================================================
output "auth_user_pool_id" {
  description = "User Pool des investisseurs (ajout au groupe admin : voir infrastructure/README.md)"
  value       = one(aws_cognito_user_pool.investors[*].id)
}

output "auth_issuer" {
  description = "Emetteur OIDC des ID tokens (COGNITO_ISSUER)"
  value       = local.auth_issuer
}

output "auth_client_id" {
  description = "Client d'application public de l'interface (COGNITO_CLIENT_ID)"
  value       = one(aws_cognito_user_pool_client.web[*].id)
}

output "auth_domain" {
  description = "Domaine de la connexion geree (COGNITO_DOMAIN)"
  value       = local.auth_domain
}
