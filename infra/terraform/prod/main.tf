locals {
  name = "${var.project}-${var.environment}"

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "vpc" {
  source = "../modules/vpc"

  name               = local.name
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  tags               = local.tags
}

module "ecr" {
  source = "../modules/ecr"

  project      = var.project
  repositories = ["api"]
  tags         = local.tags
}

module "iam" {
  source = "../modules/iam"

  name                = local.name
  github_repo         = "f-lab-edu/devopsim"
  ecr_repository_arns = values(module.ecr.repository_arns)
  tags                = local.tags
}

module "eks" {
  source = "../modules/eks"

  name               = local.name
  cluster_version    = var.eks_cluster_version
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  node_instance_type = var.eks_node_instance_type
  node_desired_size  = var.eks_node_desired_size
  node_min_size      = var.eks_node_min_size
  node_max_size      = var.eks_node_max_size
  tags               = local.tags
}
