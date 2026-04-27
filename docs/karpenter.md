# Karpenter 도입 가이드

> 기준: 2026-04-26 / Karpenter v1.12.0 / EKS 1.35

---

## 현재 인프라 상태 요약

Karpenter를 도입하기 전에 지금 뭐가 있는지 파악하는 것이 먼저다.

### EKS 클러스터

| 항목 | 값 |
|------|-----|
| 클러스터 이름 | `devopsim-prod-cluster` |
| K8s 버전 | 1.35 |
| 리전 | us-east-2 |
| AZ | us-east-2a, us-east-2b |

### 관리형 노드 그룹 (현재)

| 항목 | 값 |
|------|-----|
| 인스턴스 타입 | t3.medium (고정) |
| desired | 2 |
| min | 1 |
| max | 3 |
| 용량 유형 | ON_DEMAND (기본값) |
| 스케일링 | Cluster Autoscaler 없음 — 수동 |

### IAM 역할 목록

| 역할 이름 | 용도 | 연결된 정책 |
|-----------|------|-------------|
| `devopsim-prod-eks-cluster-role` | EKS 컨트롤 플레인 | AmazonEKSClusterPolicy |
| `devopsim-prod-eks-node-role` | EC2 노드 그룹 워커 | AmazonEKSWorkerNodePolicy, AmazonEKS_CNI_Policy, AmazonEC2ContainerRegistryReadOnly |
| `devopsim-prod-ebs-csi-role` | EBS CSI Driver (IRSA) | AmazonEBSCSIDriverPolicy |
| `devopsim-prod-alb-controller-role` | ALB Ingress Controller (IRSA) | alb-controller-policy (커스텀 인라인) |
| `devopsim-prod-external-secrets-role` | External Secrets (IRSA) | SecretsManager 조회 (커스텀 인라인) |
| `devopsim-prod-github-actions` | GitHub Actions OIDC | ECR push 권한 |

### IRSA 현황

OIDC 프로바이더가 이미 생성되어 있고, ebs-csi / alb-controller / external-secrets 3개가 IRSA로 동작 중이다.
Karpenter 컨트롤러도 같은 방식(IRSA)으로 추가하면 된다.

---

## Karpenter란 무엇인가

### 한 줄 정의

> Karpenter는 **스케줄되지 못한 Pod를 감지하면 그 Pod에 딱 맞는 EC2를 직접 생성**하고,
> 필요 없어진 노드는 스스로 삭제하는 노드 프로비저너다.

### 기존 Cluster Autoscaler와의 차이

```
Cluster Autoscaler                    Karpenter
──────────────────────────────────    ──────────────────────────────────
ASG(Auto Scaling Group) 단위 조작     EC2 Fleet API 직접 호출
노드 그룹 단위로 스케일 업/다운       Pod 요구사항 기반으로 최적 인스턴스 선택
인스턴스 타입 고정                     다양한 인스턴스 타입 중 최적 선택
스케일 다운 느림 (기본 10분 대기)     실시간 통합(consolidation)
```

Cluster Autoscaler는 "어떤 노드 그룹을 얼마나 키울까"를 결정한다.
Karpenter는 "이 Pod를 실행하려면 어떤 EC2가 필요한가"를 직접 결정한다.

### 작동 원리

```
1. Pod가 Pending 상태 (노드 부족)
        ↓
2. Karpenter가 Pod의 resource request, node selector, affinity를 분석
        ↓
3. NodePool에 정의된 조건 내에서 최적 인스턴스 타입 선택
        (bin-packing: 가장 낭비 없는 크기 선택)
        ↓
4. EC2 Fleet API 직접 호출 → 인스턴스 생성
        ↓
5. 노드가 클러스터에 합류 → Pod 스케줄링
        ↓
6. (반대 방향) 노드가 비거나 저활용 상태가 되면 Pod를 다른 노드로 이동
        → 빈 노드 삭제 (consolidation)
```

### Spot 인터럽션 처리

Spot 인스턴스는 AWS가 회수할 때 2분 전에 경고를 보낸다.
Karpenter는 이 경고를 **SQS 큐 + EventBridge**로 받아서 미리 Pod를 안전하게 다른 노드로 이동시킨다.
이 때문에 인프라 설정 시 SQS 큐와 EventBridge 규칙이 필요하다.

### 핵심 리소스 2가지

```yaml
# NodePool: "어떤 종류의 노드를 만들 수 있나" (클러스터 수준 정책)
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
spec:
  template:
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot", "on-demand"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: default
  limits:
    cpu: 100          # 클러스터 전체 Karpenter 노드 CPU 상한
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 1m
```

```yaml
# EC2NodeClass: "AWS에서 어떻게 만드나" (AWS 특화 설정)
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: default
spec:
  amiSelectorTerms:
    - alias: al2023@latest
  role: devopsim-prod-karpenter-node   # 노드에 부여할 IAM 역할
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: devopsim-prod-cluster
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: devopsim-prod-cluster
```

NodePool은 "정책", EC2NodeClass는 "AWS 인프라 설정"이라고 구분하면 된다.
여러 NodePool이 하나의 EC2NodeClass를 공유할 수 있다.

---

## Karpenter 도입을 위해 해야 할 것들

### 전체 흐름

```
① Terraform: IAM 역할 2개 추가 (컨트롤러 + 노드)
② Terraform: SQS 큐 + EventBridge 규칙 생성
③ Terraform: 서브넷/보안그룹/클러스터 태그 추가
④ K8s: aws-auth ConfigMap에 Karpenter 노드 역할 추가
⑤ Helm: Karpenter 설치
⑥ K8s: NodePool + EC2NodeClass 리소스 생성
⑦ (선택) 기존 관리형 노드 그룹 축소
```

---

### ① IAM 역할 — Karpenter 컨트롤러 (IRSA)

Karpenter Pod(컨트롤 플레인에서 실행)가 EC2를 직접 조작하려면 IAM 역할이 필요하다.
기존 ebs-csi, alb-controller와 동일하게 **IRSA** 방식으로 연결한다.

**새로 만들 역할:** `devopsim-prod-karpenter-controller`

**Trust Policy:** OIDC 프로바이더 기반 (기존 IRSA와 동일 패턴)
```
조건: system:serviceaccount:kube-system:karpenter
```

**필요한 IAM 정책 5개:**

| 정책 이름 | 하는 일 |
|-----------|---------|
| KarpenterControllerNodeLifecyclePolicy | EC2 인스턴스 생성/종료/수정 |
| KarpenterControllerIAMIntegrationPolicy | IAM 역할·인스턴스 프로파일 조작 |
| KarpenterControllerEKSIntegrationPolicy | EKS 클러스터 조회 및 연동 |
| KarpenterControllerInterruptionPolicy | SQS 큐에서 인터럽션 메시지 수신 |
| KarpenterControllerResourceDiscoveryPolicy | 서브넷·보안그룹 태그 기반 조회 |

실제 정책 JSON은 공식 CloudFormation 템플릿에서 추출하거나 Terraform `aws_iam_policy_document`로 직접 작성한다.

---

### ② IAM 역할 — Karpenter 노드

Karpenter가 생성한 EC2 노드에 부여할 역할이다.
기존 `devopsim-prod-eks-node-role`을 재사용하거나 새로 만들 수 있다.

**신규 생성 권장:** `devopsim-prod-karpenter-node`

**필요한 정책:**

| 정책 | 이유 |
|------|------|
| AmazonEKSWorkerNodePolicy | EKS 워커 노드 기본 권한 |
| AmazonEKS_CNI_Policy | VPC CNI 플러그인 |
| AmazonEC2ContainerRegistryReadOnly | ECR 이미지 풀 |
| AmazonSSMManagedInstanceCore | (권장) SSM을 통한 노드 접속/디버깅 |

> **왜 기존 노드 역할과 분리하나?**
> 관리형 노드 그룹 역할과 Karpenter 노드 역할을 분리하면 나중에 권한 범위를 독립적으로 조정할 수 있다.
> 지금은 학습 목적이라 재사용해도 무방하지만, 실무에서는 분리가 일반적이다.

---

### ③ SQS 큐 + EventBridge 규칙

Spot 인터럽션, 스팟 리밸런싱, EC2 상태 변경 이벤트를 받기 위해 필요하다.

```hcl
# SQS 큐
resource "aws_sqs_queue" "karpenter" {
  name = "devopsim-prod-cluster"   # 클러스터 이름과 동일하게
  message_retention_seconds = 300
}

# EventBridge 규칙 (4가지 이벤트)
# - EC2 Spot Instance Interruption Warning
# - EC2 Rebalance Recommendation
# - EC2 Instance State-change Notification
# - EC2 Instance State-change (running → stopping/stopped/terminated)
```

---

### ④ 서브넷 · 보안그룹 · 클러스터 태그

EC2NodeClass가 태그 기반으로 서브넷과 보안그룹을 찾는다.
기존 Terraform의 VPC/EKS 모듈에 태그를 추가해야 한다.

```hcl
# 프라이빗 서브넷에 추가
"karpenter.sh/discovery" = "devopsim-prod-cluster"

# EKS 노드 보안그룹에 추가
"karpenter.sh/discovery" = "devopsim-prod-cluster"
```

---

### ⑤ aws-auth ConfigMap 업데이트

Karpenter가 생성한 노드가 클러스터에 합류하려면 해당 노드 역할을 신뢰해야 한다.

```yaml
# kubectl edit configmap aws-auth -n kube-system
mapRoles:
  # 기존 관리형 노드 그룹 항목 유지
  - rolearn: arn:aws:iam::893286712531:role/devopsim-prod-eks-node-role
    username: system:node:{{EC2PrivateDNSName}}
    groups: [system:bootstrappers, system:nodes]
  # Karpenter 노드 역할 추가
  - rolearn: arn:aws:iam::893286712531:role/devopsim-prod-karpenter-node
    username: system:node:{{EC2PrivateDNSName}}
    groups: [system:bootstrappers, system:nodes]
```

---

### ⑥ Karpenter Helm 설치

```bash
helm registry logout public.ecr.aws
helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter \
  --version "1.12.0" \
  --namespace kube-system \
  --set "settings.clusterName=devopsim-prod-cluster" \
  --set "settings.interruptionQueue=devopsim-prod-cluster" \
  --set "serviceAccount.annotations.eks\.amazonaws\.com/role-arn=<karpenter-controller-role-arn>" \
  --wait
```

---

### ⑦ 기존 관리형 노드 그룹과의 공존

Karpenter를 처음 도입할 때는 기존 관리형 노드 그룹을 **유지하면서 시작**한다.

```
관리형 노드 그룹 (유지)
  └─ Karpenter 자체 Pod (kube-system)
  └─ ALB Controller, EBS CSI Driver 등 시스템 컴포넌트

Karpenter 관리 노드 (신규)
  └─ 애플리케이션 워크로드 (api 등)
```

Karpenter가 안정화되면 관리형 노드 그룹을 min=1 (최소 1개 유지)로 줄이거나
시스템 Pod들도 Karpenter로 이전할 수 있다.

---

## 이 프로젝트에서 Terraform으로 추가해야 할 것 체크리스트

```
[ ] modules/eks/karpenter.tf 신규 생성
    [ ] aws_iam_role.karpenter_controller (IRSA trust policy)
    [ ] aws_iam_policy × 5 (컨트롤러 권한)
    [ ] aws_iam_role_policy_attachment × 5
    [ ] aws_iam_role.karpenter_node
    [ ] aws_iam_role_policy_attachment × 4 (노드 권한)
    [ ] aws_iam_instance_profile.karpenter_node

[ ] modules/eks/interruption.tf 신규 생성
    [ ] aws_sqs_queue.karpenter
    [ ] aws_sqs_queue_policy
    [ ] aws_cloudwatch_event_rule × 4 (EventBridge)
    [ ] aws_cloudwatch_event_target × 4

[ ] modules/vpc/main.tf 수정
    [ ] 프라이빗 서브넷 tags에 karpenter.sh/discovery 추가

[ ] modules/eks/main.tf 수정
    [ ] 클러스터 tags에 karpenter.sh/discovery 추가
    [ ] 노드 보안그룹 tags에 karpenter.sh/discovery 추가

[ ] infra/helm/ 또는 infra/flux/
    [ ] Karpenter HelmRelease 추가 (Flux로 관리)
    [ ] NodePool 매니페스트
    [ ] EC2NodeClass 매니페스트
```

---

## 학습 Q&A — 작업 중 헷갈렸던 부분

### Q1. aws-auth는 어디 있나?

EKS 클러스터 안의 **Kubernetes ConfigMap**이다. 로컬 파일이나 Terraform 코드가 아니라 `kube-system` 네임스페이스에 살아있는 K8s 오브젝트.

```bash
kubectl get configmap aws-auth -n kube-system -o yaml
```

**역할:** IAM 역할 ARN → K8s RBAC 그룹 매핑 테이블.

새 EC2가 클러스터에 합류할 때 EKS는 그 EC2의 IAM 역할을 aws-auth에서 찾는다. 등록 안 되어 있으면 노드 합류 거부.

```yaml
mapRoles:
  - rolearn: ...devopsim-prod-eks-node-role
    groups: [system:nodes]      # 이 역할 가진 EC2는 워커 노드로 인정
    username: system:node:{{EC2PrivateDNSName}}
```

이 프로젝트에서는 `kubectl edit configmap aws-auth -n kube-system`으로 직접 수정한다 (Terraform으로 관리 안 함).

---

### Q2. "aws-auth에 별도로 등록하기 위해 분리"가 무슨 뜻?

Karpenter가 만든 EC2가 클러스터에 합류하려면 그 EC2의 IAM 역할이 aws-auth에 등록되어 있어야 한다.

```
관리형 노드 그룹 EC2  →  eks-node-role        →  aws-auth에 이미 있음
Karpenter EC2        →  karpenter-node-role  →  aws-auth에 새로 등록 필요
```

**분리하는 이유:**
1. 역할이 다르면 CloudTrail에서 어떤 노드의 행동인지 구분 가능
2. 두 노드 타입에 다른 권한이 필요해질 때 독립적으로 수정 가능
   (예: Karpenter 노드 앱만 S3 접근 필요해지면 karpenter-node-role에만 추가)
3. 기존 노드 그룹 역할을 재사용하면 aws-auth 수정 불필요하지만, 권한 분리가 안 됨

---

### Q3. karpenter_node 정책이 기존 노드 역할 정책과 같은데, 이관인가?

이관 아님. **두 역할이 동시에 존재**한다.

```
기존 관리형 노드 그룹            Karpenter 노드 (신규)
─────────────────────           ─────────────────────
eks-node-role        →         karpenter-node-role
  AmazonEKSWorkerNodePolicy      AmazonEKSWorkerNodePolicy
  AmazonEKS_CNI_Policy           AmazonEKS_CNI_Policy
  AmazonEC2ContainerRegistryRO   AmazonEC2ContainerRegistryRO
                                 AmazonSSMManagedInstanceCore (추가)
```

이 3개는 EKS 워커 노드라면 종류 상관없이 **필수**이기 때문에 겹친다. 복사가 아니라 동일한 요구사항을 가진 새 역할을 만든 것.

---

### Q4. 두 종류 노드가 공존한다는 게 정확히 어떤 구조?

K8s 스케줄러 입장에서 두 노드는 **그냥 똑같은 노드**다. 자동으로 분리되지 않는다. taint/toleration으로 명시적 분리해야 한다.

**전형적인 운영 패턴:**

```
관리형 노드 그룹 (taint 없음, 항상 존재)
  └─ Karpenter 컨트롤러 Pod          ← 이게 죽으면 노드 못 만듦 (닭/달걀 문제)
  └─ kube-system 시스템 Pod
  └─ ALB Controller, EBS CSI 등

Karpenter NodePool (taint: karpenter=NoSchedule)
  └─ toleration 있는 앱 Pod만 올라옴
  └─ api, worker 등 애플리케이션
```

**Karpenter 동작 원리:**
- 기존 노드에 자리 있으면 Karpenter는 아무것도 안 함
- Pod가 Pending 상태가 되어야 그때 새 EC2 생성
- 노드가 비거나 저활용되면 자동 정리(consolidation)

---

### Q5. NodePool, EC2NodeClass — CRD가 뭔가?

K8s에는 처음부터 정해진 `kind`들이 있다 (Pod, Deployment, Service 등).

**CRD (Custom Resource Definition)** = "K8s야, `NodePool`이라는 새 kind 추가할게" 하고 선언하는 오브젝트.

```bash
# Karpenter 설치 전
kubectl apply -f nodepool.yaml
→ error: no matches for kind "NodePool"

# Karpenter Helm 설치 후 (CRD가 클러스터에 등록됨)
kubectl apply -f nodepool.yaml
→ nodepool.karpenter.sh/default created
```

**용어 구분:**
- CRD = 새로운 kind의 설계도
- Custom Resource (CR) = 그 kind로 만든 실제 오브젝트

```bash
kubectl get crd          # 등록된 kind 목록
kubectl get nodepool     # NodePool 오브젝트 목록 (CR)
```

---

### Q6. NodePool은 카펜터가 만든 노드들의 묶음인가?

아니다. NodePool도 EC2NodeClass도 둘 다 **규칙서**다.

```
NodePool      = "어떤 조건의 노드를 만들 수 있나" 정책서
                - CPU/메모리 상한
                - spot 허용 여부
                - 아키텍처 (arm64/amd64)
                - consolidation 정책

EC2NodeClass  = "AWS에서 실제로 어떻게 만드나" 기술 명세서
                - 어떤 AMI
                - 어떤 서브넷/보안그룹
                - 어떤 IAM 역할
```

**관리형 노드 그룹 vs NodePool 차이:**

```
관리형 노드 그룹: "t3.medium 노드를 2개 유지해"  → 항상 노드 2개 존재
NodePool:       "이 조건 안에서 만들어도 돼"   → 노드가 0개일 수도 있음
                                                  Pod Pending 발생 시에만 생성
```

실제 노드는 그냥 K8s `Node` 오브젝트. `kubectl get nodes`에 일반 노드로 나옴. 구분은 label로:

```bash
kubectl get nodes -L karpenter.sh/nodepool
```

---

### Q7. consolidation, do-not-disrupt, PDB는 뭔가?

전부 **Karpenter가 노드를 지우려 할 때**의 동작 제어.

**Consolidation:**
Karpenter가 낭비되는 노드를 자동으로 정리. NodePool에서 설정.

```yaml
disruption:
  consolidationPolicy: WhenEmptyOrUnderutilized
  consolidateAfter: 1m
```

**do-not-disrupt** (Pod 단위 거부권):
Pod에 annotation 붙이면 그 Pod가 있는 노드는 consolidation 제외.

```yaml
metadata:
  annotations:
    karpenter.sh/do-not-disrupt: "true"
```

배치 작업처럼 중간에 끊기면 안 되는 작업에 사용.

**PodDisruptionBudget (서비스 연속성 보장):**
K8s 기본 기능. drain 시 동시에 내려가는 Pod 수를 제한.

```yaml
spec:
  minAvailable: 1   # 최소 1개는 항상 Running
```

```
do-not-disrupt = "이 작업 끝날 때까지 노드 절대 못 건드려"
PDB           = "건드려도 되는데, 한 번에 다 내리지는 마"
```

---

### Q8. 서브넷/보안그룹 태그는 어디서 활용되나?

EC2NodeClass가 **태그로 서브넷과 보안그룹을 찾는다.** 코드에 ID를 박는 게 아니라 태그 매칭으로 동적 탐색.

```yaml
# EC2NodeClass
subnetSelectorTerms:
  - tags:
      karpenter.sh/discovery: devopsim-prod-cluster
securityGroupSelectorTerms:
  - tags:
      karpenter.sh/discovery: devopsim-prod-cluster
```

이 프로젝트는 이미 비슷한 패턴을 쓰고 있다:
- Public 서브넷에 `kubernetes.io/role/elb=1` → ALB Controller가 인터넷 facing ALB 붙일 곳 찾을 때
- Private 서브넷에 `kubernetes.io/role/internal-elb=1` → Internal ALB용

**현재 구성에 추가 필요:**
- Private 서브넷에 `karpenter.sh/discovery=devopsim-prod-cluster`
- 노드 보안그룹에 `karpenter.sh/discovery=devopsim-prod-cluster`

---

### Q9. IRSA의 `Principal.Federated`가 뭔가?

Pod마다 다른 IAM 역할을 부여하기 위한 신뢰 체계.

**Principal 종류:**
```
Principal.Service   = "ec2.amazonaws.com"   → AWS 서비스가 직접 assume
Principal.AWS       = "arn:aws:iam::..."    → 다른 IAM 엔티티가 assume
Principal.Federated = "OIDC 프로바이더 ARN"  → 외부 IdP가 검증한 주체가 assume
```

`Federated`는 **외부 신뢰 기관(OIDC 프로바이더)이 발급한 토큰을 가진 주체**가 이 역할을 요청할 수 있다는 선언.

**IRSA 인증 흐름:**

```
① Pod 기동 → K8s가 ServiceAccount 토큰 자동 발급
   {
     "sub": "system:serviceaccount:kube-system:karpenter",
     "iss": "https://oidc.eks.us-east-2.amazonaws.com/id/XXXX"
   }
② Pod가 AWS STS에 AssumeRoleWithWebIdentity 요청 (토큰 첨부)
③ STS가 Trust Policy 검증
   - Federated = OIDC 프로바이더? ✓
   - Condition.sub = 정확한 ServiceAccount? ✓
   - Condition.aud = sts.amazonaws.com? ✓
④ 임시 자격증명(AccessKeyId + SecretAccessKey + SessionToken) 발급
⑤ Pod가 그 자격증명으로 AWS API 호출
```

Condition이 없으면 클러스터 안 아무 Pod나 역할 assume 가능. 그래서 `sub`로 정확히 어떤 ServiceAccount인지 좁혀야 함.

---

### Q10. `aws_iam_instance_profile`은 무슨 리소스?

IAM Role과 EC2를 이어주는 **어댑터**. IAM Role은 EC2에 직접 붙일 수 없고, 인스턴스 프로파일이라는 래퍼가 필요하다.

```
IAM Role (권한 정의)
    ↑
    └─ 담겨있음
    ↓
Instance Profile (래퍼/어댑터)
    ↑
    └─ 부착 가능
    ↓
EC2 Instance
```

**왜 분리되어 있나:**
IAM Role은 원래 "누군가 Assume"하는 모델로 설계됐는데, EC2는 부팅 시점에 스스로 Assume할 주체가 없다. AWS는 이 문제를 풀기 위해 **인스턴스 프로파일에 Role을 담아 EC2에 부착하는** 방식을 만들었다.

```
EC2 부팅
  → 인스턴스 메타데이터 서비스(169.254.169.254)
  → 부착된 인스턴스 프로파일 안의 Role을 자동 Assume
  → 임시 자격증명을 EC2 안에서 사용 가능
```

**관리형 노드 그룹은 왜 직접 안 만들었나:**
기존 `eks-node-role`에 대한 인스턴스 프로파일은 **EKS가 자동 생성**한다. `aws_eks_node_group`에 `node_role_arn`만 넘기면 EKS가 알아서 인스턴스 프로파일 만들어서 ASG에 연결.

반면 Karpenter는 EKS 외부에서 EC2를 직접 만들기 때문에, EKS의 자동 생성을 활용할 수 없다. 우리가 직접 만들어서 EC2NodeClass에 알려줘야 한다.

**흐름:**
```
① Terraform
   aws_iam_role.karpenter_node              역할 (정책 부여)
   aws_iam_instance_profile.karpenter_node  래퍼 (역할을 담음)

② EC2NodeClass에 인스턴스 프로파일 이름 지정
   spec:
     instanceProfile: devopsim-prod-karpenter-node-profile

③ Karpenter가 RunInstances 호출 시 IamInstanceProfile 파라미터로 부착
   → EC2 부팅하면서 Role 권한 자동 획득
   → 노드가 EKS 클러스터에 합류
```

---

### Q11. 임시 자격증명 vs IAM 역할 — 어느 쪽으로 API 호출?

둘은 **같은 것**. "역할을 Assume한다" = "그 역할의 권한을 담은 임시 자격증명을 발급받는다"

```
IAM Role     = 권한 목록이 적힌 문서 (그 자체로는 아무것도 못 함)
임시 자격증명 = 그 문서를 기반으로 발급된 단기 신분증

Assume       = 신분증 발급받기
API 호출     = 신분증 제시 → AWS가 역할의 정책 확인 후 허용/거부
```

STS가 돌려주는 임시 자격증명:

```json
{
  "AccessKeyId":     "ASIA...",
  "SecretAccessKey": "xxxx",
  "SessionToken":    "yyyy",
  "Expiration":      "1시간 후"
}
```

EC2도 IAM Role도 결국 호출 시점엔 모두 임시 자격증명으로 변환되어 사용된다. AWS는 항상 자격증명만 받고, 그게 어떤 역할 기반인지 추적해서 권한 체크.

---

### Q12. 프라이빗 서브넷 두 개 모두 태그 달면 AZ 자동 분배되나?

**자동 분배 안 한다.** 두 서브넷에 태그 달면 "둘 중 어디든 만들 수 있다"는 허용 범위만 정해진다. Karpenter 기본 동작은 비용 최적화 우선:

```
Pod 5개 Pending
  → Karpenter가 "가장 좋은 AZ 한 곳" 선택 (Spot 가격, capacity 등)
  → 한 AZ에 큰 EC2 1대 만들어서 거기 다 몰아넣음
  → 그 AZ 장애 시 전부 다운
```

AZ 분산은 **명시적으로 시켜야** 한다. 두 가지 방법:

**Pod 수준 — topologySpreadConstraints (강제):**
```yaml
spec:
  template:
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api
```

**NodePool 수준 — 허용 AZ 명시 (제약):**
```yaml
spec:
  template:
    spec:
      requirements:
        - key: topology.kubernetes.io/zone
          operator: In
          values: ["us-east-2a", "us-east-2b"]
```

NodePool은 "이 AZ들에서 만들어도 됨"이고, 실제 분배 강제는 Pod 쪽 topology spread로 한다.

---

### Q13. NodePool/EC2NodeClass는 Flux로 Helm 설치 시 자동 생성?

**아니다.** Helm 설치 시 자동 생성되는 건 **CRD(스키마)** 뿐이다. CRD를 사용하는 **Custom Resource(실제 오브젝트)** 는 별도로 작성해야 한다.

```
Karpenter HelmRelease 적용
  → CRD 등록됨 (NodePool, EC2NodeClass kind 사용 가능)
  → 컨트롤러 Pod 실행

NodePool / EC2NodeClass 매니페스트
  → 우리가 직접 YAML 작성
  → Flux가 Kustomization으로 적용
  → Karpenter가 그걸 보고 "어떤 노드 만들 수 있는지" 인지
```

**의존성 순서:**
1. Karpenter HelmRelease → CRD 등록
2. NodePool/EC2NodeClass 매니페스트 → CRD 사용
3. api Deployment에 topologySpreadConstraints 추가

CRD 등록 전에 NodePool 적용 시도하면 실패한다.

---

### Q14. Karpenter HelmRelease에 어떤 values 넣어야 하나?

핵심 5개:

| values | 값 | 이유 |
|--------|------|------|
| `serviceAccount.annotations[eks.amazonaws.com/role-arn]` | 컨트롤러 IRSA Role ARN | Pod가 AWS API 호출 |
| `settings.clusterName` | 클러스터 이름 | 어떤 클러스터의 노드 관리할지 |
| `settings.interruptionQueue` | SQS 큐 이름 (= 클러스터 이름) | 인터럽션 이벤트 수신 |
| `nodeSelector` | 관리형 노드 그룹 라벨 | **자기가 만든 노드에 자기가 뜨면 닭/달걀 문제** |
| `replicas` | 1 (또는 HA 시 2) | 환경 규모에 맞게 |

**ServiceAccount 이름은 IRSA Trust Policy와 일치해야 함:**
```
Trust Policy: "system:serviceaccount:kube-system:karpenter"
Helm 차트 기본값: namespace=kube-system, sa=karpenter
→ 일치하므로 따로 안 바꿔도 됨
```

**nodeSelector로 관리형 노드에 고정하는 이유:**
Karpenter가 자기가 만든 노드에 떠있다가 그 노드가 consolidation으로 삭제되면 Karpenter가 같이 죽는다. 새 노드를 만들 주체가 사라지므로 복구 불가능. 그래서 항상 관리형 노드 그룹에 고정.

---

### Q15. OCIRepository와 HelmRelease 관계 — 누가 폴링?

**폴링은 OCIRepository(Source Controller)가 한다. HelmRelease는 watch만 한다.**

```
[Source Controller]
  OCIRepository "karpenter"
    └─ public.ecr.aws/karpenter/karpenter:1.12.0
       1시간마다 폴링 → 새 차트 있으면 다운로드 → 캐싱
                ↓ (차트 변경 알림)
[Helm Controller]
  HelmRelease "karpenter"
    └─ chartRef: OCIRepository "karpenter"
       OCIRepository를 watch
       차트 변경 또는 values 변경 시 helm upgrade
```

**프로젝트 내 두 패턴 비교:**

```
[기존 api, db]
  GitRepository (우리 git repo)
        │ (git pull)
        ↓
  HelmRelease (chart 경로: ./infra/helm/api)

[신규 karpenter]
  OCIRepository (public.ecr.aws/...)
        │ (OCI pull)
        ↓
  HelmRelease (chartRef: OCIRepository)
```

차트 위치만 다르고 동작 원리는 같다. HelmRelease 입장에서는 둘 다 "Source Controller가 차트 가져다놓은 곳"으로만 본다.

---

### Q16. 두 노드 관리 시스템은 어디서 각각 관리되나?

관리형 노드 그룹과 Karpenter는 **완전히 분리된 평행 시스템**이다.

```
┌─────────────────────────────────────────────────────────────┐
│ 관리형 노드 그룹 (EKS 네이티브)                              │
│   관리 도구:    Terraform                                    │
│   리소스 타입:  aws_eks_node_group                          │
│   파일 위치:    infra/terraform/modules/eks/main.tf         │
│   특징:         항상 떠있음, 변경은 terraform apply         │
└─────────────────────────────────────────────────────────────┘
                       ↑
                       │  서로 다른 시스템
                       ↓
┌─────────────────────────────────────────────────────────────┐
│ Karpenter 노드 (CRD)                                         │
│   관리 도구:    Flux (Kubernetes CRD)                        │
│   리소스 타입:  NodePool + EC2NodeClass                     │
│   파일 위치:    infra/flux/clusters/prod/apps/              │
│                   karpenter-nodepool.yaml                   │
│   특징:         Pod 수요에 따라 0~N개 동적                  │
│                 변경은 kubectl apply (Flux 자동 감지)       │
└─────────────────────────────────────────────────────────────┘
```

K8s 스케줄러 입장에서 두 종류 노드는 똑같다. 자동 분리 안 되며, 기본 설정으로는 빈자리에 배치됨.

---

### Q17. taint/toleration 패턴 — A vs B 차이와 베스트 프랙티스

```
[A 패턴] Karpenter 노드에 taint
  기본 동작:    모든 Pod는 관리형 노드에 가려고 함
  Karpenter 사용: toleration 명시한 Pod만
  → "Karpenter 사용은 opt-in"

[B 패턴] 관리형 노드에 taint
  기본 동작:    모든 Pod는 Karpenter 노드에 가려고 함
  관리형 사용:  CriticalAddonsOnly toleration 가진 시스템 Pod만
  → "관리형 사용은 opt-in"
```

**실무 표준은 B + 다중 NodePool:**

```
관리형 노드 그룹 (taint: CriticalAddonsOnly, 작게 유지)
  └─ 시스템 컴포넌트 + Karpenter 컨트롤러

Karpenter NodePool들:
  ├─ default    taint 없음           일반 앱
  ├─ spot       taint: spot=true     비용 절감 가능 워크로드
  └─ gpu        taint: gpu=true      ML 학습/추론
```

**왜 B가 표준:**
- Karpenter의 가치 = 자동 스케일 + 비용 최적화 → 최대한 많은 워크로드가 혜택 받아야 함
- 시스템 DaemonSet은 보통 CriticalAddonsOnly toleration 기본 제공
- 관리형 노드는 "최소 안전 장치 + 닭/달걀 해결"용으로만

이 프로젝트는 B 패턴 채택 (`infra/terraform/modules/eks/main.tf`).

---

### Q18. Terraform에서 K8s taint를 어떻게 추가하나? Taint는 K8s 기능 아닌가?

Taint는 K8s 개념이 맞지만, EKS Managed Node Group은 **노드 생성 시 자동으로 taint를 붙여주는 기능**을 제공한다. Terraform이 그 API를 노출.

```hcl
resource "aws_eks_node_group" "this" {
  # ...
  taint {
    key    = "CriticalAddonsOnly"
    value  = "true"
    effect = "NO_SCHEDULE"
  }
}
```

**동작:**
```
terraform apply
    ↓
EKS API에 "이 노드 그룹은 이 taint 가지고 시작" 등록
    ↓
EKS가 노드 그룹 launch template 업데이트
    ↓
노드 부팅 시 kubelet이 taint 가지고 클러스터 합류
    ↓
kubectl describe node에 spec.taints로 보임
```

**표기 차이:**
- EKS API / Terraform: `NO_SCHEDULE` (대문자 + 언더스코어)
- K8s Node 객체: `NoSchedule` (PascalCase)

EKS가 자동 변환. 매번 `kubectl taint` 수동 실행할 필요 없이 IaC로 관리 가능.

---

### Q19. NodePool `limits`가 무슨 뜻? 도달하면 노드 더 생기나?

**정반대다.** limits는 **상한 안전장치**이지 트리거가 아니다.

```yaml
limits:
  cpu: 32
  memory: 64Gi
```

- 단위: **NodePool 전체 합계** (노드 1개당 아님)
- 관리형 노드 그룹은 별개로 카운트 안 됨
- 도달 시 → Karpenter가 **노드 생성 멈춤** (Pod는 Pending 그대로)

**노드 생성 트리거 = Pending Pod 존재 (limits와 무관):**

```
Pod Pending 발생
    ↓
Karpenter가 NodePool 정책 + Pod 요구사항 분석
    ↓
limits 체크 → 초과 안 함 → 노드 생성
                초과     → 생성 안 함, Pod는 Pending 유지
```

**메모리 미지정 시:**
```yaml
limits:
  cpu: 32       # CPU만 지정 → 메모리는 무제한
```

실무에선 보통 CPU만 제한. 학습/카오스 환경에는 둘 다 지정해 비용 폭주 방지.

---

### Q20. PDB는 어디에 설정?

별도 K8s 리소스로, Deployment와 같은 네임스페이스에 두고 selector로 보호 대상 Pod를 지정.

이 프로젝트에선 api Helm 차트에 추가:
```
infra/helm/api/templates/poddisruptionbudget.yaml
```

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ include "api.fullname" . }}
spec:
  minAvailable: 1
  selector:
    matchLabels:
      {{- include "api.selectorLabels" . | nindent 6 }}
```

**Deployment와 직접 연결되지 않음 — label로만 연결.** Service와 동일한 selector를 쓰면 같은 Pod 그룹을 보호.

```bash
kubectl get pdb -n default
# NAME   MIN AVAILABLE   ALLOWED DISRUPTIONS
# api    1               1
```

`ALLOWED DISRUPTIONS`이 핵심 — "지금 안전하게 내려도 되는 Pod 수".

---

### Q21. topologySpreadConstraints는 어디에 설정?

Pod 스펙 안에 들어간다. 우리 프로젝트에선 Helm 차트:

```
infra/helm/api/templates/deployment.yaml
  spec.template.spec.topologySpreadConstraints
```

**기본 구조:**
```yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: ScheduleAnyway
    labelSelector:
      matchLabels:
        app.kubernetes.io/name: api
```

**4개 핵심 파라미터:**
| 파라미터 | 의미 |
|----------|------|
| `topologyKey` | 어떤 단위로 분산할지 (`zone`, `hostname`, `region`) |
| `maxSkew` | 허용되는 최대 차이 (1=엄격, 2=관대) |
| `whenUnsatisfiable` | 위반 시 동작 |
| `labelSelector` | 어떤 Pod끼리 비교할지 |

---

### Q22. `whenUnsatisfiable` 값 종류와 차이

세 가지 옵션이 있다 (실제로는 두 가지가 흔히 쓰임):

```
DoNotSchedule    조건 못 맞추면 Pod Pending → 못 띄움
                 가용성 강력 보장
                 단점: 다른 AZ 노드 없으면 Pending 그대로
                       → Karpenter가 다른 AZ 노드 생성 트리거
                 적합: 프로덕션, 완벽한 분산 필요

ScheduleAnyway   선호하지만 어겨도 됨 (best effort)
                 위반해도 Pod는 띄움 (한쪽으로 쏠릴 수 있음)
                 적합: 시작 단계, Pending 위험 회피
```

`ScheduleAnyway`로 시작 → 운영 안정화 후 `DoNotSchedule`로 승격이 안전한 패턴.

---

### Q23. Karpenter와 topologySpreadConstraints의 시너지

```
DoNotSchedule + Karpenter

Pod 5개 Pending, 모든 후보 노드는 us-east-2a에만 있음
        ↓
스케줄러: "DoNotSchedule인데 한 AZ에 다 못 보냄"
        → 일부 Pod는 Pending 유지
        ↓
Karpenter: Pending 분석
        "이 Pod는 us-east-2b가 필요하다"
        → us-east-2b에 새 노드 생성
        ↓
스케줄러가 새 노드에 Pod 배치 → 분산 완성
```

`topologySpreadConstraints`는 **Karpenter에게 "어디에 노드 만들어야 하는지" 힌트를 주는 효과**도 있음. 비용 최적화(같은 AZ 몰아넣기)와 가용성(분산) 사이의 균형을 명시.

---

### Q24. 우리 프로젝트에서 PDB가 의미 있나?

대부분 워크로드는 자체 HA를 가지고 있어서 PDB가 크게 필요 없다:
- kube-system: EKS Add-on이 자체 PDB 내장
- Karpenter / Flux: Helm 차트가 자체 PDB 또는 topologySpread 내장
- db: 별도 RDS로 이전 예정

**PDB가 필요한 곳 = api.**

특히 taint를 추가하는 순간이 위험:
```
[Before]
관리형 노드 2대에 api Pod × N (toleration 없음)

[After taint apply]
api Pod 모두 동시에 evicted
  → PDB 없으면 한꺼번에 다 내려감 → 순단
  → PDB 있으면 1개씩 안전하게 내려감
```

학습 단계에서는 PDB 없이 일부러 진행해 disruption 관찰 → 추가하며 차이 비교가 가치 있음.

---

## 참고

- 공식 시작 가이드: https://karpenter.sh/docs/getting-started/getting-started-with-karpenter/
- NodePool 레퍼런스: https://karpenter.sh/docs/concepts/nodepools/
- EC2NodeClass 레퍼런스: https://karpenter.sh/docs/concepts/nodeclasses/
- Karpenter v1.12.0 (2026-04-25 기준 최신)
