# Terraform 인프라 구성 기록

## 개요

AWS 리전: `us-east-2` (Ohio)  
Terraform 버전: `>= 1.11.0`  
AWS Provider: `~> 6.0`  
State Backend: S3 (`nurihaus-terraform-state/devopsim/terraform.tfstate`)

---

## 모듈 구조

```
infra/terraform/
  versions.tf        provider, terraform 버전 고정
  backend.tf         S3 remote state 설정
  variables.tf       입력 변수 (region, project, VPC, EKS 설정)
  main.tf            모듈 호출 (vpc, ecr, eks)
  outputs.tf         출력값 (vpc_id, cluster_name, kubeconfig 명령어 등)
  modules/
    vpc/             VPC, 서브넷, 게이트웨이, S3 VPC Endpoint
    eks/
      main.tf        EKS 클러스터, 노드그룹, IAM Role
      irsa.tf        OIDC Provider, IRSA 역할들
      addons.tf      EKS Addon (EBS CSI Driver)
    ecr/             ECR 리포지토리
```

---

## 리소스 구성

### VPC (`modules/vpc/`)

| 리소스 | 이름 | 설명 |
|---|---|---|
| VPC | devopsim-prod-vpc | 10.0.0.0/16 |
| Public Subnet | devopsim-prod-public-us-east-2a/b | 10.0.0.0/24, 10.0.1.0/24 |
| Private Subnet | devopsim-prod-private-us-east-2a/b | 10.0.10.0/24, 10.0.11.0/24 |
| Internet Gateway | devopsim-prod-igw | Public 서브넷 인터넷 출구 |
| NAT Gateway | devopsim-prod-nat | Private 서브넷 아웃바운드 출구 (1개) |
| Elastic IP | devopsim-prod-nat-eip | NAT Gateway용 고정 IP |
| Public Route Table | devopsim-prod-public-rt | 0.0.0.0/0 → IGW |
| Private Route Table | devopsim-prod-private-rt | 0.0.0.0/0 → NAT Gateway |
| S3 Gateway Endpoint | devopsim-prod-s3-endpoint | ECR 이미지 레이어 pull (무료) |

**서브넷 태그 (ALB Controller가 사용):**
- Public: `kubernetes.io/role/elb: "1"` — 외부 ALB 배치용
- Private: `kubernetes.io/role/internal-elb: "1"` — Internal ALB 배치용

**VPC Endpoint 결정:**

| 타입 | 비용 | 결정 |
|---|---|---|
| Gateway (S3, DynamoDB) | 무료 | S3 적용 |
| Interface (ECR, STS 등) | ~$14/월/엔드포인트 | 미적용 |

Interface Endpoint는 트래픽이 많을 때 NAT 비용 절감 효과가 있지만, 학습 프로젝트 수준에서는 NAT Gateway 데이터 처리 비용이 더 저렴합니다. 트래픽이 늘어나면 추가 검토합니다.

---

### EKS (`modules/eks/`)

**`main.tf` — 클러스터 + 노드그룹**

| 리소스 | 설명 |
|---|---|
| EKS Cluster | devopsim-prod-cluster, K8s 1.35 |
| Cluster IAM Role | eks.amazonaws.com AssumeRole + AmazonEKSClusterPolicy |
| Managed Node Group | t3.medium, desired 2 / min 1 / max 3 |
| Node IAM Role | AmazonEKSWorkerNodePolicy, AmazonEKS_CNI_Policy, AmazonEC2ContainerRegistryReadOnly |

EKS 엔드포인트: private + public 모두 활성화 (로컬 kubectl 접근)

**`irsa.tf` — OIDC + IRSA**

IRSA(IAM Role for Service Accounts): EKS OIDC Provider를 통해 특정 ServiceAccount에 IAM Role을 부여합니다. Pod에 static credential 없이 AWS API 접근이 가능합니다.

```
Pod → ServiceAccount → OIDC → IAM Role → AWS API
```

| IAM Role | ServiceAccount | 용도 |
|---|---|---|
| ebs-csi-role | kube-system/ebs-csi-controller-sa | EBS 볼륨 생성/관리 |
| alb-controller-role | kube-system/aws-load-balancer-controller | ALB 자동 생성 |
| external-secrets-role | external-secrets/external-secrets | Secrets Manager 접근 |

**`addons.tf` — EKS Addon**

| Addon | 용도 |
|---|---|
| aws-ebs-csi-driver | StatefulSet PVC → EBS 볼륨 자동 프로비저닝 |

EKS 1.23+에서 EBS CSI Driver가 기본 내장에서 제거되어 별도 addon 설치 필요.

---

### ECR (`modules/ecr/`)

| 리소스 | 값 |
|---|---|
| Repository | devopsim/api |
| scan_on_push | true (CVE 스캔) |
| Lifecycle Policy | 최근 10개 이미지만 유지 |

---

## 네트워크 트래픽 흐름

```
인터넷
  ↓↑
Internet Gateway
  ↓
Public Subnet (ALB, NAT Gateway 위치)

Private Subnet (EKS 노드)
  → ECR 이미지 레이어 pull  → S3 Gateway Endpoint (NAT 안 거침)
  → ECR API / STS / 기타    → NAT Gateway → Internet Gateway
  → ALB → 노드 (인바운드)   → ALB에서 직접
```

---

## 배포 명령어

```bash
# 초기화
terraform init

# 변경사항 미리보기
terraform plan

# 배포 (~15-20분)
terraform apply

# kubeconfig 설정
aws eks update-kubeconfig \
  --region us-east-2 \
  --name devopsim-prod-cluster \
  --profile devopsim

# 클러스터 확인
kubectl get nodes
kubectl get pods -A

# 삭제
terraform destroy
```

---

## 비용 추정 (us-east-2 기준)

| 리소스 | 월 예상 비용 |
|---|---|
| EKS Cluster | ~$72 |
| t3.medium × 2 노드 | ~$60 |
| NAT Gateway | ~$32 + 데이터 처리량 ($0.045/GB) |
| S3 Gateway Endpoint | 무료 |
| ECR | 무료 (500MB/월 이하) |
| **합계** | **~$164/월 + 데이터 처리량** |

Interface VPC Endpoint 제거로 월 ~$57 절감.

---

## 주의사항

- `terraform destroy` 시 EKS 노드에 PVC가 붙어있으면 EBS 볼륨이 남을 수 있음 → 수동 삭제 필요
- NAT Gateway는 1개만 생성 (비용 절감). HA 필요 시 AZ별 1개씩 추가
- EKS 엔드포인트 public 접근 허용 상태 — 운영 환경에서는 IP 제한 권장
