# =============================================================================
# Bootstrap de l'image de l'interface (app/web) : meme etat local que main.tf.
#
# Le job build_web de .github/workflows/app.yml pousse l'image dans ECR AVANT
# que HCP Terraform applique la pile : le depot ECR et le droit de pousser
# doivent donc exister avant le premier run. Le role des runs HCP Terraform ne
# peut pas creer de fournisseur OIDC (IAM limite aux roles alphaforge-*).
#
#   - fournisseur OIDC de GitHub Actions (token.actions.githubusercontent.com)
#   - depot ECR alphaforge-web
#   - role alphaforge-github-ecr-push : pousser dans ce depot seulement,
#     assumable seulement par les runs de la branche par defaut du repo
#   - roles lies aux services ECS et Elastic Load Balancing : le premier
#     cluster cree sans eux echoue parfois ("Unable to assume the service
#     linked role")
#
# GitHub Actions n'a toujours aucune cle AWS : il echange son jeton OIDC contre
# une session courte de ce role, limitee a ECR.
# =============================================================================

variable "github_repository" {
  description = "Repo GitHub (owner/repo) dont les runs poussent l'image."
  type        = string
  default     = "sf-bit24/alphaforge-polyfinances-2026"
}

# Formes du sub qu'envoie GitHub pour ce repo. Le repo a le reglage
# « immutable subject » (API actions/oidc/customization/sub :
# use_immutable_subject = true) : le sub porte les identifiants numeriques du
# proprietaire et du repo, qu'un repo recree sous le meme nom n'aurait pas.
# L'ancienne forme reste acceptee au cas ou le reglage serait retire.
variable "github_subject_prefixes" {
  description = "Prefixes du sub OIDC de GitHub pour ce repo (sans :ref:...)."
  type        = list(string)
  default = [
    "repo:sf-bit24@231555058/alphaforge-polyfinances-2026@1458006494",
    "repo:sf-bit24/alphaforge-polyfinances-2026",
  ]
}

variable "github_branch" {
  description = "Seule branche dont les runs peuvent pousser (branche par defaut du repo)."
  type        = string
  default     = "master"
}

# AWS valide le certificat de l'emetteur par ses propres autorites racines :
# pas d'empreinte a fournir, comme pour HCP Terraform (main.tf).
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_ecr_repository" "web" {
  name                 = "${var.project_name}-web"
  image_tag_mutability = "MUTABLE"
  # Le compte est supprime le 2026-11-16 : rien a garder au destroy.
  force_delete = true

  encryption_configuration {
    encryption_type = "KMS"
  }

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Les tags sont des SHA de commit : garder les 30 derniers suffit au rollback.
resource "aws_ecr_lifecycle_policy" "web" {
  repository = aws_ecr_repository.web.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Garder les 30 dernieres images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 30
      }
      action = { type = "expire" }
    }]
  })
}

# Les workflows appeles (app.yml) heritent du sub de l'appelant (pipeline.yml) :
# <prefixe>:ref:refs/heads/<branche>.
data "aws_iam_policy_document" "github_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for prefix in var.github_subject_prefixes : "${prefix}:ref:refs/heads/${var.github_branch}"]
    }
  }
}

resource "aws_iam_role" "github_push" {
  name                 = "${var.project_name}-github-ecr-push"
  description          = "Assume par GitHub Actions (${var.github_repository}, ${var.github_branch}) pour pousser l'image de l'interface."
  assume_role_policy   = data.aws_iam_policy_document.github_trust.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "github_push" {
  statement {
    sid       = "Login"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "PushWebImage"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.web.arn]
  }
}

resource "aws_iam_role_policy" "github_push" {
  name   = "push-web-image"
  role   = aws_iam_role.github_push.id
  policy = data.aws_iam_policy_document.github_push.json
}

resource "aws_iam_service_linked_role" "ecs" {
  aws_service_name = "ecs.amazonaws.com"
}

resource "aws_iam_service_linked_role" "elb" {
  aws_service_name = "elasticloadbalancing.amazonaws.com"
}

output "web_ecr_repository_url" {
  description = "Depot de l'image de l'interface : ECR_REGISTRY_IMAGE de .github/workflows/pipeline.yml."
  value       = aws_ecr_repository.web.repository_url
}

output "github_ecr_push_role_arn" {
  description = "Role assume par le job build_web : AWS_ECR_PUSH_ROLE_ARN de .github/workflows/pipeline.yml."
  value       = aws_iam_role.github_push.arn
}
