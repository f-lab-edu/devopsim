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
  k8s/          Kubernetes 매니페스트
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

---
## 주차별 진행

| 주차 | 내용 |
|------|------|
| week1 | Docker 최적화, Fastify CRUD API, docker-compose + node-pg-migrate |
| week2 | Kubernetes (minikube), Deployment/Service/Ingress, probe 설정 |
| week3 | Helm Chart 작성, 환경별 values 분리 |
| week4 | Terraform으로 AWS VPC + EKS 클러스터 구성 |
| week5 | ECR + ArgoCD GitOps 배포 루프 |
| week6 | GitHub Actions CI/CD 파이프라인 |
| week7 | Karpenter + HPA 오토스케일링 |
| week8 | Redis 캐시 + RDS Read Replica |
| week9 | Prometheus 커스텀 메트릭 + Grafana 대시보드 |
| week10 | PrometheusRule + Alertmanager + Loki |
| week11 | Traefik + HTTPS + Rate Limit |
| week12 | 부하 테스트 + 장애 시나리오 종합 실습 |
