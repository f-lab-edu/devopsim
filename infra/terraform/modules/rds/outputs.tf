output "primary_endpoint" {
  description = "Primary RDS endpoint (host:port)"
  value       = aws_db_instance.primary.endpoint
}

output "primary_address" {
  description = "Primary host (port 제외)"
  value       = aws_db_instance.primary.address
}

output "primary_port" {
  value = aws_db_instance.primary.port
}

output "replica_endpoint" {
  description = "Read Replica endpoint, replica 미생성 시 null"
  value       = var.create_replica ? aws_db_instance.replica[0].endpoint : null
}

output "replica_address" {
  value = var.create_replica ? aws_db_instance.replica[0].address : null
}

output "db_name" {
  value = aws_db_instance.primary.db_name
}

output "master_username" {
  value = aws_db_instance.primary.username
}

# Secrets Manager ARN — External Secrets Operator로 K8s Secret에 동기화할 때 사용
# username/password/host/port/dbname JSON 형태로 저장됨
output "master_user_secret_arn" {
  description = "Secrets Manager에 저장된 RDS 자격증명 + 연결 정보 ARN"
  value       = aws_secretsmanager_secret.master.arn
}

output "master_user_secret_name" {
  description = "Secrets Manager 시크릿 이름"
  value       = aws_secretsmanager_secret.master.name
}

output "security_group_id" {
  description = "RDS 보안그룹 ID"
  value       = aws_security_group.this.id
}
