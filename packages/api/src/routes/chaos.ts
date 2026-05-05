import { FastifyInstance } from 'fastify'

const MAX_BURN_MS = 10_000
const MAX_SLOW_MS = 5_000
const MAX_DB_SLEEP_SEC = 10
const MAX_DB_BURST = 100

export default async function chaosRoute(app: FastifyInstance) {
  // ── CPU 소모 ────────────────────────────────────────────────────────
  // GET /chaos/cpu?ms=2000 → 약 2초간 이벤트 루프 점유
  app.get<{ Querystring: { ms?: string } }>('/chaos/cpu', async (req, reply) => {
    const requested = Number(req.query.ms ?? 1000)
    const ms = Math.min(Math.max(requested, 1), MAX_BURN_MS)

    const end = Date.now() + ms
    let iterations = 0
    while (Date.now() < end) {
      Math.sqrt(Math.random() * Math.random())
      iterations++
    }

    reply.send({ burnedMs: ms, iterations })
  })

  // ── 캐시 강제 비우기 ────────────────────────────────────────────────
  // POST /chaos/cache/flush → popular 캐시 키 모두 삭제. cache miss storm 시뮬레이션.
  app.post('/chaos/cache/flush', async (_req, reply) => {
    if (!app.redis) {
      return reply.code(503).send({ error: 'redis disabled' })
    }
    const keys = await app.redis.keys('items:popular:*')
    if (keys.length > 0) {
      await app.redis.del(...keys)
    }
    reply.send({ deleted: keys.length })
  })

  // ── 캐시 응답 지연 ──────────────────────────────────────────────────
  // GET /chaos/cache/slow?ms=500 → Redis 호출 후 의도적 sleep. cache 응답 느려진 상황 시뮬.
  app.get<{ Querystring: { ms?: string } }>('/chaos/cache/slow', async (req, reply) => {
    const requested = Number(req.query.ms ?? 500)
    const ms = Math.min(Math.max(requested, 1), MAX_SLOW_MS)

    if (app.redis) {
      await app.redis.set('chaos:slow', '1', 'EX', 1)
    }
    await new Promise((r) => setTimeout(r, ms))
    reply.send({ delayedMs: ms })
  })

  // ── DB slow query ──────────────────────────────────────────────────
  // GET /chaos/db/slow?seconds=2 → pg_sleep으로 의도적 slow query.
  // db_query_duration_seconds_bucket의 큰 bucket(0.5, 1, 2.5)에 카운트 증가.
  app.get<{ Querystring: { seconds?: string } }>('/chaos/db/slow', async (req, reply) => {
    const requested = Number(req.query.seconds ?? 1)
    const sec = Math.min(Math.max(requested, 1), MAX_DB_SLEEP_SEC)

    await app.pg.pool.query('SELECT pg_sleep($1)', [sec])
    reply.send({ sleptSeconds: sec })
  })

  // ── DB burst (풀 고갈) ──────────────────────────────────────────────
  // GET /chaos/db/burst?count=20 → 동시 query N개로 풀 max 초과 시도.
  // pg_pool_waiting_clients 메트릭이 발현됨.
  app.get<{ Querystring: { count?: string; sleep?: string } }>(
    '/chaos/db/burst',
    async (req, reply) => {
      const requestedCount = Number(req.query.count ?? 20)
      const count = Math.min(Math.max(requestedCount, 1), MAX_DB_BURST)
      const sleepSec = Math.min(Math.max(Number(req.query.sleep ?? 2), 1), MAX_DB_SLEEP_SEC)

      const queries = Array.from({ length: count }, () =>
        app.pg.pool.query('SELECT pg_sleep($1)', [sleepSec])
      )
      await Promise.all(queries)
      reply.send({ count, sleepSec })
    }
  )

  // ── DB error ───────────────────────────────────────────────────────
  // GET /chaos/db/error → 잘못된 query 발생. setErrorHandler가 잡아서
  // app_errors_total{type="unhandled"} 카운트 증가.
  app.get('/chaos/db/error', async () => {
    await app.pg.pool.query('SELECT * FROM nonexistent_table_for_chaos')
    return { unreachable: true }
  })
}
