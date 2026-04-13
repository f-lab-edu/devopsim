data "aws_region" "current" {}

locals {
  az_count = length(var.availability_zones)

  # vpc: 10.0.0.0/16
  # public:  10.0.0.0/24, 10.0.1.0/24
  # private: 10.0.10.0/24, 10.0.11.0/24
  public_cidrs  = [for i in range(local.az_count) : cidrsubnet(var.vpc_cidr, 8, i)]
  private_cidrs = [for i in range(local.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 10)]
}

# VPC
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true # EKS 노드가 DNS로 통신하려면 필요

  tags = merge(var.tags, {
    Name = "${var.name}-vpc"
  })
}

# Internet Gateway
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, {
    Name = "${var.name}-igw"
  })
}

# Public Subnets
resource "aws_subnet" "public" {
  count = local.az_count

  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.public_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true # Public 서브넷: 인스턴스에 자동으로 퍼블릭 IP 부여

  tags = merge(var.tags, {
    Name                     = "${var.name}-public-${var.availability_zones[count.index]}"
    "kubernetes.io/role/elb" = "1" # ALB가 이 서브넷을 찾는 태그
  })
}

# Private Subnets
resource "aws_subnet" "private" {
  count = local.az_count

  vpc_id            = aws_vpc.this.id
  cidr_block        = local.private_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = merge(var.tags, {
    Name                              = "${var.name}-private-${var.availability_zones[count.index]}"
    "kubernetes.io/role/internal-elb" = "1" # Internal ALB용 태그
  })
}

# Elastic IP for NAT Gateway
resource "aws_eip" "nat" {
  domain = "vpc"

  tags = merge(var.tags, {
    Name = "${var.name}-nat-eip"
  })
}

# NAT Gateway — Private 서브넷의 아웃바운드 인터넷 출구 (1개로 비용 절감)
resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id # Public 서브넷에 위치

  tags = merge(var.tags, {
    Name = "${var.name}-nat"
  })

  depends_on = [aws_internet_gateway.this]
}

# Public Route Table — IGW로 라우팅
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = merge(var.tags, {
    Name = "${var.name}-public-rt"
  })
}

# Private Route Table — NAT Gateway로 라우팅
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this.id
  }

  tags = merge(var.tags, {
    Name = "${var.name}-private-rt"
  })
}

# Route Table 연결
resource "aws_route_table_association" "public" {
  count = local.az_count

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count = local.az_count

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# S3 Gateway Endpoint — 무료, ECR 이미지 레이어 pull 시 NAT 비용 절감
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.id}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = merge(var.tags, {
    Name = "${var.name}-s3-endpoint"
  })
}
