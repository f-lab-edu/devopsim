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

# ---
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
