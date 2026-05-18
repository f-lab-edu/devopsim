variable "name" {
  description = "리소스 이름 prefix (예: devopsim-prod)"
  type        = string
}

variable "oidc_provider_arn" {
  description = "EKS OIDC Provider ARN (IRSA trust policy에 사용)"
  type        = string
}

variable "oidc_provider_url" {
  description = "EKS OIDC issuer URL (https:// 없는 host 부분)"
  type        = string
}

variable "service_account_namespace" {
  description = "Loki ServiceAccount의 namespace"
  type        = string
  default     = "monitoring"
}

variable "service_account_name" {
  description = "Loki ServiceAccount 이름 (Helm chart default: loki)"
  type        = string
  default     = "loki"
}

variable "tags" {
  description = "공통 태그"
  type        = map(string)
  default     = {}
}
