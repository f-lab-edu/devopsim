output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnet_ids
}

output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "eks_kubeconfig_command" {
  description = "Command to update kubeconfig"
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}${var.aws_profile != null ? " --profile ${var.aws_profile}" : ""}"
}

output "ecr_repository_urls" {
  description = "ECR repository URLs"
  value       = module.ecr.repository_urls
}

output "github_actions_role_arn" {
  description = "GitHub Actions IAM Role ARN — set as AWS_ROLE_ARN in GitHub repository variables"
  value       = module.iam.github_actions_role_arn
}

output "alb_controller_role_arn" {
  description = "ALB Controller IAM Role ARN (for Helm install)"
  value       = module.eks.alb_controller_role_arn
}

output "external_secrets_role_arn" {
  description = "External Secrets IAM Role ARN (for Helm install)"
  value       = module.eks.external_secrets_role_arn
}

output "karpenter_controller_role_arn" {
  description = "Karpenter 컨트롤러 IRSA Role ARN — Helm ServiceAccount annotation에 사용"
  value       = module.eks.karpenter_controller_role_arn
}

output "karpenter_node_role_name" {
  description = "Karpenter 노드 Role 이름 — aws-auth ConfigMap에 등록"
  value       = module.eks.karpenter_node_role_name
}

output "karpenter_node_instance_profile_name" {
  description = "Karpenter 노드 Instance Profile 이름 — EC2NodeClass의 instanceProfile에 사용"
  value       = module.eks.karpenter_node_instance_profile_name
}

output "karpenter_interruption_queue_name" {
  description = "Karpenter Interruption SQS Queue 이름 — Helm settings.interruptionQueue에 사용"
  value       = module.eks.karpenter_interruption_queue_name
}

# ── RDS ──────────────────────────────────────────────────────────────────────

output "rds_primary_endpoint" {
  description = "Primary RDS endpoint (host:port)"
  value       = module.rds.primary_endpoint
}

output "rds_primary_address" {
  description = "Primary host (port 제외)"
  value       = module.rds.primary_address
}

output "rds_replica_endpoint" {
  description = "Read Replica endpoint"
  value       = module.rds.replica_endpoint
}

output "rds_replica_address" {
  description = "Read Replica host (port 제외)"
  value       = module.rds.replica_address
}

output "rds_db_name" {
  value = module.rds.db_name
}

output "rds_master_user_secret_arn" {
  description = "Secrets Manager ARN — External Secrets Operator로 K8s Secret에 동기화"
  value       = module.rds.master_user_secret_arn
}

output "rds_master_user_secret_name" {
  description = "Secrets Manager 시크릿 이름 (ExternalSecret remoteRef.key에 사용)"
  value       = module.rds.master_user_secret_name
}
