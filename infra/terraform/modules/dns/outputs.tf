output "zone_id" {
  description = "Route53 hosted zone ID (Traefik record 생성 시 사용)"
  value       = aws_route53_zone.this.zone_id
}

output "zone_name" {
  description = "Hosted zone 이름 (= 도메인)"
  value       = aws_route53_zone.this.name
}

output "name_servers" {
  description = "Registrar(가비아 등) 콘솔의 네임서버 설정에 입력할 NS 4개"
  value       = aws_route53_zone.this.name_servers
}

output "external_dns_role_arn" {
  description = "external-dns IRSA Role ARN (HelmRelease serviceAccount.annotations에 사용)"
  value       = aws_iam_role.external_dns.arn
}
