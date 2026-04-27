# Karpenter Discovery Tag (보안그룹)
resource "aws_ec2_tag" "karpenter_cluster_sg" {
  resource_id = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  key         = "karpenter.sh/discovery"
  value       = aws_eks_cluster.this.name
}

# Karpenter Node Role
# Karpenter가 생성한 EC2 노드에 부여하는 역할
resource "aws_iam_role" "karpenter_node" {
  name = "${var.name}-karpenter-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "karpenter_node" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
  ])

  role       = aws_iam_role.karpenter_node.name
  policy_arn = each.value
}

# EC2NodeClass의 role 필드에 지정하는 인스턴스 프로파일
resource "aws_iam_instance_profile" "karpenter_node" {
  name = "${var.name}-karpenter-node-profile"
  role = aws_iam_role.karpenter_node.name

  tags = var.tags
}

# Karpenter Controller Role (IRSA)
#
# Karpenter 컨트롤러 Pod에 부여하는 역할
resource "aws_iam_role" "karpenter_controller" {
  name = "${var.name}-karpenter-controller-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.eks.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_host}:sub" = "system:serviceaccount:kube-system:karpenter"
          "${local.oidc_host}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "karpenter_controller" {
  name = "${var.name}-karpenter-controller-policy"
  role = aws_iam_role.karpenter_controller.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # EC2 노드 생성/삭제 및 조회
        Sid    = "NodeLifecycle"
        Effect = "Allow"
        Action = [
          "ec2:CreateFleet",
          "ec2:CreateLaunchTemplate",
          "ec2:CreateTags",
          "ec2:DeleteLaunchTemplate",
          "ec2:RunInstances",
          "ec2:TerminateInstances",
          "ec2:DescribeAvailabilityZones",
          "ec2:DescribeImages",
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "ec2:DescribeInstanceTypeOfferings",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeLaunchTemplates",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeSpotPriceHistory",
          "ec2:DescribeSubnets",
        ]
        Resource = "*"
      },
      {
        # IAM 인스턴스 프로파일 조작 (노드에 역할 연결)
        Sid    = "IAMIntegration"
        Effect = "Allow"
        Action = [
          "iam:AddRoleToInstanceProfile",
          "iam:CreateInstanceProfile",
          "iam:DeleteInstanceProfile",
          "iam:GetInstanceProfile",
          "iam:ListInstanceProfiles",
          "iam:RemoveRoleFromInstanceProfile",
          "iam:TagInstanceProfile",
        ]
        Resource = "*"
      },
      {
        # AMI alias 해석 — al2023@latest 같은 alias를 EKS 최적화 AMI ID로 변환
        # Karpenter가 SSM Parameter Store에서 AMI ID 조회
        Sid      = "AMIDiscovery"
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = "arn:aws:ssm:*::parameter/aws/service/*"
      },
      {
        # Karpenter 노드 역할을 EC2에 넘기기 위한 PassRole
        # Karpenter가 생성한 노드 역할만 허용
        Sid      = "PassNodeRole"
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = aws_iam_role.karpenter_node.arn
      },
      {
        # EKS 클러스터 정보 조회 (엔드포인트, CA 등)
        Sid      = "EKSIntegration"
        Effect   = "Allow"
        Action   = "eks:DescribeCluster"
        Resource = aws_eks_cluster.this.arn
      },
      {
        # Spot 인터럽션 이벤트 수신 (SQS)
        Sid    = "Interruption"
        Effect = "Allow"
        Action = [
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl",
          "sqs:ReceiveMessage",
        ]
        Resource = aws_sqs_queue.karpenter.arn
      },
      {
        # 인스턴스 타입별 가격 조회 (최적 인스턴스 선택에 사용)
        Sid      = "PricingDiscovery"
        Effect   = "Allow"
        Action   = "pricing:GetProducts"
        Resource = "*"
      },
    ]
  })
}
