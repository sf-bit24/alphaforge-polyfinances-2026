terraform {
  # Organisation et workspace HCP Terraform de l'equipe. Le pipeline televerse
  # la configuration par l'API (workspace sans VCS, repertoire de travail
  # "infra", auto-apply) : voir scripts/upload-config.sh.
  cloud {
    organization = "larpathon_2026"

    workspaces {
      name = "larpathon"
    }
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.73"
    }
  }

  # Version du workspace HCP Terraform (1.17.2).
  required_version = "~> 1.17.2"
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }

  # Identifiants : Dynamic Provider Credentials d'HCP Terraform. Le workspace
  # porte TFC_AWS_PROVIDER_AUTH=true et TFC_AWS_RUN_ROLE_ARN (poses par
  # scripts/init.sh et scripts/upload-config.sh) ; HCP Terraform injecte
  # AWS_ROLE_ARN et AWS_WEB_IDENTITY_TOKEN_FILE dans le run, que le SDK AWS
  # lit seul. Le role et sa confiance OIDC sont crees par
  # infrastructure/bootstrap/.
}
