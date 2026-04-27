resource "aws_eks_addon" "ebs_csi" {
  cluster_name             = aws_eks_cluster.this.name
  addon_name               = "aws-ebs-csi-driver"
  service_account_role_arn = aws_iam_role.ebs_csi.arn

  tags = var.tags

  depends_on = [aws_eks_node_group.this]
}

# metrics-server: HPA가 Pod CPU/메모리 메트릭을 읽기 위한 컴포넌트
# 자체적으로 AWS API 호출 안 하므로 IRSA 불필요
resource "aws_eks_addon" "metrics_server" {
  cluster_name = aws_eks_cluster.this.name
  addon_name   = "metrics-server"

  tags = var.tags

  depends_on = [aws_eks_node_group.this]
}
