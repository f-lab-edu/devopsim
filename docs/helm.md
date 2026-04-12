# Helm 학습 기록

## Helm이란

K8s용 패키지 매니저. `kubectl apply`의 상위 레이어로, 템플릿 렌더링 + 배포 이력 관리를 담당한다.

```
templates/ + values.yaml
    ↓ helm 렌더링
완성된 K8s YAML
    ↓ kubectl apply (helm 내부 실행)
클러스터 배포
```

---

## Kustomize와의 차이

| | Kustomize | Helm |
|---|---|---|
| 방식 | 파일 단위 오버라이드 | 값 단위 오버라이드 |
| 환경 분리 | overlays/ 디렉토리 | values-{env}.yaml |
| 배포 이력 | 없음 | K8s Secret에 자동 저장 |
| 롤백 | 없음 (git으로 관리) | `helm rollback` |
| 복잡한 조건문 | 어려움 | `if`, `range` 가능 |
| 학습 난이도 | 낮음 | 높음 |

Kustomize는 K8s 오브젝트를 "있는 그대로" 다루고, Helm은 템플릿 엔진을 통해 생성한다.

---

## 배포 이력 관리

Helm은 배포할 때마다 K8s Secret에 전체 매니페스트를 저장한다.

```bash
kubectl get secrets | grep helm
# sh.helm.release.v1.api.v1
# sh.helm.release.v1.api.v2
# sh.helm.release.v1.api.v3

helm history api
# REVISION  STATUS    CHART      APP VERSION
# 1         deployed  api-0.1.0  0.0.1
# 2         deployed  api-0.1.0  0.0.2
# 3         failed    api-0.1.0  0.0.3

helm rollback api 2  # REVISION 번호로 롤백
```

`Chart.yaml`의 `version`/`appVersion`은 표시용이고, 롤백 대상 지정은 REVISION 번호를 쓴다.

---

## Chart 구조 (단일 앱 기준)

```
infra/helm/api/
  Chart.yaml          ← 메타정보 (name, version, appVersion)
  values.yaml         ← 기본값
  values-local.yaml   ← 로컬 오버라이드
  values-production.yaml
  templates/
    _helpers.tpl      ← 공통 함수 (레이블, 이름 생성)
    deployment.yaml
    service.yaml
    ingress.yaml
    NOTES.txt         ← helm install 후 출력되는 안내 메시지
  charts/             ← 의존 Chart (redis, postgresql 등)
  .helmignore
```

---

## 멀티 앱 구조

앱별로 Chart를 분리한다. 하나의 Chart 안에 환경별 Chart를 만들지 않는다.

```
infra/helm/
  api/        ← helm install api ./infra/helm/api
  detector/   ← helm install detector ./infra/helm/detector
  dashboard/  ← helm install dashboard ./infra/helm/dashboard
```

같은 클러스터에서 앱별 독립 배포/롤백이 가능하다.

---

## 환경별 분리 패턴

Chart는 하나, values 파일로 환경 분리.

```bash
# 로컬
helm install api ./infra/helm/api -f values-local.yaml

# 프로덕션
helm upgrade api ./infra/helm/api -f values-production.yaml
```

리소스 on/off도 values로 제어:

```yaml
# values.yaml
waitForDb:
  enabled: true   # 로컬: DB StatefulSet 기다림

# values-production.yaml
waitForDb:
  enabled: false  # production: RDS는 항상 떠있으니 불필요
```

```yaml
# templates/deployment.yaml
{{- if .Values.waitForDb.enabled }}
initContainers:
  - name: wait-for-db
    ...
{{- end }}
```

---

## _helpers.tpl 핵심 함수

```
api.name         → Chart 이름 (nameOverride 없으면 Chart.yaml의 name)
api.fullname     → release-name + chart-name 조합 (최대 63자)
api.labels       → 공통 레이블 (helm.sh/chart, app.kubernetes.io/*)
api.selectorLabels → selector용 레이블 (name + instance)
```

템플릿에서 반복 작성 없이 재사용:

```yaml
metadata:
  labels:
    {{- include "api.labels" . | nindent 4 }}
spec:
  selector:
    matchLabels:
      {{- include "api.selectorLabels" . | nindent 6 }}
```

`nindent N` — N칸 들여쓰기 + 앞에 줄바꿈 추가. YAML 구조에 맞게 위치별로 숫자를 맞춰야 한다.

---

## resources 주석 처리 관례

```yaml
resources: {}
# requests/limits는 환경마다 달라서 기본값을 비워둠
# production values에서 명시적으로 설정
```

기본값을 설정하면 모든 환경에 강제 적용된다. 로컬 minikube에서 리소스 제한이 걸리면 Pending이 날 수 있어서 비워두는 게 표준이다.

---

## 렌더링 확인 명령어

```bash
# 로컬 렌더링 (클러스터 불필요)
helm template api infra/helm/api

# 특정 템플릿만
helm template api infra/helm/api -s templates/deployment.yaml

# values 오버라이드
helm template api infra/helm/api -f values-local.yaml

# K8s API 서버 유효성 검사 포함 (클러스터 필요)
helm install api infra/helm/api --dry-run=server
```

`helm template`은 YAML 문법만 확인, `--dry-run=server`는 K8s가 실제로 받아들일 수 있는지까지 확인한다.

---

## Service와 Ingress

### Service (네트워크 오브젝트)

Service는 워크로드가 아닌 네트워크 오브젝트다. 특정 노드가 아닌 **클러스터 레벨**에 존재한다.

```
ClusterIP (고정 가상 IP)
    ↓ kube-proxy가 라우팅
Pod (containerPort: 3000)
```

- Pod IP는 재시작마다 바뀌지만 Service ClusterIP는 고정
- `port: 80 → targetPort: 3000` 포워딩
- CoreDNS가 Service 이름(`db`, `api`)을 ClusterIP로 해석

### Ingress (네트워크 오브젝트)

Ingress도 클러스터 레벨 오브젝트다. 실제 트래픽은 **Ingress Controller Pod**가 처리한다.

```
외부 요청
    ↓
Ingress Controller Pod (노드에 존재)  ← Ingress 규칙 읽어서 라우팅
    ↓
Service (ClusterIP)
    ↓
api Pod
```

### 로컬 vs AWS 구조 차이

| | minikube (로컬) | AWS EKS |
|---|---|---|
| Controller | nginx Pod (노드에 존재) | AWS ALB (노드 밖 AWS 인프라) |
| 노드 장애 시 | 통신 불가 (단일 노드) | 다른 노드로 계속 서비스 |
| 외부 접근 | minikube tunnel → 127.0.0.1 | ALB DNS 주소 |

로컬에서 노드가 죽으면 nginx Controller Pod도 같이 죽어서 통신 불가. 멀티 노드 HA는 EKS에서만 의미 있다.

### Ingress host 설정

```yaml
host: ""           # 모든 IP/도메인으로 들어오는 요청 처리
                   # minikube tunnel 시 127.0.0.1로 접근 가능

host: "api.devopsim.com"  # 해당 도메인으로만 처리
                           # Route53 도메인 구매 + ALB DNS 연결 필요
```

### nginx → ALB 전환 시 변경 사항

템플릿은 그대로, values만 바꾼다:

```yaml
# values-production.yaml
ingress:
  enabled: true
  className: alb                         # nginx → alb
  host: api.devopsim.com
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
```

ALB Controller가 이 Ingress를 읽고 AWS ALB를 자동 생성한다.

### Ingress enabled 패턴

```yaml
# values.yaml
ingress:
  enabled: false   # 기본 비활성

# templates/ingress.yaml
{{- if .Values.ingress.enabled }}
...
{{- end }}
```

`enabled: false`면 Ingress 오브젝트 자체가 렌더링되지 않는다.

```bash
# Ingress 포함해서 확인
helm template api infra/helm/api --set ingress.enabled=true
helm install api infra/helm/api --dry-run=server --set ingress.enabled=true
```

---

## DB 마이그레이션 전략

### 방법별 비교

| 방법 | 실행 시점 | 문제점 |
|---|---|---|
| initContainer | api Pod 뜰 때마다 | 스케일 아웃 시 레이스 컨디션 → DB lock 필요 |
| 앱 코드에서 실행 | 앱 시작 시 | 동일하게 레이스 컨디션 → DB lock 필요 |
| Helm Hook (Job) | helm install/upgrade 시 | 없음 (권장) |
| GitHub Actions | git push 시 | ArgoCD 환경에서 별도 클러스터 접근 권한 필요 |

2, 3번은 api Pod가 뜰 때마다 실행되어 스케일 아웃 시 여러 Pod가 동시에 migrate를 시도하는 레이스 컨디션이 발생한다.

### Helm Hook 선택 이유

```
helm upgrade api infra/helm/api
  → pre-upgrade Hook: migrate Job 자동 실행
  → DB에 직접 접근 (클러스터 내부)
  → Job 완료 확인
  → Deployment 롤링 업데이트
```

ArgoCD GitOps 환경에서 CI가 직접 클러스터에 접근하지 않아도 되고, `helm upgrade` 한 번으로 마이그레이션 + 배포가 자동화된다.

GitHub Actions 방식은 migrate 단계를 독립적으로 세밀하게 제어할 수 있지만, ArgoCD 환경에서는 클러스터 접근 권한을 별도로 줘야 해서 복잡해진다.

### Hook 어노테이션

```yaml
annotations:
  helm.sh/hook: pre-install,pre-upgrade       # install, upgrade 시 모두 실행
  helm.sh/hook-weight: "0"                    # 여러 hook 간 실행 순서 (낮을수록 먼저)
  helm.sh/hook-delete-policy: before-hook-creation  # 다음 실행 전 이전 Job 삭제
```

`hook-delete-policy: before-hook-creation` — 같은 이름의 Job이 이미 있으면 삭제 후 재생성. 이전 migrate Job이 남아있어도 `helm upgrade` 시 항상 새로 실행된다.

### node-pg-migrate idempotent 보장

node-pg-migrate가 DB 안에 `pgmigrations` 테이블을 자동으로 관리한다.

```sql
-- devopsim DB 안에 자동 생성 (StatefulSet PVC에 영속)
SELECT * FROM pgmigrations;
-- name                  | run_on
-- 001_create_items      | 2026-04-01
-- 002_add_tags          | 2026-04-10
```

```
node-pg-migrate up 실행
  → pgmigrations 테이블 조회
  → migrations/ 파일 목록과 비교
  → 테이블에 없는 파일만 실행
  → 이미 있는 파일은 스킵 (idempotent)
```

매번 실행해도 안전하다. Pod 재시작, helm upgrade 반복 실행 모두 안전.

### pre-install vs post-install hook — deadlock 주의

같은 Chart 안에 DB StatefulSet과 migrate Job이 함께 있을 때 `pre-install` hook을 쓰면 deadlock이 발생한다.

```
pre-install hook 실행 (다른 리소스보다 먼저)
  → migrate Job 생성
  → wait-for-db: db 기다림
  → 근데 db StatefulSet은 hook 완료 후 생성 예정
  → 영원히 대기 (deadlock)
```

**해결: `post-install,post-upgrade`로 변경**

```yaml
annotations:
  helm.sh/hook: post-install,post-upgrade  # 모든 리소스 배포 후 실행
```

```
db StatefulSet, api Deployment 배포
  → 완료 후 migrate Job 실행 (post-install)
  → wait-for-db: db ready 대기
  → migrate 실행
```

`pre-install`은 Chart 밖에 DB가 있을 때(RDS 등) 적합하다. 같은 Chart 안에 DB가 있으면 `post-install`을 써야 한다.

---

### Kustomize(K8s Job) vs Helm Hook 순서 보장 비교

**Kustomize 방식 (기존):**
```bash
kubectl apply -k overlays/local
  → db StatefulSet, api Deployment, migrate Job 동시 생성
  → 순서 보장 없음
  → migrate Job 안의 wait-for-db initContainer가 대기 역할
```

순서 보장을 Job 내부 로직(wait-for-db)으로 해결했다.

**Helm Hook 방식:**
```
helm upgrade
  → pre-upgrade: migrate Job 실행 + 완료 대기 (Helm이 보장)
  → 완료 후: StatefulSet, Deployment 배포
```

Helm이 순서를 명시적으로 보장한다. 단, `wait-for-db`는 여전히 필요하다. hook이 "배포 전"은 보장하지만 "db가 실제로 ready 상태"까지는 보장하지 않기 때문이다.

---

## Secret 관리

### 로컬 환경

Secret은 Helm Chart에 포함하지 않는다. `kubectl create secret`으로 직접 생성한다.

```bash
kubectl create secret generic postgres-secret \
  --from-literal=postgres-db=devopsim \
  --from-literal=postgres-user=devopsim \
  --from-literal=postgres-password=devopsim

kubectl create secret generic api-secret \
  --from-literal=database-url="postgresql://devopsim:devopsim@db:5432/devopsim"
```

### 운영 환경 Secret 관리 방법

| 방법 | 특징 |
|---|---|
| **External Secrets Operator** | AWS Secrets Manager 값을 K8s Secret으로 자동 동기화. ArgoCD GitOps와 궁합 좋음 |
| **Sealed Secrets** | Secret 암호화 후 Git 커밋 가능. 복호화는 클러스터만 가능 |
| **HashiCorp Vault** | 엔터프라이즈급 시크릿 관리 |
| **helm --set** | CI에서 `helm upgrade --set db.password=$SECRET` 방식 |

이 프로젝트는 week4 EKS 구성 시 **External Secrets Operator + AWS Secrets Manager**로 전환 예정.

```
AWS Secrets Manager
  └── devopsim/api: { database-url: "..." }
        ↓ External Secrets Operator
K8s Secret (자동 생성, Git에 없음)
        ↓
Pod
```

---

## ArgoCD + 모노레포 GitOps

모노레포에서 앱별 독립 자동 배포가 가능하다.

```yaml
# ApplicationSet으로 앱 목록만 추가하면 자동 생성
spec:
  generators:
    - list:
        elements:
          - app: api
          - app: detector
  template:
    spec:
      source:
        path: infra/helm/{{ app }}
      destination:
        namespace: {{ app }}
```

CI/CD 흐름:
```
코드 변경 → GitHub Actions
  → 이미지 빌드/푸시 (ECR)
  → infra/helm/api/values.yaml image.tag 업데이트
  → ArgoCD 변경 감지 → api만 자동 배포
```
