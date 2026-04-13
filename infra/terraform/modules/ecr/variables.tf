variable "project" {
  description = "Project name used as ECR repository prefix"
  type        = string
}

variable "repositories" {
  description = "List of ECR repository names"
  type        = list(string)
  default     = ["api"]
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
