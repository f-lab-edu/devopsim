variable "region" {
  description = "AWS region"
  type        = string
}

variable "aws_profile" {
  description = "AWS CLI profile for local development (null in CI — uses OIDC credential chain)"
  type        = string
  default     = null
}

variable "project" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "devopsim"
}

variable "environment" {
  description = "Deployment environment (e.g. prod, dev)"
  type        = string
}

# VPC
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
}

# EKS
variable "eks_cluster_version" {
  description = "Kubernetes version for EKS cluster"
  type        = string
}

variable "eks_node_instance_type" {
  description = "EC2 instance type for EKS node group"
  type        = string
}

variable "eks_node_desired_size" {
  description = "Desired number of nodes in EKS node group"
  type        = number
}

variable "eks_node_min_size" {
  description = "Minimum number of nodes in EKS node group"
  type        = number
}

variable "eks_node_max_size" {
  description = "Maximum number of nodes in EKS node group"
  type        = number
}
