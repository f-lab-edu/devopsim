import type { Pool } from 'pg'
import { Histogram, Gauge } from 'prom-client'
import { register } from './register'

// operation 라벨로 어떤 쿼리가 느린지 분리 분석. URL 라벨은 cardinality 위험해서 X
export const dbQueryDuration = new Histogram({
  name: 'db_query_duration_seconds',
  help: 'DB query duration in seconds',
  labelNames: ['operation'],
  buckets: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1],
  registers: [register],
})

// startTimer()는 prom-client 제공 — 종료 함수 호출 시 elapsed 자동 observe.
export async function measureDbQuery<T>(
  operation: string,
  fn: () => Promise<T>
): Promise<T> {
  const end = dbQueryDuration.startTimer({ operation })
  try {
    return await fn()
  } finally {
    end()
  }
}

// pg.Pool은 totalCount/idleCount/waitingCount를 표준 속성으로 노출.
// /metrics 호출 시점에 collect 콜백이 그 값을 set — 항상 최신값을 반환.
// idempotent: 테스트에서 buildApp이 여러 번 호출돼도 register 중복 등록 에러 회피.
export function registerPgPoolGauges(pool: Pool) {
  if (register.getSingleMetric('pg_pool_total_connections')) return
  new Gauge({
    name: 'pg_pool_total_connections',
    help: 'Total connections in the pool (active + idle)',
    registers: [register],
    collect() { this.set(pool.totalCount) },
  })
  new Gauge({
    name: 'pg_pool_idle_connections',
    help: 'Idle connections waiting to be checked out',
    registers: [register],
    collect() { this.set(pool.idleCount) },
  })
  new Gauge({
    name: 'pg_pool_waiting_clients',
    help: 'Clients waiting for a connection (queue length when pool is full)',
    registers: [register],
    collect() { this.set(pool.waitingCount) },
  })
}
