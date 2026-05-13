# Stage 1: prod 의존성만
FROM node:24-alpine AS deps

WORKDIR /app
RUN chown node:node /app
USER node

COPY --chown=node:node package*.json ./
COPY --chown=node:node packages/detector/package.json ./packages/detector/
COPY --chown=node:node packages/shared/package.json ./packages/shared/

RUN npm ci --omit=dev

# ---
# Stage 2: 전체 의존성 + 빌드
FROM node:24-alpine AS builder

WORKDIR /app
RUN chown node:node /app
USER node

COPY --chown=node:node package*.json ./
COPY --chown=node:node packages/detector/package.json ./packages/detector/
COPY --chown=node:node packages/shared/package.json ./packages/shared/
RUN npm ci

COPY --chown=node:node . .

RUN npm run build -w packages/shared
RUN npm run build -w packages/detector

# ---
# Stage 3: 런타임
FROM node:24-alpine AS runner

WORKDIR /app

COPY --from=deps --chown=node:node /app/node_modules ./node_modules

COPY --from=builder --chown=node:node /app/package.json ./
COPY --from=builder --chown=node:node /app/packages/detector/package.json ./packages/detector/
COPY --from=builder --chown=node:node /app/packages/shared/package.json ./packages/shared/

COPY --from=builder --chown=node:node /app/packages/detector/dist ./packages/detector/dist
COPY --from=builder --chown=node:node /app/packages/shared/dist ./packages/shared/dist

ARG BUILD_VERSION=dev
ARG BUILD_COMMIT=unknown
ARG BUILD_DATE=unknown
ARG BUILD_SERVICE=detector

ENV APP_VERSION=$BUILD_VERSION
ENV APP_COMMIT=$BUILD_COMMIT
ENV APP_BUILD_DATE=$BUILD_DATE
ENV APP_SERVICE=$BUILD_SERVICE

USER node

EXPOSE 3000

ENTRYPOINT ["node"]
CMD ["packages/detector/dist/index.js"]
