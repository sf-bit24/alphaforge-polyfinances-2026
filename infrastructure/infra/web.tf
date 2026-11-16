# =============================================================================
# Service : interface Next.js (app/web) sur ECS Fargate.
#
#   navigateur -> CloudFront (HTTPS, *.cloudfront.net) -> ALB (HTTP :80)
#              -> tache Fargate (next start, :3000, AGENT_MODE=aws)
#              -> AgentCore (runtimes profile, portfolio) et Step Functions
#                 (collecte), avec le role de la tache
#
# Pourquoi ces services (lus dans app/web) :
#   - /api/portfolio attend jusqu'a 600 s une reponse JSON, /api/agent repond
#     en SSE, et un envoi de fichiers peut peser ~70 Mo : Lambda (6 Mo) et App
#     Runner (120 s) ne conviennent pas ; l'ALB garde la connexion
#     web_idle_timeout_seconds.
#   - Le navigateur appelle crypto.randomUUID() et navigator.clipboard, reserves
#     aux contextes securises : CloudFront donne le HTTPS sans nom de domaine.
#     CloudFront coupe une reponse muette apres 60 s (maximum sans hausse de
#     quota) : un build du portefeuille plus long passe par l'URL directe de
#     l'ALB (output web_alb_url), mais seulement sans connexion
#     (auth_enabled = false) : en HTTP, le cookie de session Secure ne passe
#     pas (auth.tf).
#
# L'image vient d'ECR (<web_ecr_repository>:<release_id>), poussee par le job
# build_web de .github/workflows/app.yml avec le role de
# infrastructure/bootstrap/github.tf. release_id change a chaque commit : chaque
# apply cree une revision de la definition de tache et ECS remplace la tache.
#
# Reseau : VPC par defaut, sous-reseaux publics. Les taches y prennent une IP
# publique pour joindre ECR et les API AWS sans NAT Gateway ; leur groupe de
# securite n'accepte que l'ALB et ne sort qu'en HTTPS.
# =============================================================================

locals {
  web_count = var.web_enabled ? 1 : 0
  web_name  = "${local.prefix}-web"
  web_port  = 3000

  # Runtimes appeles par le serveur Next.js, trouves par nom (ListAgentRuntimes) :
  # l'ARN porte un suffixe aleatoire (runtime/<nom>-<id>), d'ou le joker. Le /*
  # couvre le point de terminaison DEFAULT (qualifier de InvokeAgentRuntime).
  web_runtime_arns = [
    for role in ["profile", "portfolio"] :
    "arn:${local.partition}:bedrock-agentcore:${var.aws_region}:${local.account_id}:runtime/${local.name_snake}_${role}-*"
  ]
}

data "aws_ecr_repository" "web" {
  count = local.web_count
  name  = var.web_ecr_repository
}

# -----------------------------------------------------------------------------
# Journaux
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "web" {
  count             = local.web_count
  name              = "/ecs/${local.web_name}"
  retention_in_days = 14
}

# -----------------------------------------------------------------------------
# IAM : role d'execution (tirer l'image, ecrire les journaux) et role de la
# tache (ce que le serveur Next.js appelle).
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "web_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "web_execution" {
  count              = local.web_count
  name               = "${local.web_name}-execution"
  description        = "Execution de la tache ECS de l'interface : tirer l'image ECR, ecrire les journaux."
  assume_role_policy = data.aws_iam_policy_document.web_assume.json
}

resource "aws_iam_role_policy_attachment" "web_execution" {
  count      = local.web_count
  role       = aws_iam_role.web_execution[0].name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "web_task" {
  count              = local.web_count
  name               = "${local.web_name}-task"
  description        = "Serveur Next.js de l'interface : AgentCore (profile, portfolio) et machine de collecte."
  assume_role_policy = data.aws_iam_policy_document.web_assume.json
}

# Exactement les appels de app/web/src/lib/server/aws.ts.
data "aws_iam_policy_document" "web_task" {
  statement {
    sid       = "InvokeRuntimes"
    actions   = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = local.web_runtime_arns
  }

  # ListAgentRuntimes et ListStateMachines n'acceptent pas de ressource.
  statement {
    sid       = "FindByName"
    actions   = ["bedrock-agentcore:ListAgentRuntimes", "states:ListStateMachines"]
    resources = ["*"]
  }

  statement {
    sid       = "RunCollecte"
    actions   = ["states:StartExecution", "states:ListExecutions"]
    resources = [aws_sfn_state_machine.collecte.arn]
  }

  statement {
    sid       = "ReadCollecteRuns"
    actions   = ["states:DescribeExecution"]
    resources = ["arn:${local.partition}:states:${var.aws_region}:${local.account_id}:execution:${local.collecte_name}:*"]
  }
}

resource "aws_iam_role_policy" "web_task" {
  count  = local.web_count
  name   = "agentcore-and-collecte"
  role   = aws_iam_role.web_task[0].id
  policy = data.aws_iam_policy_document.web_task.json
}

# -----------------------------------------------------------------------------
# « Supprimer mon compte » (app/CONTRACTS.md section 7.1), avec la connexion
# seulement : le serveur Next.js, en code deterministe
# (app/web/src/lib/server/auth/account-deletion.ts), supprime la base du compte
# de la session, puis son utilisateur Cognito. Jamais un runtime ni un modele :
# les runtimes n'ont toujours aucun droit de suppression. Le code verifie que
# chaque cle commence par clients/<client_id>/ ; IAM borne le reste.
# -----------------------------------------------------------------------------
locals {
  web_deletion_count = var.web_enabled && var.auth_enabled ? 1 : 0
}

data "aws_iam_policy_document" "web_account_deletion" {
  count = local.web_deletion_count

  # 1. Knowledge Base du client, trouvee par son nom <prefix>-client-<client_id>
  # (pas de kb.json a lire). ListKnowledgeBases n'accepte pas de ressource.
  statement {
    sid       = "FindClientKnowledgeBases"
    actions   = ["bedrock:ListKnowledgeBases"]
    resources = ["*"]
  }

  # Lecture (ARN, statut) et etiquettes, verifiees par le code avant la
  # suppression ; seulement une base etiquetee alphaforge:scope=client de ce
  # prefixe. Sa source CUSTOM, en RETAIN, part avec elle sans toucher aux
  # vecteurs : pas de DeleteDataSource.
  statement {
    sid       = "DeleteClientKnowledgeBases"
    actions   = ["bedrock:GetKnowledgeBase", "bedrock:ListTagsForResource", "bedrock:DeleteKnowledgeBase"]
    resources = [local.client_kb_arn_pattern]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/alphaforge:scope"
      values   = ["client"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/alphaforge:prefix"
      values   = [local.prefix]
    }
  }

  # La base generale ne se supprime jamais d'ici, meme etiquetee par erreur.
  statement {
    sid       = "KeepGeneralKnowledgeBase"
    effect    = "Deny"
    actions   = ["bedrock:DeleteKnowledgeBase", "bedrock:DeleteDataSource"]
    resources = [aws_bedrockagent_knowledge_base.general.arn]
  }

  # 2. Index client-<client_id> du bucket des vecteurs des clients.
  statement {
    sid       = "DeleteClientIndexes"
    actions   = ["s3vectors:DeleteIndex"]
    resources = [local.client_kb_index_arn_pattern]
  }

  # 3. Toutes les versions et tous les marqueurs de suppression sous
  # clients/<client_id>/ (bucket versionne). Ni lecture d'objet ni KMS : lister
  # et supprimer des versions ne dechiffre rien.
  statement {
    sid       = "ListClientVersions"
    actions   = ["s3:ListBucketVersions"]
    resources = [aws_s3_bucket.this.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["clients/*"]
    }
  }

  statement {
    sid       = "DeleteClientVersions"
    actions   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${aws_s3_bucket.this.arn}/clients/*"]
  }

  # Les bases de demonstration FICTION (clients/demo-<persona>/) restent.
  statement {
    sid       = "KeepDemoBases"
    effect    = "Deny"
    actions   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${aws_s3_bucket.this.arn}/clients/demo-*"]
  }

  # 4. L'utilisateur, en dernier (nom d'utilisateur = sub du compte).
  statement {
    sid       = "DeleteInvestorUser"
    actions   = ["cognito-idp:AdminDeleteUser"]
    resources = [aws_cognito_user_pool.investors[0].arn]
  }
}

resource "aws_iam_role_policy" "web_account_deletion" {
  count  = local.web_deletion_count
  name   = "account-deletion"
  role   = aws_iam_role.web_task[0].id
  policy = data.aws_iam_policy_document.web_account_deletion[0].json
}

# -----------------------------------------------------------------------------
# Reseau : ALB public, taches joignables seulement depuis l'ALB.
# -----------------------------------------------------------------------------
data "aws_ec2_managed_prefix_list" "cloudfront" {
  count = local.web_count
  name  = "com.amazonaws.global.cloudfront.origin-facing"
}

# Descriptions des groupes et des regles : EC2 n'accepte que
# a-zA-Z0-9. _-:/()#,@[]+=&;{}!$* (ni apostrophe ni accent).
resource "aws_security_group" "web_alb" {
  count       = local.web_count
  name        = "${local.web_name}-alb"
  description = "ALB interface web, HTTP depuis CloudFront et web_allowed_cidrs"
  vpc_id      = var.web_vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "web_alb_cloudfront" {
  count             = local.web_count
  security_group_id = aws_security_group.web_alb[0].id
  description       = "CloudFront (origine)"
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront[0].id
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "web_alb_direct" {
  for_each          = var.web_enabled ? toset(var.web_allowed_cidrs) : toset([])
  security_group_id = aws_security_group.web_alb[0].id
  description       = "Acces direct a ALB"
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_egress_rule" "web_alb_tasks" {
  count                        = local.web_count
  security_group_id            = aws_security_group.web_alb[0].id
  description                  = "Vers les taches"
  referenced_security_group_id = aws_security_group.web_tasks[0].id
  ip_protocol                  = "tcp"
  from_port                    = local.web_port
  to_port                      = local.web_port
}

resource "aws_security_group" "web_tasks" {
  count       = local.web_count
  name        = "${local.web_name}-tasks"
  description = "Taches interface web, entree depuis ALB, sortie HTTPS vers ECR et API AWS"
  vpc_id      = var.web_vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "web_tasks_alb" {
  count                        = local.web_count
  security_group_id            = aws_security_group.web_tasks[0].id
  description                  = "Depuis ALB"
  referenced_security_group_id = aws_security_group.web_alb[0].id
  ip_protocol                  = "tcp"
  from_port                    = local.web_port
  to_port                      = local.web_port
}

resource "aws_vpc_security_group_egress_rule" "web_tasks_https" {
  count             = local.web_count
  security_group_id = aws_security_group.web_tasks[0].id
  description       = "ECR, AgentCore, Step Functions, CloudWatch Logs"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_lb" "web" {
  count                      = local.web_count
  name                       = local.web_name
  load_balancer_type         = "application"
  internal                   = false
  subnets                    = var.web_subnet_ids
  security_groups            = [aws_security_group.web_alb[0].id]
  idle_timeout               = var.web_idle_timeout_seconds
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "web" {
  count                = local.web_count
  name                 = local.web_name
  port                 = local.web_port
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = var.web_vpc_id
  deregistration_delay = 30

  # /api/ping repond sans appeler AWS ; /api/health ouvrirait une session
  # AgentCore a chaque sonde.
  health_check {
    path                = "/api/ping"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "web_http" {
  count             = local.web_count
  load_balancer_arn = aws_lb.web[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web[0].arn
  }
}

# -----------------------------------------------------------------------------
# ECS
# -----------------------------------------------------------------------------
resource "aws_ecs_cluster" "web" {
  count = local.web_count
  name  = local.web_name
}

resource "aws_ecs_task_definition" "web" {
  count                    = local.web_count
  family                   = local.web_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.web_cpu
  memory                   = var.web_memory
  execution_role_arn       = aws_iam_role.web_execution[0].arn
  task_role_arn            = aws_iam_role.web_task[0].arn

  # Image construite sur un runner GitHub x86_64 (pas d'emulation).
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "web"
    image     = "${data.aws_ecr_repository.web[0].repository_url}:${var.release_id}"
    essential = true
    portMappings = [{
      containerPort = local.web_port
      protocol      = "tcp"
    }]
    # app/CONTRACTS.md section 7 : le serveur trouve le runtime et la machine
    # par leur nom. Connexion (section 7.1) : AUTH_MODE et la configuration
    # Cognito viennent de auth.tf (local.web_auth_environment).
    environment = concat([
      { name = "AGENT_MODE", value = "aws" },
      { name = "AWS_REGION", value = var.aws_region },
      { name = "ALPHAFORGE_PREFIX", value = local.name_snake },
      { name = "ALPHAFORGE_STATE_MACHINE", value = local.collecte_name },
    ], local.web_auth_environment)
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.web[0].name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "web"
      }
    }
  }])
}

resource "aws_ecs_service" "web" {
  count                             = local.web_count
  name                              = local.web_name
  cluster                           = aws_ecs_cluster.web[0].id
  task_definition                   = aws_ecs_task_definition.web[0].arn
  desired_count                     = var.web_desired_count
  launch_type                       = "FARGATE"
  health_check_grace_period_seconds = 60
  propagate_tags                    = "SERVICE"

  # La nouvelle tache demarre avant l'arret de l'ancienne ; une image qui ne
  # demarre pas est annulee au profit de la revision precedente.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.web_subnet_ids
    security_groups  = [aws_security_group.web_tasks[0].id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web[0].arn
    container_name   = "web"
    container_port   = local.web_port
  }

  depends_on = [aws_lb_listener.web_http, aws_iam_role_policy_attachment.web_execution]
}

# -----------------------------------------------------------------------------
# CloudFront : HTTPS sur le domaine par defaut, rien en cache sauf les fichiers
# immuables de Next.js (/_next/static/, noms haches).
#
# Connexion (auth.tf) : le comportement par defaut (pages, /api/*, /api/auth/*)
# ne met rien en cache (Managed-CachingDisabled) et transmet a l'origine tous
# les cookies, la query string (code et state du retour de Cognito) et les
# en-tetes, Host compris (Managed-AllViewer). /_next/static/* ne porte aucune
# donnee personnelle : ni cookie transmis, ni session lue (proxy.ts l'exclut).
# -----------------------------------------------------------------------------
data "aws_cloudfront_cache_policy" "disabled" {
  count = local.web_count
  name  = "Managed-CachingDisabled"
}

data "aws_cloudfront_cache_policy" "optimized" {
  count = local.web_count
  name  = "Managed-CachingOptimized"
}

# Tout passe, Host compris : Next.js voit le domaine CloudFront.
data "aws_cloudfront_origin_request_policy" "all_viewer" {
  count = local.web_count
  name  = "Managed-AllViewer"
}

resource "aws_cloudfront_distribution" "web" {
  count           = local.web_count
  enabled         = true
  comment         = "${local.web_name} : interface AlphaForge, HTTPS devant ALB"
  is_ipv6_enabled = true
  http_version    = "http2and3"
  price_class     = "PriceClass_100"

  origin {
    origin_id   = "alb"
    domain_name = aws_lb.web[0].dns_name

    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_protocol_policy   = "http-only"
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 60
      origin_keepalive_timeout = 60
    }
  }

  default_cache_behavior {
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled[0].id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer[0].id
  }

  ordered_cache_behavior {
    path_pattern           = "/_next/static/*"
    target_origin_id       = "alb"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized[0].id
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
