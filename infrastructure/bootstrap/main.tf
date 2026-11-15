# =============================================================================
# Bootstrap du compte AWS : a appliquer UNE fois, depuis un poste, etat local.
#
# Cree ce que le pipeline ne peut pas creer lui-meme, faute d'acces AWS avant
# son premier run : la confiance OIDC entre HCP Terraform et AWS, et le role
# qu'assument les runs du workspace (Dynamic Provider Credentials).
#
#   terraform -chdir=infrastructure/bootstrap init
#   terraform -chdir=infrastructure/bootstrap apply
#
# Puis reporter l'output tfc_run_role_arn dans
# infrastructure/deploy/envs/sandbox.tfvars (cle tfc_aws_run_role_arn).
#
# L'etat (terraform.tfstate) reste sur le poste : il ne decrit que ces deux
# ressources, et le compte Workshop est supprime le 2026-11-16.
# =============================================================================

terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.73"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform-bootstrap"
      Event     = "datathon-polyfinances-2026"
    }
  }
}

variable "aws_region" {
  description = "Region AWS du compte Workshop (seule region permise par sa SCP)."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefixe des ressources du projet. Le role des runs ne gere que les roles IAM qui portent ce prefixe."
  type        = string
  default     = "alphaforge"
}

variable "tfc_hostname" {
  description = "Hote HCP Terraform."
  type        = string
  default     = "app.terraform.io"
}

variable "tfc_organization" {
  description = "Organisation HCP Terraform."
  type        = string
  default     = "larpathon_2026"
}

variable "tfc_workspace" {
  description = "Seul workspace autorise a assumer le role."
  type        = string
  default     = "larpathon"
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
}

# Fournisseur OIDC d'HCP Terraform. AWS valide le certificat de l'emetteur
# par ses propres autorites racines : pas d'empreinte a fournir.
resource "aws_iam_openid_connect_provider" "tfc" {
  url            = "https://${var.tfc_hostname}"
  client_id_list = ["aws.workload.identity"]
}

# Seuls les runs (plan et apply) du workspace nomme peuvent assumer le role.
data "aws_iam_policy_document" "tfc_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.tfc.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.tfc_hostname}:aud"
      values   = ["aws.workload.identity"]
    }

    condition {
      test     = "StringLike"
      variable = "${var.tfc_hostname}:sub"
      values   = ["organization:${var.tfc_organization}:project:*:workspace:${var.tfc_workspace}:run_phase:*"]
    }
  }
}

resource "aws_iam_role" "tfc_run" {
  name                 = "${var.project_name}-tfc-run"
  description          = "Assume par les runs HCP Terraform du workspace ${var.tfc_workspace} (${var.tfc_organization})."
  assume_role_policy   = data.aws_iam_policy_document.tfc_trust.json
  max_session_duration = 3600
}

# Tous les services sauf IAM, Organizations et Account. Le compte Workshop
# limite deja toute action regionale a us-east-1 par SCP.
resource "aws_iam_role_policy_attachment" "power_user" {
  role       = aws_iam_role.tfc_run.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/PowerUserAccess"
}

# IAM limite aux roles du projet : la pile cree les roles d'execution des
# runtimes AgentCore, de la Knowledge Base, de Step Functions et du Scheduler,
# tous prefixes par le nom du projet.
data "aws_iam_policy_document" "tfc_iam" {
  statement {
    sid = "ManageProjectRoles"
    actions = [
      "iam:AttachRolePolicy",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:DeleteRolePolicy",
      "iam:DetachRolePolicy",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListRolePolicies",
      "iam:ListRoleTags",
      "iam:PassRole",
      "iam:PutRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:UpdateRole",
      "iam:UpdateRoleDescription",
    ]
    resources = ["arn:${local.partition}:iam::${local.account_id}:role/${var.project_name}-*"]
  }

  statement {
    sid       = "ReadPolicies"
    actions   = ["iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListPolicyVersions"]
    resources = ["*"]
  }

  statement {
    sid       = "ServiceLinkedRoles"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["arn:${local.partition}:iam::${local.account_id}:role/aws-service-role/*"]
  }
}

resource "aws_iam_role_policy" "tfc_iam" {
  name   = "project-roles"
  role   = aws_iam_role.tfc_run.id
  policy = data.aws_iam_policy_document.tfc_iam.json
}

output "tfc_run_role_arn" {
  description = "A reporter dans deploy/envs/sandbox.tfvars (tfc_aws_run_role_arn)."
  value       = aws_iam_role.tfc_run.arn
}

output "tfc_oidc_provider_arn" {
  description = "Fournisseur OIDC d'HCP Terraform."
  value       = aws_iam_openid_connect_provider.tfc.arn
}
