# Stage 1: production 의존성만 설치
FROM node:24-alpine AS deps

WORKDIR /app
RUN chown node:node /app
USER node

COPY --chown=node:node package*.json ./
COPY --chown=node:node packages/api/package.json ./packages/api/
COPY --chown=node:node packages/shared/package.json ./packages/shared/

# devDependencies 없이 런타임에 필요한 패키지만 포함
RUN npm ci --omit=dev

# ---
# Stage 2: 전체 의존성 설치 + 빌드
# typescript 등 devDependencies가 필요하므로 별도 스테이지에서 빌드
FROM node:24-alpine AS builder

WORKDIR /app
RUN chown node:node /app
USER node

COPY --chown=node:node package*.json ./
COPY --chown=node:node packages/api/package.json ./packages/api/
COPY --chown=node:node packages/shared/package.json ./packages/shared/
RUN npm ci

COPY --chown=node:node . .

RUN npm run build -w packages/shared
RUN npm run build -w packages/api

# ---
# Stage 3: 런타임 이미지
# node_modules(deps) + dist(builder)
FROM node:24-alpine AS runner

WORKDIR /app

# node_modules(심링크 포함)
COPY --from=deps --chown=node:node /app/node_modules ./node_modules

# package.json -> 심링크 해석
COPY --from=builder --chown=node:node /app/package.json ./
COPY --from=builder --chown=node:node /app/packages/api/package.json ./packages/api/
COPY --from=builder --chown=node:node /app/packages/shared/package.json ./packages/shared/

# dist만
COPY --from=builder --chown=node:node /app/packages/api/dist ./packages/api/dist
COPY --from=builder --chown=node:node /app/packages/shared/dist ./packages/shared/dist

USER node

EXPOSE 3000

ENTRYPOINT ["node"]
CMD ["packages/api/dist/index.js"]
