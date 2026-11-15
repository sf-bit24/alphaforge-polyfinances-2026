# =============================================================================
# Outputs specifiques a l'interface deployee (null si web_enabled = false).
# =============================================================================
output "web_url" {
  description = "URL HTTPS de l'interface (CloudFront)"
  value       = one([for d in aws_cloudfront_distribution.web : "https://${d.domain_name}"])
}

output "web_alb_url" {
  description = "URL HTTP directe de l'ALB : sans la limite de 60 s de CloudFront, pour un build du portefeuille plus long"
  value       = one([for lb in aws_lb.web : "http://${lb.dns_name}"])
}

output "web_image" {
  description = "Image deployee (ECR, tag = release_id)"
  value       = one([for repo in data.aws_ecr_repository.web : "${repo.repository_url}:${var.release_id}"])
}

output "web_cluster_name" {
  description = "Cluster ECS de l'interface"
  value       = one(aws_ecs_cluster.web[*].name)
}

output "web_service_name" {
  description = "Service ECS de l'interface"
  value       = one(aws_ecs_service.web[*].name)
}
