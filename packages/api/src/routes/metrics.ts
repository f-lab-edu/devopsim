import { FastifyInstance } from 'fastify'
import {
  register,
  httpRequestsTotal,
  httpRequestDuration,
  httpRequestsInFlight,
} from '../lib/metrics'

export default async function metricsRoute(app: FastifyInstance) {
  // HTTP 메트릭 수집 훅
  app.addHook('onRequest', (_req, _reply, done) => {
    httpRequestsInFlight.inc()
    done()
  })

  app.addHook('onResponse', (req, reply, done) => {
    httpRequestsInFlight.dec()
    const route = req.routeOptions?.url ?? req.url
    httpRequestsTotal.inc({
      method: req.method,
      route,
      status_code: String(reply.statusCode),
    })
    done()
  })

  app.get('/metrics', async (_req, reply) => {
    reply.header('Content-Type', register.contentType)
    return register.metrics()
  })
}
