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
