# Loki object storage + IRSA.
#
# 버킷 세 개 (chunks / ruler / admin)를 분리하는 이유는 Loki chart가 기본적으로
# 그렇게 분리해서 path prefix를 두는 구조이기 때문. 하나로 묶어도 동작은 하지만,
# 추후 retention/lifecycle 정책을 chunks에만 적용하려면 분리되어 있는 편이 깔끔.

locals {
  bucket_chunks = "${var.name}-loki-chunks"
  bucket_ruler  = "${var.name}-loki-ruler"
  bucket_admin  = "${var.name}-loki-admin"

  all_buckets = [
    local.bucket_chunks,
    local.bucket_ruler,
    local.bucket_admin,
  ]
}

# ── S3 buckets ──────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "this" {
  for_each = toset(local.all_buckets)

  bucket = each.key
  tags   = var.tags
}

# 공개 접근 차단 (S3 default deny — 보안 가드).
resource "aws_s3_bucket_public_access_block" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 서버사이드 암호화 (SSE-S3). KMS는 비용 + key 관리 부담 → 일단 AES256.
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versioning은 의도적으로 비활성. Loki chunk는 immutable이고 compactor가
# retention 만료 시 delete를 호출 — versioning이 켜져 있으면 delete marker만
# 쌓이고 실제 용량이 줄지 않음.
resource "aws_s3_bucket_versioning" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id

  versioning_configuration {
    status = "Disabled"
  }
}

# Lifecycle: abort_incomplete_multipart_upload만. retention은 Loki compactor가 담당.
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id

  rule {
    id     = "abort-incomplete-mpu"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# ── IRSA role ───────────────────────────────────────────────────────────────

resource "aws_iam_role" "loki" {
  name = "${var.name}-loki-role"

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
          "${var.oidc_provider_url}:sub" = "system:serviceaccount:${var.service_account_namespace}:${var.service_account_name}"
          "${var.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "loki" {
  name = "${var.name}-loki-policy"
  role = aws_iam_role.loki.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BucketLevel"
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ]
        Resource = [for b in local.all_buckets : "arn:aws:s3:::${b}"]
      },
      {
        Sid    = "ObjectLevel"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts",
        ]
        Resource = [for b in local.all_buckets : "arn:aws:s3:::${b}/*"]
      },
    ]
  })
}
