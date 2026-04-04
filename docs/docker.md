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

---

## Dockerfile (프로덕션) — 3-stage 구조

`Dockerfile.optimized`에서 두 가지 문제가 남아 있었다.

1. **node_modules 전체 복사**: builder의 `node_modules`에는 `typescript`, `ts-node` 등 devDependencies가 섞여 있어 runner에서 그대로 복사하면 불필요한 패키지가 포함된다.
2. **packages/shared 전체 복사**: `packages/shared`의 소스 파일, tsconfig 등 런타임에 불필요한 파일이 최종 이미지에 들어간다.

### 해결 구조: 3-stage 빌드

```
deps    → npm ci --omit=dev   production 의존성만 설치 (runner에 복사할 node_modules)
builder → npm ci + tsc 빌드  전체 의존성 + shared/api 각각 빌드 (dist 생성)
runner  → 조립              deps의 node_modules + builder의 dist만 복사
```

**왜 deps와 builder를 분리하는가:**

빌드에는 `typescript`가 필요하므로 `npm ci`(전체 설치)를 해야 한다. 그러면 builder의 `node_modules`에 devDependencies가 섞인다. 분리할 방법이 없기 때문에, 처음부터 `--omit=dev`로만 설치한 별도 스테이지(deps)를 만들어 runner에서 가져다 쓴다.

### npm workspaces 심링크와 shared dist

```
node_modules/@devopsim/shared  →  (심링크)  →  packages/shared/
                                                  package.json  ← "main": "dist/index.js"
                                                  dist/index.js ← 실제 파일
```

`node_modules/@devopsim/shared`는 파일이 없고 `packages/shared/`를 가리키는 심링크다. Node.js가 `require('@devopsim/shared')`를 만나면 심링크를 따라가 `packages/shared/package.json`의 `"main"` 필드를 읽고 `dist/index.js`를 로드한다.

`deps` 스테이지에서는 `package.json`만 복사하고 소스가 없으므로 `packages/shared/dist/`가 존재하지 않는다. 따라서 builder에서 `npm run build -w packages/shared`로 dist를 생성한 뒤 runner에 복사해야 한다.

runner에 필요한 파일:
- `node_modules/` (deps — production 패키지 + 심링크)
- `packages/shared/dist/` (builder — 심링크가 가리키는 실제 파일)
- `packages/shared/package.json` (builder — `"main"` 필드 해석용)
- `packages/api/dist/` (builder — 앱 실행 파일)

---

## 3-stage 추가 후 실측 비교

환경: Apple M-series, Docker Desktop, base image 캐시됨 (2025-04)

### 이미지 크기

| | naive | optimized | prod (3-stage) |
|---|---|---|---|
| 이미지 크기 | 212 MB | 175 MB | **147 MB** |
| naive 대비 | — | -37 MB (-17%) | **-65 MB (-31%)** |

### node_modules 크기

| | naive | optimized | prod |
|---|---|---|---|
| node_modules | 48.6 MB | 48.6 MB | **20.1 MB** |

`optimized`는 multi-stage로 소스를 분리했지만 `node_modules`는 builder 것을 그대로 복사해서 devDependencies가 그대로 포함된다. `prod`는 처음부터 `--omit=dev`로 설치한 것을 가져와 node_modules가 절반 이하다.

### 빌드 시간

| | naive | optimized | prod (3-stage) |
|---|---|---|---|
| 빌드 시간 (캐시 활용) | 3.8s | 3.0s | 4.4s |

prod는 스테이지가 하나 더 많아(deps) 빌드 시간이 소폭 증가한다. 그러나 `deps`와 `builder` 스테이지는 병렬 실행 가능하도록 Docker BuildKit이 최적화하므로 실제 차이는 작다.

### 포함 내용 비교

| | naive | optimized | prod |
|---|---|---|---|
| 실행 유저 | root (보안 취약) | node | node |
| src/ 소스 파일 | ✅ 포함 | ❌ 제외 | ❌ 제외 |
| devDependencies (typescript 등) | ✅ 포함 | ✅ 포함 | ❌ 제외 |
| packages/shared 소스 | ✅ 포함 | ✅ 포함 | ❌ 제외 (dist만) |
| production dependencies | ✅ 포함 | ✅ 포함 | ✅ 포함 |
| dist/ 빌드 결과물 | ✅ 포함 | ✅ 포함 | ✅ 포함 |

### 동작 확인

```bash
$ docker run -d -p 3001:3000 devopsim-prod
$ curl http://localhost:3001/health
{"status":"ok"}
```

---

## packages/shared 사전 조건

`Dockerfile`(3-stage)에서 `npm run build -w packages/shared`를 실행하므로 `packages/shared`에 빌드 구조가 필요하다.

```
packages/shared/
  tsconfig.json   ← packages/api/tsconfig.json과 동일한 구조로 추가
  src/
    index.ts      ← shared 유틸리티 진입점
```

`tsconfig.json` 없이 빌드하면 루트 `tsconfig.json`이 `**/*`로 전체를 탐색해 `packages/api/src`까지 포함하려 해 `rootDir` 충돌 에러가 발생한다.
