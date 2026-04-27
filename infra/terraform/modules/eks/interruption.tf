# Karpenter Interruption Queue
# Spot 인터럽션, EC2 상태 변경, AWS Health 이벤트를 받는 SQS 큐

resource "aws_sqs_queue" "karpenter" {
  name                      = aws_eks_cluster.this.name
  message_retention_seconds = 300
  sqs_managed_sse_enabled   = true

  tags = var.tags
}

# 큐 정책 — EventBridge가 메시지 보낼 수 있게 허용 + HTTPS 강제
resource "aws_sqs_queue_policy" "karpenter" {
  queue_url = aws_sqs_queue.karpenter.url

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EventBridgeWrite"
        Effect = "Allow"
        Principal = {
          Service = ["events.amazonaws.com", "sqs.amazonaws.com"]
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.karpenter.arn
      },
      {
        Sid       = "DenyHTTP"
        Effect    = "Deny"
        Principal = "*"
        Action    = "sqs:*"
        Resource  = aws_sqs_queue.karpenter.arn
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
    ]
  })
}

# EventBridge Rules
# 5개 이벤트를 SQS 큐로 라우팅 (공식 CloudFormation 템플릿과 동일)

locals {
  karpenter_event_rules = {
    scheduled_change = {
      description  = "AWS Health 이벤트 (예정된 유지보수 등)"
      source       = "aws.health"
      detail_types = ["AWS Health Event"]
    }
    spot_interruption = {
      description  = "Spot 인스턴스 회수 2분 전 경고"
      source       = "aws.ec2"
      detail_types = ["EC2 Spot Instance Interruption Warning"]
    }
    rebalance = {
      description  = "Spot 리밸런싱 권고 (회수 가능성 높아질 때)"
      source       = "aws.ec2"
      detail_types = ["EC2 Instance Rebalance Recommendation"]
    }
    instance_state_change = {
      description  = "EC2 상태 변경 (running → terminated 등)"
      source       = "aws.ec2"
      detail_types = ["EC2 Instance State-change Notification"]
    }
    capacity_reservation = {
      description  = "Capacity Reservation 인스턴스 회수 경고"
      source       = "aws.ec2"
      detail_types = ["EC2 Capacity Reservation Instance Interruption Warning"]
    }
  }
}

resource "aws_cloudwatch_event_rule" "karpenter" {
  for_each = local.karpenter_event_rules

  name        = "${var.name}-karpenter-${replace(each.key, "_", "-")}"
  description = each.value.description

  event_pattern = jsonencode({
    source      = [each.value.source]
    detail-type = each.value.detail_types
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "karpenter" {
  for_each = local.karpenter_event_rules

  rule      = aws_cloudwatch_event_rule.karpenter[each.key].name
  target_id = "KarpenterInterruptionQueueTarget"
  arn       = aws_sqs_queue.karpenter.arn
}
