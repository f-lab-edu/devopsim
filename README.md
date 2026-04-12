# devopsim

API를 통해 장애를 주입하고, 메트릭 · 로그 · 트레이스로 이상을 감지하고, 알림 → 자동 복구까지 연결하는 DevOps 시뮬레이터.

## 시스템 흐름

```mermaid
flowchart TD
    dashboard["dashboard\n장애 주입 UI"]
    api["api\nFastify CRUD + /chaos/*"]
    prometheus["Prometheus\n메트릭 수집"]
    detector["detector\n이상 탐지 엔진"]
    alertmanager["Alertmanager\n알림 라우팅"]
    grafana["Grafana\n시각화"]
    loki["Loki\n로그 수집"]
    slack["Slack\n알림"]

    dashboard -->|"POST /chaos/inject"| api
    dashboard -->|"iframe embed"| grafana
    api -->|"/metrics scrape"| prometheus
    api -->|"구조화 로그"| loki
    prometheus --> detector
    prometheus --> grafana
    loki --> grafana
    detector -->|"이상 감지 alert"| alertmanager
    prometheus -->|"고정 임계치 alert"| alertmanager
    alertmanager --> slack
    alertmanager -->|"annotation"| grafana
```

## 앱 구성

```
packages/
  api/          Fastify CRUD API + 장애 주입 엔드포인트 + 메트릭 노출
  detector/     Prometheus 메트릭 쿼리 → 통계 기반 이상 탐지 → Alertmanager
  dashboard/    장애 주입 컨트롤 패널 + Grafana iframe
  shared/       공통 유틸리티 (logger, types)

infra/
  docker/       docker-compose 로컬 실행 환경
  k8s/          Kubernetes 매니페스트 (Kustomize)
  helm/         Helm Charts
    api/        api 앱 Chart
    db/         PostgreSQL Chart (독립 인프라)
  terraform/    AWS EKS 인프라 (IaC)

scenarios/      장애 시나리오 스크립트
docs/           설계 기록 및 측정 결과
```

---

## 로컬 실행 (docker-compose)

### 사전 조건

- Docker 실행 중

### 1. 환경 변수 파일 생성

```bash
cp infra/docker/.env.example infra/docker/.env
```

`.env` 내용:

```
POSTGRES_DB=devopsim
POSTGRES_USER=devopsim
POSTGRES_PASSWORD=devopsim
DATABASE_URL=postgresql://devopsim:devopsim@db:5432/devopsim
```

### 2. 실행

```bash
cd infra/docker
docker compose up -d --build
```

기동 순서: `db (healthy)` → `migrate (completed)` → `api`

### 3. 동작 확인

```bash
# 프로세스 생존 확인
curl http://localhost:3000/health

# DB 연결 상태 확인
curl http://localhost:3000/ready

# 아이템 생성
curl -X POST http://localhost:3000/api/items \
  -H "Content-Type: application/json" \
  -d '{"name": "test", "description": "hello"}'

# 목록 조회
curl http://localhost:3000/api/items
```

### 4. 종료

```bash
# 컨테이너만 종료 (볼륨 유지)
docker compose down

# 컨테이너 + 볼륨 전체 삭제
docker compose down -v
```

---

## 로컬 실행 (Helm + minikube)

### 사전 조건

- minikube 실행 중 (`minikube start`)
- Helm 설치 (`brew install helm`)

### 1. minikube에 이미지 빌드

```bash
eval $(minikube docker-env)
docker build -t devopsim-api:latest -f packages/api/Dockerfile .
eval $(minikube docker-env -u)
```

### 2. Secret 생성

```bash
kubectl create secret generic postgres-secret \
  --from-literal=postgres-db=devopsim \
  --from-literal=postgres-user=devopsim \
  --from-literal=postgres-password=devopsim

kubectl create secret generic api-secret \
  --from-literal=database-url="postgresql://devopsim:devopsim@db:5432/devopsim"
```

### 3. DB 먼저 배포

```bash
helm install db infra/helm/db
kubectl wait --for=condition=ready pod/db-0 --timeout=60s
```

### 4. API 배포

```bash
helm install api infra/helm/api -f infra/helm/api/values-local.yaml
```

기동 순서: `db (ready)` → `migrate Job (pre-install hook)` → `api × 3`

### 5. 동작 확인

```bash
# minikube tunnel 실행 (별도 터미널, sudo 필요)
minikube tunnel

# 테스트
curl http://127.0.0.1/health
curl http://127.0.0.1/ready
curl -X POST http://127.0.0.1/api/items \
  -H "Content-Type: application/json" \
  -d '{"name": "test"}'
curl http://127.0.0.1/api/items
```

### 6. 종료

```bash
helm uninstall api
helm uninstall db
kubectl delete secret api-secret postgres-secret
kubectl delete pvc postgres-data-db-0
```

### Helm 유용한 명령어

```bash
# 배포 이력 확인
helm history api

# 상태 확인
helm status api

# 이전 버전으로 롤백
helm rollback api 1

# 렌더링 결과 확인 (배포 없이)
helm template api infra/helm/api -f infra/helm/api/values-local.yaml

# K8s 유효성 검사 포함 dry-run
helm install api infra/helm/api --dry-run=server
```

---

## 개발 환경 실행

### 사전 조건

- Node.js 24+
- PostgreSQL 실행 중

### 설치 및 실행

```bash
# 의존성 설치
npm ci

# shared 빌드 (api가 의존)
npm run build -w packages/shared

# DB 마이그레이션
DATABASE_URL=postgresql://devopsim:devopsim@localhost:5432/devopsim \
  npm run migrate -w packages/api

# 개발 서버 실행
DATABASE_URL=postgresql://devopsim:devopsim@localhost:5432/devopsim \
  npm run dev -w packages/api
```

### 테스트

```bash
TEST_DATABASE_URL=postgresql://devopsim:devopsim@localhost:5432/devopsim \
  npm test -w packages/api
```

---

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | /health | liveness — 프로세스 생존 확인 |
| GET | /ready | readiness — DB 연결 상태 확인 |
| POST | /api/items | 아이템 생성 |
| GET | /api/items | 목록 조회 |
| GET | /api/items/:id | 상세 조회 |
| PUT | /api/items/:id | 수정 |
| DELETE | /api/items/:id | 삭제 |
