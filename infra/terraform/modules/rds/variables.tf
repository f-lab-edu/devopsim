variable "name" {
  description = "Name prefix (project-environment)"
  type        = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  description = "DB Subnet Group에 사용할 프라이빗 서브넷 (최소 2개 AZ)"
  type        = list(string)
}

variable "allowed_security_group_ids" {
  description = "RDS 5432 포트 인입 허용할 보안그룹 (보통 EKS 노드 SG)"
  type        = list(string)
}

variable "engine_version" {
  description = "PostgreSQL 엔진 버전 (us-east-2 가용 버전 중 선택)"
  type        = string
  default     = "16.13"
}

variable "instance_class" {
  description = "Primary와 Replica 동일 클래스 사용"
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "GB 단위, gp3는 최소 20"
  type        = number
  default     = 20
}

variable "db_name" {
  type    = string
  default = "devopsim"
}

variable "master_username" {
  type    = string
  default = "devopsim"
}

variable "backup_retention_days" {
  type    = number
  default = 1
}

variable "create_replica" {
  description = "Read Replica 생성 여부"
  type        = bool
  default     = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
