# devopsim

DevOps 시뮬레이터 프로젝트.

## 브랜치 전략

```
main ← feat/* PR merge
```

- 기능 단위로 `feat/` 브랜치 생성
- PR → main merge (멘토 리뷰)
- 릴리즈는 GitHub Tag/Release로 관리 예정

## 커밋 컨벤션

```
feat:     새 기능
fix:      버그 수정
chore:    빌드/설정 변경
docs:     문서
refactor: 리팩토링
test:     테스트
```

## 모노레포 구조

```
packages/
  api/        Fastify CRUD API + /chaos/* + /metrics
  shared/     공통 유틸리티 (pino logger, types)

infra/
  docker/     docker-compose 로컬 실행
  k8s/        Kustomize 매니페스트 (base + overlays/local)
  helm/
    api/      api Helm Chart (Deployment, Service, Ingress, migrate Job)
    db/       PostgreSQL Helm Chart (StatefulSet, Service)
  terraform/  AWS 인프라 IaC (VPC, EKS, ECR)
```

## 현재 배포 상태

### 로컬 (docker-compose)
```bash
cd infra/docker && docker compose up -d --build
```

### 로컬 K8s (minikube + Kustomize)
```bash
kubectl apply -k infra/k8s/overlays/local
```

### 로컬 K8s (minikube + Helm)
```bash
helm install db infra/helm/db
helm install api infra/helm/api -f infra/helm/api/values-local.yaml
```

### AWS EKS (Helm)
```bash
# 이미지 빌드 (amd64 필수)
docker buildx build --platform linux/amd64 \
  -t 893286712531.dkr.ecr.us-east-2.amazonaws.com/devopsim/api:0.0.1 \
  -f packages/api/Dockerfile --push .

helm install db infra/helm/db
helm install api infra/helm/api -f infra/helm/api/values-production.yaml
```

## AWS 인프라 (Terraform)

- **리전**: us-east-2
- **클러스터**: devopsim-prod-cluster (K8s 1.35)
- **노드**: t3.medium × 2
- **ECR**: 893286712531.dkr.ecr.us-east-2.amazonaws.com/devopsim/api
- **State**: s3://nurihaus-terraform-state/devopsim/terraform.tfstate

```bash
cd infra/terraform
terraform apply -var-file=prod.tfvars   # VPC + EKS + ECR
aws eks update-kubeconfig --region us-east-2 --name devopsim-prod-cluster --profile devopsim
```

## api 레이어 구조

```
src/
  domain/         → 도메인 타입 + 레포지토리 인터페이스 (순수 계약, import 없음)
  repositories/   → DB 구현체 (domain 인터페이스 구현)
  services/       → 비즈니스 로직 (domain 인터페이스만 의존)
  routes/         → 요청/응답 처리 + 의존성 조립
    schemas/      → Fastify JSON 스키마 (validation)
  plugins/        → Fastify 플러그인 (DB 등)
  errors.ts       → AppError (중앙화된 에러 클래스)
  app.ts          → buildApp 팩토리 함수 (테스트 재사용)
  index.ts        → listen만 담당
  test/           → Vitest 테스트

migrations/       → node-pg-migrate JS 마이그레이션 파일
```

### 의존성 방향

```
routes → repositories (구현체 조립)
routes → services
services → domain (인터페이스)
repositories → domain (인터페이스 구현)
domain ← 아무것도 import 안 함
```

### 에러 처리

- `AppError(statusCode, message)` throw → `setErrorHandler`에서 일괄 처리
- Fastify schema validation 에러 → `error.validation` 체크 후 400 반환

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | /health | liveness |
| GET | /ready | readiness (DB 연결 확인) |
| GET | /api/version | 버전 확인 |
| POST | /api/items | 아이템 생성 |
| GET | /api/items | 목록 조회 |
| GET | /api/items/:id | 상세 조회 |
| PUT | /api/items/:id | 수정 |
| DELETE | /api/items/:id | 삭제 |

## 주의사항

- EKS 배포 시 반드시 `--platform linux/amd64`로 빌드 (M-series Mac → amd64 EKS)
- db StatefulSet에 `PGDATA=/var/lib/postgresql/data/pgdata` 필요 (EBS lost+found 회피)
- migrate Job은 Helm pre-install hook — db Chart 먼저 설치 후 api Chart 설치
- Secrets는 `kubectl create secret`으로 직접 생성 (Helm Chart에 포함 안 함)
