import { FastifyInstance } from 'fastify'
import {
  register,
  httpRequestsTotal,
  httpRequestDuration,
  httpRequestsInFlight,
} from '../lib/metrics'

// 매 요청마다 객체 shape에 동적 property 추가하는 비용을 피하기 위해
// 시작 시각을 저장할 필드를 모듈 augmentation으로 미리 선언.
declare module 'fastify' {
  interface FastifyRequest {
    metricsStart?: bigint
  }
}

export default async function metricsRoute(app: FastifyInstance) {
  // V8 hidden class 최적화 — Fastify가 request 객체에 미리 자리를 잡아둠
  app.decorateRequest('metricsStart')

  app.addHook('onRequest', (req, _reply, done) => {
    httpRequestsInFlight.inc()
    // hrtime은 monotonic clock (NTP 동기화에 영향받지 않음 → 측정 전용)
    req.metricsStart = process.hrtime.bigint()
    done()
  })

  app.addHook('onResponse', (req, reply, done) => {
    httpRequestsInFlight.dec()
    // routeOptions.url은 라우트 패턴 (e.g. "/api/items/:id"). req.url은 실제 경로라 라벨 cardinality 폭발 위험.
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

  app.get('/metrics', async (_req, reply) => {
    reply.header('Content-Type', register.contentType)
    return register.metrics()
  })
}
