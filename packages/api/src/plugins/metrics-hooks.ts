import fp from 'fastify-plugin'
import { FastifyInstance } from 'fastify'
import {
  httpRequestsTotal,
  httpRequestDuration,
  httpRequestsInFlight,
} from '../lib/metrics'

declare module 'fastify' {
  interface FastifyRequest {
    metricsStart?: bigint
  }
}

// fastify-plugin (fp)으로 감싸야 hook이 부모 scope로 hoist되어
// 모든 라우트(items/chaos/health/metrics)에 적용됨. 일반 plugin 함수면
// register 한 자기 scope 안에서만 동작 — HTTP 메트릭이 /metrics만 잡히는 버그 원인.
async function metricsHooks(app: FastifyInstance) {
  app.decorateRequest('metricsStart')

  app.addHook('onRequest', (req, _reply, done) => {
    httpRequestsInFlight.inc()
    req.metricsStart = process.hrtime.bigint()
    done()
  })

  app.addHook('onResponse', (req, reply, done) => {
    httpRequestsInFlight.dec()
    // routeOptions.url 은 라우트 패턴 (예: "/api/items/:id"). req.url은 실제 경로라
    // id별로 라벨이 달라져 cardinality 폭발 위험.
    const route = req.routeOptions?.url ?? req.url
    httpRequestsTotal.inc({
      method: req.method,
      route,
      status_code: String(reply.statusCode),
    })

    if (req.metricsStart !== undefined) {
      const elapsed = Number(process.hrtime.bigint() - req.metricsStart) / 1e9
      httpRequestDuration.observe({ method: req.method, route }, elapsed)
    }
    done()
  })
}

export default fp(metricsHooks)
