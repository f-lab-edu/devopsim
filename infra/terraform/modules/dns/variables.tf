variable "domain" {
  description = "관리할 루트 도메인 (예: devopsim.cloud)"
  type        = string
}

variable "name" {
  description = "IAM 리소스 이름 prefix (예: devopsim-prod)"
  type        = string
  default     = ""
}

variable "oidc_provider_arn" {
  description = "EKS OIDC Provider ARN (external-dns IRSA용)"
  type        = string
  default     = ""
}

variable "oidc_provider_url" {
  description = "EKS OIDC issuer URL (host)"
  type        = string
  default     = ""
}

variable "external_dns_namespace" {
  description = "external-dns ServiceAccount namespace"
  type        = string
  default     = "external-dns"
}

variable "external_dns_service_account" {
  description = "external-dns ServiceAccount 이름"
  type        = string
  default     = "external-dns"
}

variable "tags" {
  description = "공통 태그"
  type        = map(string)
  default     = {}
}
