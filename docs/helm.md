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

## production에서 DB 분리

로컬은 StatefulSet, production은 RDS를 쓰는 구조:

```yaml
# values.yaml
db:
  enabled: true
  host: db
  port: 5432

# values-production.yaml
db:
  enabled: false
  host: mydb.xxxx.rds.amazonaws.com
  port: 5432
```

```yaml
# templates/db-statefulset.yaml
{{- if .Values.db.enabled }}
apiVersion: apps/v1
kind: StatefulSet
...
{{- end }}
```

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
