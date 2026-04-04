# docker-compose migrate 서비스 추가

## 배경

초기 `docker-compose.yaml`은 `api`와 `db` 두 서비스만 존재했다.
이 상태에서 `docker compose up`을 실행하면 다음 문제가 발생한다.

```
api 컨테이너 기동
  → GET /items 호출
  → ERROR: relation "items" does not exist
```

테이블이 없는 상태에서 api가 먼저 뜨기 때문이다. 개발자가 직접 아래 명령을 실행해야 했다.

```bash
psql $DATABASE_URL -f migrations/001_create_items.sql
```

이 문제를 해결하기 위해 `migrate` 서비스를 추가했다.

---

## 마이그레이션 실행 방식 비교

마이그레이션을 자동화하는 방법은 크게 두 가지다.

### 방식 1: 엔트리포인트 스크립트 (같은 컨테이너)

```sh
#!/bin/sh
# entrypoint.sh
node-pg-migrate up   # 마이그레이션
exec node dist/index.js  # 서버 실행
```

```yaml
# docker-compose.yaml
api:
  command: ["sh", "entrypoint.sh"]
  depends_on:
    db:
      condition: service_healthy
```

**동작:** api 컨테이너 안에서 마이그레이션을 먼저 실행한 뒤 서버를 띄운다.

**문제점 — 스케일 아웃 시 레이스 컨디션:**

```yaml
api:
  deploy:
    replicas: 3  # 3개 컨테이너가 동시에 마이그레이션 실행
```

3개 컨테이너가 동시에 `CREATE TABLE items`를 실행하면:

```
replica-1: CREATE TABLE items → 성공
replica-2: CREATE TABLE items → ERROR: relation "items" already exists
replica-3: CREATE TABLE items → ERROR: relation "items" already exists
```

`IF NOT EXISTS`로 회피할 수 있지만, 복잡한 DDL(ALTER TABLE, 인덱스 생성 등)에서는 동시 실행 자체가 위험하다.

---

### 방식 2: 별도 migrate 컨테이너 (현재 방식)

```yaml
migrate:
  build:
    context: ../../
    dockerfile: packages/api/Dockerfile
  command: ["node_modules/.bin/node-pg-migrate", "-m", "packages/api/migrations", "up"]
  depends_on:
    db:
      condition: service_healthy

api:
  depends_on:
    migrate:
      condition: service_completed_successfully
```

**동작:** migrate 컨테이너가 완전히 종료(exit 0)된 후에만 api 컨테이너가 기동된다.

스케일 아웃해도 migrate는 1개만 실행되므로 레이스 컨디션이 없다.

---

## depends_on condition 비교

`depends_on`의 `condition`은 세 가지 값을 지원한다.

| condition | 의미 | 언제 사용 |
|-----------|------|----------|
| `service_started` | 컨테이너 프로세스가 시작됨 | 종속성이 단순히 실행 중이어야 할 때 |
| `service_healthy` | healthcheck가 통과됨 | DB처럼 실제로 요청을 받을 준비가 된 상태가 필요할 때 |
| `service_completed_successfully` | 컨테이너가 exit code 0으로 종료됨 | 마이그레이션처럼 "완전히 끝났다"는 보장이 필요할 때 |

이 프로젝트의 기동 순서:

```
db (service_healthy)
  ↓ pg_isready 통과 후
migrate (service_completed_successfully)
  ↓ exit 0 후
api
```

`service_started`나 `service_healthy`를 migrate에 적용하면 migrate가 실행 중일 때 api가 기동되어 테이블이 없는 상태에서 쿼리가 실행될 수 있다.

---

## 실측 지표

환경: Apple M-series, Docker Desktop, 이미지 빌드 완료 상태

### migrate 컨테이너 실행 시간

| 실행 | 결과 | 소요 시간 |
|------|------|----------|
| 1회차 (최초, 볼륨 없음) | `001_create_items` 실행 | ~298ms |
| 2회차 (볼륨 유지) | `No migrations to run!` 스킵 | ~162ms |

2회차에서 migrate가 `pgmigrations` 테이블을 확인하고 이미 실행된 파일은 건너뛴다. **마이그레이션은 항상 안전하게 재실행 가능하다.**

### docker compose up 전체 시간

| 상태 | 소요 시간 |
|------|----------|
| 최초 기동 (볼륨 없음) | ~6.5s |
| 재기동 (볼륨 유지, 서비스 Running) | ~1.2s |

### 이미지 크기

방식 1(엔트리포인트)은 migrate 전용 이미지가 없으므로 해당 없음.
방식 2에서 migrate 컨테이너는 api와 동일한 이미지를 재사용한다.

| 이미지 | 크기 | 용도 |
|--------|------|------|
| `docker-api` (= `docker-migrate`) | 178 MB | api 실행 + 마이그레이션 |
| `postgres:16-alpine` | 272 MB | (구 방식: psql로 마이그레이션) |

별도 postgres 이미지 대신 api 이미지를 재사용하므로 **migrate 전용 이미지가 추가로 필요 없다.**

---

## 새 마이그레이션 추가 시 비교

### 구 방식 (psql 하드코딩)

```yaml
# docker-compose.yaml 수정 필요
command: >
  sh -c "psql $DATABASE_URL -f /migrations/001_create_items.sql &&
         psql $DATABASE_URL -f /migrations/002_add_tags.sql"
```

파일이 늘어날수록 `docker-compose.yaml`도 함께 수정해야 한다.

### 현재 방식 (node-pg-migrate)

```
migrations/
  001_create_items.js   ← 기존
  002_add_tags.js       ← 파일만 추가
```

`docker-compose.yaml` 수정 없이 파일만 추가하면 된다. `node-pg-migrate`가 `pgmigrations` 테이블과 대조해 실행되지 않은 파일만 순서대로 실행한다.

---

## K8s 전환 시 매핑

별도 컨테이너 방식은 Kubernetes의 Job / InitContainer 패턴과 자연스럽게 대응된다.

| docker-compose | Kubernetes |
|----------------|-----------|
| migrate 서비스 | `Job` (한 번 실행 후 완료) |
| `service_completed_successfully` | `initContainers` (완료 후 메인 컨테이너 기동) |
| api 서비스 | `Deployment` |

엔트리포인트 방식으로 구현했다면 K8s 전환 시 구조를 다시 설계해야 한다.
