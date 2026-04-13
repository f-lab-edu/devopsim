output "cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_ca" {
  description = "EKS cluster certificate authority"
  value       = aws_eks_cluster.this.certificate_authority[0].data
}

output "oidc_provider_arn" {
  description = "OIDC Provider ARN for IRSA"
  value       = aws_iam_openid_connect_provider.eks.arn
}

output "alb_controller_role_arn" {
  description = "IAM Role ARN for ALB Controller"
  value       = aws_iam_role.alb_controller.arn
}

output "external_secrets_role_arn" {
  description = "IAM Role ARN for External Secrets"
  value       = aws_iam_role.external_secrets.arn
}
