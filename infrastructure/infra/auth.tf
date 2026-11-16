# =============================================================================
# Service : connexion des investisseurs (Amazon Cognito, connexion geree).
#
#   navigateur -> /api/auth/login (Next.js, code + PKCE + state + nonce)
#              -> connexion geree de Cognito (inscription libre, courriel verifie)
#              -> /api/auth/callback (echange du code, ID token verifie avec le
#                 JWKS du User Pool) -> cookie de session chiffre (AES-256-GCM)
#
# Un compte = un client_id = une base OKF clients/<client_id>/ (la base
# generale general/ reste commune). Le serveur Next.js tire le client_id du sub
# du compte et refuse tout autre client_id dans le corps d'une requete (voir
# app/CONTRACTS.md section 7.1 et app/web/src/lib/server/auth/).
#
# Pourquoi dans Next.js et pas sur l'ALB : l'ALB n'ecoute qu'en HTTP (web.tf,
# pas de certificat sans nom de domaine) et l'action authenticate-cognito exige
# un listener HTTPS. Consequence : le lien direct web_alb_url (HTTP) ne garde
# pas de session (cookie Secure, et Cognito n'accepte un retour en HTTP que sur
# localhost).
#
# Aucun utilisateur n'est cree ici : chacun cree son compte sur la page de
# connexion. Le groupe admin (lancer une collecte) se remplit a la main, avec la
# CLI (voir infrastructure/README.md).
#
# Compte Workshop ephemere : pas de protection contre la suppression, et le
# courriel par defaut de Cognito (quota d'envoi faible, suffisant pour la demo).
# =============================================================================

locals {
  auth_count = var.auth_enabled ? 1 : 0

  # Prefixe du domaine de connexion, unique dans la region (le nom du compte
  # evite une collision avec un autre compte du Workshop).
  auth_domain_prefix = "${local.prefix}-${local.account_id}"

  # Origines de l'interface : CloudFront (si web_enabled) puis next dev.
  auth_app_urls = concat(
    [for d in aws_cloudfront_distribution.web : "https://${d.domain_name}"],
    var.auth_local_urls,
  )

  auth_issuer = one([for pool in aws_cognito_user_pool.investors : "https://cognito-idp.${var.aws_region}.amazonaws.com/${pool.id}"])
  auth_domain = one([for domain in aws_cognito_user_pool_domain.investors : "https://${domain.domain}.auth.${var.aws_region}.amazoncognito.com"])

  # Variables de la tache ECS de l'interface (web.tf). Sans connexion, AUTH_MODE
  # vaut off : le comportement d'avant (client_id du navigateur) reste intact.
  web_auth_environment = var.auth_enabled && var.web_enabled ? [
    { name = "AUTH_MODE", value = "cognito" },
    { name = "COGNITO_ISSUER", value = local.auth_issuer },
    { name = "COGNITO_CLIENT_ID", value = aws_cognito_user_pool_client.web[0].id },
    { name = "COGNITO_DOMAIN", value = local.auth_domain },
    { name = "APP_URL", value = "https://${aws_cloudfront_distribution.web[0].domain_name}" },
    { name = "AUTH_SESSION_SECRET", value = random_password.web_session[0].result },
  ] : [{ name = "AUTH_MODE", value = "off" }]
}

# -----------------------------------------------------------------------------
# User Pool : le courriel est l'identifiant, inscription libre, courriel verifie
# par un code. La connexion geree (version 2) exige le plan Essentials.
# -----------------------------------------------------------------------------
resource "aws_cognito_user_pool" "investors" {
  count          = local.auth_count
  name           = "${local.prefix}-investors"
  user_pool_tier = "ESSENTIALS"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OFF"
  deletion_protection      = "INACTIVE"

  username_configuration {
    case_sensitive = false
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Un nouveau courriel ne remplace l'ancien qu'une fois verifie.
  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }
}

# Domaine prefixe de Cognito (HTTPS fourni par AWS), pages de la connexion
# geree (version 2).
resource "aws_cognito_user_pool_domain" "investors" {
  count                 = local.auth_count
  domain                = local.auth_domain_prefix
  user_pool_id          = aws_cognito_user_pool.investors[0].id
  managed_login_version = 2
}

# -----------------------------------------------------------------------------
# Client d'application PUBLIC : pas de secret, flux code avec PKCE (verifie par
# le serveur Next.js). L'ID token dure auth_session_hours : la session de
# l'interface expire avec lui, puis l'investisseur se reconnecte.
# -----------------------------------------------------------------------------
resource "aws_cognito_user_pool_client" "web" {
  count        = local.auth_count
  name         = "${local.prefix}-web"
  user_pool_id = aws_cognito_user_pool.investors[0].id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]

  callback_urls = [for url in local.auth_app_urls : "${url}/api/auth/callback"]
  logout_urls   = [for url in local.auth_app_urls : "${url}/"]

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  id_token_validity      = var.auth_session_hours
  access_token_validity  = var.auth_session_hours
  refresh_token_validity = 1

  token_validity_units {
    id_token      = "hours"
    access_token  = "hours"
    refresh_token = "days"
  }
}

# Sans style de marque, un client cree par l'API n'affiche pas les pages de la
# connexion geree : on prend le style par defaut de Cognito.
resource "aws_cognito_managed_login_branding" "web" {
  count                       = local.auth_count
  user_pool_id                = aws_cognito_user_pool.investors[0].id
  client_id                   = aws_cognito_user_pool_client.web[0].id
  use_cognito_provided_values = true
}

# Seuls ses membres lancent une collecte (POST /api/collect, cognito:groups).
resource "aws_cognito_user_group" "admin" {
  count        = local.auth_count
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.investors[0].id
  description  = "Equipe AlphaForge : lance les collectes de la base generale."
  precedence   = 1
}

# -----------------------------------------------------------------------------
# Secret du cookie de session (chiffrement AES-256-GCM dans Next.js). Il reste
# stable d'un deploiement a l'autre : un nouvel apply ne deconnecte personne.
# -----------------------------------------------------------------------------
resource "random_password" "web_session" {
  count   = local.auth_count
  length  = 64
  special = false
}
