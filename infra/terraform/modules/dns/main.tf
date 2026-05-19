# Route53 hosted zone.
#
# 도메인은 registrar(가비아)에서 구매. 여기서는 그 도메인의 DNS 관리를
# Route53에 위임받기 위한 zone만 생성.
# zone 생성 후 출력되는 NS 4개를 registrar 콘솔의 네임서버 설정에 입력.
#
# 실제 record(A/ALIAS/CNAME 등)는 zone이 만들어진 뒤 다른 곳에서
# aws_route53_record 리소스로 추가 (Traefik NLB 주소 결정 후).

resource "aws_route53_zone" "this" {
  name = var.domain

  comment = "Managed by Terraform — devopsim ${var.domain} root zone"

  tags = var.tags
}

# ── external-dns IRSA ───────────────────────────────────────────────────────
#
# external-dns가 cluster의 Gateway/HTTPRoute 리소스를 watch하고 Route53 record를
# 자동 생성/갱신. 권한은 의도적으로 좁힘:
#   - 위에서 만든 hosted zone에 대해서만 ChangeResourceRecordSets
#   - 모든 hosted zone에 대한 List/Get은 허용 (zone discovery용 — write 권한 없음)
#
# policy: upsert-only로 운영해도 cluster에서 권한 자체는 동일하게 필요함.

resource "aws_iam_role" "external_dns" {
  name = "${var.name}-external-dns-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = var.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${var.oidc_provider_url}:sub" = "system:serviceaccount:${var.external_dns_namespace}:${var.external_dns_service_account}"
          "${var.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "external_dns" {
  name = "${var.name}-external-dns-policy"
  role = aws_iam_role.external_dns.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "WriteOurZoneOnly"
        Effect = "Allow"
        Action = ["route53:ChangeResourceRecordSets"]
        Resource = [
          "arn:aws:route53:::hostedzone/${aws_route53_zone.this.zone_id}",
        ]
      },
      {
        Sid    = "DiscoverZones"
        Effect = "Allow"
        Action = [
          "route53:ListHostedZones",
          "route53:ListResourceRecordSets",
          "route53:ListTagsForResource",
        ]
        Resource = ["*"]
      },
    ]
  })
}
