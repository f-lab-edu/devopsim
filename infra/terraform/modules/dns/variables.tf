variable "domain" {
  description = "관리할 루트 도메인 (예: devopsim.cloud)"
  type        = string
}

variable "tags" {
  description = "공통 태그"
  type        = map(string)
  default     = {}
}
