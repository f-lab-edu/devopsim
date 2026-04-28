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

output "cluster_security_group_id" {
  description = "EKS가 자동 생성한 클러스터 보안그룹 (모든 노드에 부여됨, RDS 인입 허용 등에 사용)"
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "alb_controller_role_arn" {
  description = "IAM Role ARN for ALB Controller"
  value       = aws_iam_role.alb_controller.arn
}

output "external_secrets_role_arn" {
  description = "IAM Role ARN for External Secrets"
  value       = aws_iam_role.external_secrets.arn
}

# ── Karpenter outputs ────────────────────────────────────────────────────────

output "karpenter_controller_role_arn" {
  description = "Karpenter 컨트롤러 IRSA Role ARN (Helm values의 ServiceAccount annotation에 사용)"
  value       = aws_iam_role.karpenter_controller.arn
}

output "karpenter_node_role_name" {
  description = "Karpenter 노드 Role 이름 (aws-auth ConfigMap에 등록할 때 사용)"
  value       = aws_iam_role.karpenter_node.name
}

output "karpenter_node_role_arn" {
  description = "Karpenter 노드 Role ARN"
  value       = aws_iam_role.karpenter_node.arn
}

output "karpenter_node_instance_profile_name" {
  description = "Karpenter 노드 Instance Profile 이름 (EC2NodeClass의 instanceProfile 필드에 사용)"
  value       = aws_iam_instance_profile.karpenter_node.name
}

output "karpenter_interruption_queue_name" {
  description = "Karpenter Interruption SQS Queue 이름 (Helm values의 settings.interruptionQueue에 사용)"
  value       = aws_sqs_queue.karpenter.name
}
