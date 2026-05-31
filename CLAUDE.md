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

## Python 패키지 관리 (강제 규칙)

`packages/detector/` 등 Python 패키지는 **uv만 사용**한다. pip / poetry / pipenv 금지.

```bash
# 의존성 관리
uv add <pkg>              # 의존성 추가 (pyproject.toml + uv.lock 갱신)
uv sync                   # uv.lock 기준 .venv 재현
uv lock                   # 락 파일만 갱신

# 실행
uv run python -m <module>
uv run pytest
uv run <script.py>
```

Dockerfile도 builder stage에서 uv로 venv 생성 후 prod stage에 복사. `pip install`은 쓰지 않는다.

CI에서도 `uv sync && uv run pytest` 형태. Claude는 Python 관련 작업 시 항상 위 명령 패턴을 사용해야 한다.

### 린트 (ruff, 커밋 전 필수)

Python 코드 커밋 전 반드시 아래 두 명령을 모두 통과시켜야 한다:

```bash
uv run ruff check .       # lint 통과 (errors == 0)
uv run ruff format .      # 자동 포매팅 적용
```

설정은 `packages/detector/pyproject.toml` 의 `[tool.ruff]` 섹션. line-length=120,
select = ["E", "F", "I", "B", "UP", "N", "RUF"]. tests/는 일부 규칙 완화.

이 검증을 거치지 않은 커밋은 만들지 않는다.

### TDD (Red-Green-Refactor, 모든 신규 기능 필수)

신규 Python 기능 구현 시 다음 흐름을 따른다:

1. spec 작성: 사용자와 합의해 `.plan/specs/<feature>.md` 생성 (사용자 의도 직접 표현)
2. `/tdd <spec-path>` 스킬 호출 → Red-Green-Refactor 사이클을 컨텍스트 격리된 sub-agent로 순차 실행
   - test-author agent (spec.md만 input)
   - impl-author agent (test_*.py만 input)
   - refactor agent (impl + 테스트 결과만 input)
3. 각 단계 자동 검증 통과 후 사용자 승인 → 커밋

**핵심 원칙**:
- 외부 의존성(K8s, Prom, Loki, Anthropic 등 Protocol 정의)은 **`tests/fakes/Fake<X>` 클래스 직접 구현**. `unittest.mock`/`pytest-mock`은 httpx 경계에서만.
- Anthropic SDK는 절대 실호출 금지 → `httpx.MockTransport` 주입.
- 테스트는 **행위(input→output/사이드이펙트)** 만 검증. 내부 메서드 호출 횟수/순서 검증 금지.
- 한 사이클 1~10분. step이 30분 넘어가면 spec을 더 작게 쪼갠다.
- sub-agent prompt에 부모 conversation 내용을 인용하지 않는다(격리 보장).

**커밋 전 필수 명령** (ruff + tests 통합):
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -n auto
```

상세 가이드 및 DoD 체크리스트: `.plan/detector/python-tdd.md` (로컬 메모, gitignore).
스킬 정의: `.claude/skills/tdd/SKILL.md`.

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
cd infra/terraform/prod
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
