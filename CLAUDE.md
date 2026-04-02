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
routes/       → 요청/응답 처리
services/     → 비즈니스 로직
repositories/ → DB 접근
```
