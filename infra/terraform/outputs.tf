output "app_url" {
  description = "Public HTTPS URL (dashboard at /dashboard/)."
  value       = "https://${aws_cloudfront_distribution.app.domain_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service" {
  value = aws_ecs_service.app.name
}

output "github_deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN repository variable."
  value       = aws_iam_role.github_deploy.arn
}

output "admin_key_secret" {
  description = "aws secretsmanager get-secret-value --secret-id <this> --query SecretString --output text"
  value       = aws_secretsmanager_secret.admin_key.name
}

output "log_group" {
  value = aws_cloudwatch_log_group.app.name
}
