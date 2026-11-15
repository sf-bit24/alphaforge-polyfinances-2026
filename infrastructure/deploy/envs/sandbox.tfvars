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

# Scenarios probabilistes (scenarios.tf, app/CONTRACTS.md section 10). Seule
# source de verite : package.sh lit cette ligne pour construire, ou non, le
# bundle du job (infra/build/scenarios/) quand ALPHAFORGE_PACKAGE_SCENARIOS
# n'est pas posee (cas de la CI). Aucun declencheur : l'equipe lance chaque run.
scenarios_enabled = true

# Veille : collecte toutes les 6 heures.
collecte_schedule_expression = "rate(6 hours)"
collecte_schedule_enabled    = true

# Runtime portfolio (A3, lentilles, Judge du volet finance) : zip
# agents-portfolio.zip construit par defaut par package.sh, donnees longues lues
# sous runtime/data/long/ (scripts/finance/upload_long_data.py).
portfolio_enabled = true

# Evolution du portefeuille dans le temps (evolution.tf) : machine Step Functions
# qui appelle les actions evolution.* du runtime portfolio. Lancee a la demande ;
# l'horaire de demo (1 execution = 1 mois simule) reste desactive.
evolution_enabled = true

additional_tags = {
  Owner = "larpathon"
  Event = "datathon-polyfinances-2026"
}
