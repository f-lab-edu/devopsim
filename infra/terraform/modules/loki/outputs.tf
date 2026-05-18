output "role_arn" {
  description = "Loki IRSA Role ARN (HelmRelease values의 serviceAccount.annotations에 사용)"
  value       = aws_iam_role.loki.arn
}

output "bucket_chunks" {
  description = "Chunks bucket 이름"
  value       = local.bucket_chunks
}

output "bucket_ruler" {
  description = "Ruler bucket 이름"
  value       = local.bucket_ruler
}

output "bucket_admin" {
  description = "Admin bucket 이름"
  value       = local.bucket_admin
}
