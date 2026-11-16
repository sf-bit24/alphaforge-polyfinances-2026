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

# Courriel de contact declare a la SEC (User-Agent d'EDGAR), sur les runtimes
# press, data et researcher seulement. Courriel du volet recherche.
sec_contact_email = "sacha.burelle.1@ens.etsmtl.ca"

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

# Interface deployee (web.tf) : ECS Fargate derriere un ALB et CloudFront, image
# ECR poussee par le job build_web (role de infrastructure/bootstrap/github.tf).
# VPC par defaut ; trois sous-reseaux publics par defaut de zone (us-east-1a, b,
# c), hors us-east-1e (use1-az3), ou Fargate n'est pas propose.
web_enabled    = true
web_vpc_id     = "vpc-069adf85dbd931d7f"
web_subnet_ids = ["subnet-0281babfcae54063f", "subnet-0315eb8575f90e70d", "subnet-05548ee397dc9ba6b"]

# Connexion des investisseurs (auth.tf) : User Pool Cognito, connexion geree,
# un compte = un client_id. La tache ECS passe en AUTH_MODE=cognito ; le lien
# direct de l'ALB (HTTP) ne garde alors pas de session.
auth_enabled = true

additional_tags = {
  Owner = "larpathon"
  Event = "datathon-polyfinances-2026"
}
