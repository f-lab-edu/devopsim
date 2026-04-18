output "github_actions_role_arn" {
  description = "IAM Role ARN for GitHub Actions OIDC — use as AWS_ROLE_ARN in workflow"
  value       = aws_iam_role.github_actions.arn
}
