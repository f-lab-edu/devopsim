# Dockerfile 비교 및 학습 기록

## 개요

`packages/api`의 Dockerfile을 두 가지 버전으로 작성하고, 직접 디버깅하며 Docker 동작 원리를 파악한다.

| 항목 | Dockerfile.naive | Dockerfile.optimized |
|------|-----------------|----------------------|
| 빌드 방식 | 단일 스테이지 | multi-stage (builder + runner) |
| 보안 | root 실행 | non-root (USER node) |
| 이미지 크기 | 202 MB | 167 MB |
| devDependencies 포함 | ✅ (런타임에도 포함) | ❌ (빌드 후 제외) |

---

## Dockerfile.naive

```dockerfile
FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
COPY packages/api/package.json ./packages/api/
COPY packages/shared/package.json ./packages/shared/

RUN npm ci

COPY . .

RUN npm run build -w packages/api

EXPOSE 3000

ENTRYPOINT ["node"]
CMD ["packages/api/dist/index.js"]
```

**의도적으로 생략한 것들:**
- `USER node` — root로 실행 (보안 취약)
- multi-stage — devDependencies가 런타임 이미지에 포함됨

---

## Dockerfile.optimized

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
RUN chown node:node /app
USER node

COPY --chown=node:node package*.json ./
COPY --chown=node:node packages/api/package.json ./packages/api/
COPY --chown=node:node packages/shared/package.json ./packages/shared/
RUN npm ci

COPY --chown=node:node . .

RUN npm run build -w packages/api

FROM node:20-alpine AS runner

WORKDIR /app

COPY --from=builder /app/packages/api/dist ./packages/api/dist
COPY --from=builder /app/packages/shared ./packages/shared
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

USER node

EXPOSE 3000

ENTRYPOINT ["node"]
CMD ["packages/api/dist/index.js"]
```

---

## 디버깅 과정

### 1. npm ci 실패 — package-lock.json 없음

```
npm error The `npm ci` command can only install with an existing package-lock.json
```

**원인:** `COPY package*.json ./`은 현재 디렉토리(루트)의 `package.json`, `package-lock.json`만 복사한다.
모노레포 워크스페이스 구조에서 각 패키지의 `package.json`은 별도로 명시해야 한다.

**해결:**
```dockerfile
COPY package*.json ./
COPY packages/api/package.json ./packages/api/
COPY packages/shared/package.json ./packages/shared/
```

**배운 점:** `npm ci`는 `package-lock.json` 기준으로 정확한 버전을 설치한다.
`npm install`과 달리 lock 파일을 수정하지 않아 CI/Docker 환경에 적합하다.

---

### 2. EACCES: permission denied — USER 선언 순서 문제

```
npm error EACCES: permission denied, mkdir '/app/node_modules'
```

**원인:** `USER node` 선언 이후 `WORKDIR`이 생성되거나 `COPY`가 실행되면
파일 소유자가 root가 되어 node 유저가 쓰기 권한을 갖지 못한다.

```dockerfile
# 잘못된 순서
USER node       # node 유저로 전환
WORKDIR /app    # root 소유로 /app 생성
COPY . .        # root 소유로 복사
RUN npm ci      # node 유저가 node_modules 생성 시도 → EACCES
```

**해결 (optimized):** `--chown` 옵션으로 복사 시 소유자를 명시한다.
```dockerfile
WORKDIR /app
RUN chown node:node /app
USER node
COPY --chown=node:node . .
RUN npm ci      # node 유저가 자신 소유 파일에 쓰기 → 성공
```

**해결 (naive):** `USER node`를 아예 제거한다. (보안 고려 안 하는 버전)

**배운 점:** Docker 레이어는 순서가 중요하다. `USER`, `WORKDIR`, `COPY`의 실행 순서에 따라
파일 소유권이 달라지며, 이후 명령의 실행 권한에 영향을 준다.

---

### 3. tsc: not found — 모노레포 워크스페이스 구조 미인식

```
sh: tsc: not found
```

**원인:** `COPY package*.json ./`가 루트 `package.json`만 복사하면
`npm ci`가 워크스페이스 구조를 인식하지 못해 각 패키지의 `devDependencies`를 설치하지 않는다.
`typescript`는 `packages/api/package.json`의 `devDependencies`에 있으므로 설치되지 않는다.

**해결:** 워크스페이스 패키지의 `package.json`을 먼저 복사해서 npm이 전체 워크스페이스 구조를 인식하게 한다.

**배운 점:** npm workspaces는 루트에서 의존성을 통합 관리하지만,
각 패키지의 `package.json`이 있어야 워크스페이스 구조를 인식한다.

---

### 4. dist 경로 오류 — 모노레포 빌드 결과물 위치

```
Error: Cannot find module '/app/dist/index.js'
```

**원인:** `npm run build -w packages/api`는 `packages/api/` 안에서 빌드하므로
결과물은 `/app/packages/api/dist/`에 생성된다. `/app/dist/`가 아니다.

**해결:**
```dockerfile
CMD ["packages/api/dist/index.js"]  # 실제 경로
```

**배운 점:** 모노레포에서 빌드 컨텍스트와 워크스페이스 명령의 실행 위치를 명확히 구분해야 한다.

---

### 5. multi-stage에서 shared 패키지 누락

**원인:** `node_modules/@devopsim/shared`는 `packages/shared/`를 심볼릭 링크로 가리킨다.
runner 스테이지에서 `node_modules`만 복사하면 링크 타겟이 없어 런타임에 모듈을 찾지 못한다.

**해결:**
```dockerfile
COPY --from=builder /app/packages/shared ./packages/shared  # 링크 타겟 포함
COPY --from=builder /app/node_modules ./node_modules        # 심볼릭 링크
```

**배운 점:** npm workspaces의 로컬 패키지는 심볼릭 링크로 연결된다.
multi-stage 빌드에서 링크 타겟도 함께 복사해야 한다.

---

## 빌드 결과 비교

환경: Apple M-series, Docker Desktop, 로컬 네트워크 (base image 캐시됨)

### 최초 빌드 (--no-cache)

| | naive | optimized |
|---|---|---|
| 빌드 시간 | ~4.8s | ~4.2s |
| 이미지 크기 | 202 MB | 167 MB |

> base image(`node:alpine`)가 이미 로컬에 캐시된 상태라 절대 시간보다 크기 차이가 더 의미 있는 지표다.

### 소스 코드 변경 후 재빌드 (캐시 활용)

`packages/api/src/routes/health.ts` 수정 후 재빌드:

| | naive | optimized |
|---|---|---|
| 재빌드 시간 | ~1.6s | ~1.9s |
| npm ci | CACHED ✅ | CACHED ✅ |
| 재실행 레이어 | COPY + tsc | COPY + tsc + runner COPY |

**분석:**
- 두 버전 모두 `package*.json`을 소스보다 먼저 복사하는 레이어 캐시 전략을 사용하므로
  소스 변경 시 `npm ci`는 캐시 히트된다.
- optimized는 runner 스테이지 COPY가 추가되어 재빌드가 약간 더 걸린다.
- 의존성 변경(`package.json` 수정) 시에는 두 버전 모두 `npm ci`부터 다시 실행된다.

### 크기 차이 원인

| 구성 요소 | naive | optimized |
|-----------|-------|-----------|
| 소스코드 (src/) | ✅ 포함 | ❌ 제외 |
| devDependencies (typescript 등) | ✅ 포함 | ❌ 제외 |
| 빌드 결과물 (dist/) | ✅ 포함 | ✅ 포함 |
| production dependencies | ✅ 포함 | ✅ 포함 |

35MB 차이의 대부분은 `typescript`, `ts-node`, `@types/*` 등 devDependencies다.

---

## 빌드 명령어

```bash
# 루트에서 실행 (모노레포 컨텍스트 필요)

# naive
docker build -f packages/api/Dockerfile.naive -t devopsim-api-naive .

# optimized
docker build -f packages/api/Dockerfile.optimized -t devopsim-api-optimized .

# 실행
docker run -e DATABASE_URL=postgresql://dummy -p 3000:3000 devopsim-api-naive
```
