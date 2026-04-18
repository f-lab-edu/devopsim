variable "name" {
  description = "Name prefix for IAM resources"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository in org/repo format (e.g. f-lab-edu/devopsim)"
  type        = string
}

variable "ecr_repository_arns" {
  description = "List of ECR repository ARNs to grant push access"
  type        = list(string)
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
