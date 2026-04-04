# devopsim

DevOps 시뮬레이터 프로젝트.

## 브랜치 전략

```
main ← week1, week2, week3, ...
```

- 주차 단위로 브랜치 생성 (`week1`, `week2`, ...)
- 주차 브랜치에서 기능 단위로 커밋 후 PR → main merge
- 멘토 리뷰는 PR 단위로 진행

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

- `packages/api` — Fastify 앱 (대상 서비스)
- `packages/shared` — 공통 유틸리티
- `infra/` — Docker, K8s, Terraform
- `scenarios/` — 장애 시나리오 스크립트

## 레이어 구조 (api)

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

migrations/       → SQL 마이그레이션 파일
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
