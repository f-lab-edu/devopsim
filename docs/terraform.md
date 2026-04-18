# Terraform 인프라 구성 기록

## 개요

AWS 리전: `us-east-2` (Ohio)  
Terraform 버전: `>= 1.11.0`  
AWS Provider: `~> 6.0`  
State Backend: S3 (`nurihaus-terraform-state/devopsim/prod/terraform.tfstate`)

---

## 디렉터리 구조

환경별 디렉터리 분리 방식을 사용한다. `modules/`는 공유, 환경별 설정은 각 디렉터리에서 관리한다.

```
infra/terraform/
  modules/                    공유 모듈 (환경 무관)
    vpc/                      VPC, 서브넷, 게이트웨이, S3 VPC Endpoint
    eks/
      main.tf                 EKS 클러스터, 노드그룹, IAM Role
      irsa.tf                 OIDC Provider, IRSA 역할들
      addons.tf               EKS Addon (EBS CSI Driver)
    ecr/                      ECR 리포지토리
  prod/                       프로덕션 환경
    backend.tf                S3 remote state (key: devopsim/prod/terraform.tfstate)
    versions.tf               provider, terraform 버전 고정
    variables.tf              입력 변수 선언 (default 없음)
    main.tf                   모듈 호출 (source = "../modules/...")
    outputs.tf                출력값
    prod.tfvars               실제 값 — .gitignore
    prod.tfvars.example       템플릿 — 커밋됨
  # dev/ 환경 추가 시:
  # dev/
  #   backend.tf              key: devopsim/dev/terraform.tfstate
  #   dev.tfvars
  #   ...
```

**환경 추가 방법**: `prod/` 디렉터리를 복사하고 `backend.tf`의 key, `*.tfvars` 값만 바꾸면 된다.

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

Interface Endpoint는 트래픽이 많을 때 NAT 비용 절감 효과가 있지만, 해당 프로젝트 수준에서는 NAT Gateway 데이터 처리 비용이 더 저렴합니다.
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

## 변수 관리 (tfvars)

### 구조

```
infra/terraform/prod/
  variables.tf          변수 선언 (type + description만, default 없음)
  prod.tfvars           prod 실제 값 — .gitignore (커밋 안 함)
  prod.tfvars.example   prod 템플릿 — 커밋됨
```

`aws_profile`은 예외적으로 `default = null`
- 로컬에서는 `prod.tfvars`에서 값을 주고 사용
-  CI(OIDC)에서는 null로 두면 AWS 기본 자격증명 체인을 사용한다.

---

### 변수 적용 우선순위 (낮음 → 높음)

```
variables.tf default
  → terraform.tfvars (파일명이 이거면 -var-file 없이 자동 로드)
    → *.auto.tfvars (알파벳순 자동 로드)
      → -var-file 플래그
        → -var 플래그  ← 최고 우선순위
```

같은 변수가 여러 곳에 정의되면 우선순위가 높은 쪽이 이긴다. 예상치 못한 값이 적용될 때 디버깅 포인트.

---

### 알아야 할 포인트

**Backend는 tfvars로 파라미터화 불가**

```hcl
# 이건 작동 안 함 — Variables not allowed in backend config
terraform {
  backend "s3" {
    bucket = var.state_bucket  # ERROR
  }
}
```

환경별 backend를 분리하려면 별도 파일로 처리해야 한다:

```bash
terraform init -backend-config=backend.prod.hcl
```

**tfvars는 State에 저장되지 않는다**

`terraform apply` 시 tfvars는 입력값으로만 쓰이고, `.tfstate`에는 리소스 결과값만 저장된다. tfvars를 잃어도 인프라는 살아있지만, 다음 `plan` 시 올바른 값을 넣지 않으면 의도치 않은 변경이 감지될 수 있다.

**sensitive 변수와 State 암호화**

```hcl
variable "db_password" {
  type      = string
  sensitive = true  # plan/apply 출력에서 마스킹
}
```

`sensitive = true`는 CLI 출력만 가린다. `.tfstate`에는 평문으로 저장된다. S3 backend에 SSE(서버 사이드 암호화)가 필요한 이유다. 비밀번호 같은 민감한 값은 tfvars가 아니라 환경변수(`TF_VAR_db_password`)나 Secrets Manager에서 주입하는 것이 표준이다.

**CI에서는 -var-file 대신 환경변수**

```bash
# GitHub Actions: secret → TF_VAR_* 환경변수로 주입
TF_VAR_db_password=${{ secrets.DB_PASSWORD }} terraform apply -var-file=prod.tfvars
```

민감하지 않은 설정값은 tfvars, 시크릿은 환경변수로 분리하는 것이 일반적인 패턴이다.

---

## 배포 명령어

```bash
# prod 환경 디렉터리로 이동
cd infra/terraform/prod

# 초기화 (처음 또는 모듈/백엔드 변경 후)
terraform init

# 변경사항 미리보기
terraform plan -var-file=prod.tfvars

# 배포 (~15-20분)
terraform apply -var-file=prod.tfvars

# kubeconfig 설정
aws eks update-kubeconfig \
  --region us-east-2 \
  --name devopsim-prod-cluster \
  --profile devopsim

# 클러스터 확인
kubectl get nodes
kubectl get pods -A

# 삭제
terraform destroy -var-file=prod.tfvars
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

## 시크릿 관리 (SSM Parameter Store)

### 왜 SSM인가

Terraform은 시크릿 값을 `.tfstate`에 평문으로 저장한다. `sensitive = true`는 CLI 출력만 가릴 뿐이다. DB 패스워드 같은 값을 tfvars나 `TF_VAR_*`로 주입하면 결국 state 파일에 남는다.

SSM Parameter Store를 쓰면 Terraform이 시크릿 값을 아예 모른 채로 리소스를 구성할 수 있다.

### 네이밍 컨벤션

```
/<project>/<environment>/<category>/<key>
/devopsim/prod/db/password
/devopsim/prod/db/host
/devopsim/prod/api/secret_key
```

### 패턴 1: Terraform이 SSM에서 직접 읽기

시크릿이 SSM에 이미 등록되어 있을 때. Terraform이 apply 시점에 직접 값을 가져온다. tfvars, 환경변수 어디에도 실제 값이 지나가지 않는다.

```hcl
data "aws_ssm_parameter" "db_password" {
  name            = "/devopsim/prod/db/password"
  with_decryption = true
}

resource "aws_db_instance" "main" {
  password = data.aws_ssm_parameter.db_password.value
}
```

이 패턴을 사용하려면 Terraform을 실행하는 IAM Role(CI의 OIDC Role)에 권한이 필요하다:
```json
{
  "Action": ["ssm:GetParameter", "ssm:GetParameters"],
  "Resource": "arn:aws:ssm:us-east-2:893286712531:parameter/devopsim/prod/*"
}
```

### 패턴 2: Terraform은 경로만 만들고, 값은 별도 등록

Terraform이 SSM 파라미터 리소스 자체만 생성하고 실제 값은 운영자가 별도로 넣는다.

```hcl
resource "aws_ssm_parameter" "db_password" {
  name  = "/devopsim/prod/db/password"
  type  = "SecureString"
  value = "CHANGE_ME"   # 초기 placeholder — 배포 후 콘솔/CLI로 교체

  lifecycle {
    ignore_changes = [value]   # Terraform이 값 변경을 추적하지 않음
  }
}
```

```bash
# 실제 값 등록 (1회)
aws ssm put-parameter \
  --name "/devopsim/prod/db/password" \
  --value "실제패스워드" \
  --type SecureString \
  --overwrite \
  --profile devopsim
```

### Kubernetes에서 SSM 값 사용 — External Secrets Operator

EKS 파드가 SSM 값을 쓸 때는 직접 읽는 것이 아니라 External Secrets Operator가 SSM에서 읽어 Kubernetes Secret으로 동기화한다. `external-secrets-role` IRSA가 이미 준비되어 있다.

```
SSM Parameter Store
  ↑ (읽기, IRSA)
External Secrets Operator (EKS 내부)
  ↓ (생성/갱신)
Kubernetes Secret
  ↓ (마운트)
Pod
```

```yaml
# ExternalSecret CRD 예시
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: db-credentials
  namespace: default
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-ssm
    kind: ClusterSecretStore
  target:
    name: db-secret          # 생성될 Kubernetes Secret 이름
  data:
    - secretKey: password    # Kubernetes Secret의 key
      remoteRef:
        key: /devopsim/prod/db/password   # SSM parameter 경로
```

---

## 주의사항

- `terraform destroy` 시 EKS 노드에 PVC가 붙어있으면 EBS 볼륨이 남을 수 있음 → 수동 삭제 필요
- NAT Gateway는 1개만 생성 (비용 절감). HA 필요 시 AZ별 1개씩 추가
- EKS 엔드포인트 public 접근 허용 상태 — 운영 환경에서는 IP 제한 권장
