import { FastifyInstance } from 'fastify'
import {
  Registry,
  collectDefaultMetrics,
  Counter,
  Histogram,
  Gauge,
} from 'prom-client'

const register = new Registry()

collectDefaultMetrics({ register })

// ── HTTP 메트릭 ──────────────────────────────────────────────────────────

export const httpRequestsTotal = new Counter({
  name: 'http_requests_total',
  help: 'Total number of HTTP requests',
  labelNames: ['method', 'route', 'status_code'],
  registers: [register],
})

export const httpRequestDuration = new Histogram({
  name: 'http_request_duration_seconds',
  help: 'HTTP request duration in seconds',
  labelNames: ['method', 'route'],
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5],
  registers: [register],
})

export const httpRequestsInFlight = new Gauge({
  name: 'http_requests_in_flight',
  help: 'Number of HTTP requests currently being processed',
  registers: [register],
})

// ── DB 메트릭 ────────────────────────────────────────────────────────────

export const dbPoolActive = new Gauge({
  name: 'db_pool_active',
  help: 'Number of active DB connections',
  registers: [register],
})

export const dbPoolIdle = new Gauge({
  name: 'db_pool_idle',
  help: 'Number of idle DB connections',
  registers: [register],
})

export const dbPoolWaiting = new Gauge({
  name: 'db_pool_waiting',
  help: 'Number of requests waiting for a DB connection (0이면 정상, 양수면 포화)',
  registers: [register],
})

export const dbQueryDuration = new Histogram({
  name: 'db_query_duration_seconds',
  help: 'DB query duration in seconds',
  labelNames: ['operation'],
  buckets: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1],
  registers: [register],
})

export const dbConnectionErrors = new Counter({
  name: 'db_connection_errors_total',
  help: 'Total number of DB connection errors',
  registers: [register],
})

// ── /metrics 라우트 ──────────────────────────────────────────────────────

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

  // DB pool 상태를 주기적으로 수집 (10초마다)
  const collectDbPoolMetrics = () => {
    try {
      const pool = app.pg.pool
      dbPoolActive.set(pool.totalCount - pool.idleCount)
      dbPoolIdle.set(pool.idleCount)
      dbPoolWaiting.set(pool.waitingCount)
    } catch {
      // DB 플러그인 초기화 전에 호출될 수 있으므로 무시
    }
  }

  const interval = setInterval(collectDbPoolMetrics, 10_000)
  app.addHook('onClose', () => clearInterval(interval))

  app.get('/metrics', async (_req, reply) => {
    reply.header('Content-Type', register.contentType)
    return register.metrics()
  })
}
