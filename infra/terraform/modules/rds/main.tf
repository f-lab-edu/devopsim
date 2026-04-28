# 비밀번호 직접 생성 — RDS managed master password는 Read Replica와 호환 안 됨
# 대신 random_password + Secrets Manager로 동일 효과 구현
resource "random_password" "master" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "master" {
  name                    = "${var.name}/rds/master"
  description             = "RDS master password for ${var.name}-postgres"
  recovery_window_in_days = 0 # 학습용 — 즉시 삭제 가능

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "master" {
  secret_id = aws_secretsmanager_secret.master.id
  secret_string = jsonencode({
    username = var.master_username
    password = random_password.master.result
    engine   = "postgres"
    host     = aws_db_instance.primary.address
    port     = aws_db_instance.primary.port
    dbname   = aws_db_instance.primary.db_name
  })
}

# Subnet Group — 프라이빗 서브넷 2개 AZ 사용 (Multi-AZ Replica용)
resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name}-db-subnet-group"
  })
}

# Security Group — EKS 노드 SG에서만 5432 인입 허용
resource "aws_security_group" "this" {
  name        = "${var.name}-rds-sg"
  description = "RDS PostgreSQL access from EKS nodes"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.name}-rds-sg"
  })
}

resource "aws_security_group_rule" "ingress_from_eks" {
  for_each = toset(var.allowed_security_group_ids)

  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = each.value
  security_group_id        = aws_security_group.this.id
  description              = "PostgreSQL from EKS node SG ${each.value}"
}

# Custom Parameter Group — 슬로우 쿼리 학습용 설정
resource "aws_db_parameter_group" "this" {
  name   = "${var.name}-postgres16"
  family = "postgres16"

  # pg_stat_statements 익스텐션 활성화 (재시작 필요)
  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }

  # 100ms 이상 쿼리는 CloudWatch Logs로 기록
  parameter {
    name  = "log_min_duration_statement"
    value = "100"
  }

  # DDL 변경도 로깅
  parameter {
    name  = "log_statement"
    value = "ddl"
  }

  parameter {
    name  = "pg_stat_statements.track"
    value = "all"
  }

  tags = var.tags
}

# Primary
resource "aws_db_instance" "primary" {
  identifier     = "${var.name}-postgres"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true
  max_allocated_storage = 0 # 자동 확장 비활성 (비용 안전)

  db_name  = var.db_name
  username = var.master_username
  password = random_password.master.result

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.this.id]
  parameter_group_name   = aws_db_parameter_group.this.name
  publicly_accessible    = false

  backup_retention_period = var.backup_retention_days
  backup_window           = "17:00-18:00" # KST 02-03시
  maintenance_window      = "sun:18:00-sun:19:00"

  # Performance Insights — t-class는 7일 보존 무료
  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  # 슬로우 쿼리 로그를 CloudWatch에 전송
  enabled_cloudwatch_logs_exports = ["postgresql"]

  # 학습용: 삭제 보호 끄고, 스냅샷 없이 바로 삭제 허용
  deletion_protection      = false
  skip_final_snapshot      = true
  delete_automated_backups = true

  apply_immediately = true # 변경사항 즉시 반영

  tags = merge(var.tags, {
    Name = "${var.name}-postgres-primary"
    Role = "primary"
  })
}

# Read Replica
resource "aws_db_instance" "replica" {
  count = var.create_replica ? 1 : 0

  identifier          = "${var.name}-postgres-replica"
  replicate_source_db = aws_db_instance.primary.identifier
  instance_class      = var.instance_class

  storage_type      = "gp3"
  storage_encrypted = true

  vpc_security_group_ids = [aws_security_group.this.id]
  parameter_group_name   = aws_db_parameter_group.this.name
  publicly_accessible    = false

  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  # Replica는 backup retention 0 (Primary가 백업 담당)
  backup_retention_period = 0

  deletion_protection = false
  skip_final_snapshot = true

  apply_immediately = true

  tags = merge(var.tags, {
    Name = "${var.name}-postgres-replica"
    Role = "replica"
  })
}
