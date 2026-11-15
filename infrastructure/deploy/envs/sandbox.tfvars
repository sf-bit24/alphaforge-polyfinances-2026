# =============================================================================
# Sandbox : compte AWS Workshop Studio du Datathon (us-east-1, supprime le
# 2026-11-16 en fin de journee). Seul environnement du projet.
# Selectionne par le pipeline via DEPLOY_ENV=sandbox ; copie en
# terraform.auto.tfvars par scripts/upload-config.sh avant l'upload.
# =============================================================================

environment = "sandbox"
aws_region  = "us-east-1"

# Role assume par les runs HCP Terraform (infrastructure/bootstrap/).
# scripts/init.sh et scripts/upload-config.sh le posent sur le workspace comme
# TFC_AWS_RUN_ROLE_ARN ; aucune ressource ne le lit.
tfc_aws_run_role_arn = "arn:aws:iam::024848478575:role/alphaforge-tfc-run"

# Administrateurs des cles KMS, en plus du role Terraform : le role du
# Workshop, pour lire les bases OKF dans la console et les exporter.
kms_admin_principal_arns = ["arn:aws:iam::024848478575:role/WSParticipantRole"]

# Runtime portfolio (volet finance : etape 0, A3, lentilles, Judge). Active le
# 2026-11-15 a la demande de l'utilisateur. package.sh construit alors
# agents-portfolio.zip sans variable de CI (il lit cette ligne). Donnees longues
# deposees sous runtime/market/long/<portfolio_market_data_sha>/.
portfolio_enabled = true

# Veille : collecte toutes les 6 heures.
collecte_schedule_expression = "rate(6 hours)"
collecte_schedule_enabled    = true

additional_tags = {
  Owner = "larpathon"
  Event = "datathon-polyfinances-2026"
}
