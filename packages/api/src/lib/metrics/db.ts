import type { Pool } from 'pg'
import { Histogram, Gauge } from 'prom-client'
import { register } from './register'

export type DbPoolName = 'read' | 'write'

// operation 라벨로 어떤 쿼리가 느린지, pool 라벨로 read replica vs primary 분리 분석.
// URL 라벨은 cardinality 위험해서 X
export const dbQueryDuration = new Histogram({
  name: 'db_query_duration_seconds',
  help: 'DB query duration in seconds',
  labelNames: ['operation', 'pool'],
  buckets: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1],
  registers: [register],
})

// startTimer()는 prom-client 제공 — 종료 함수 호출 시 elapsed 자동 observe.
export async function measureDbQuery<T>(
  operation: string,
  pool: DbPoolName,
  fn: () => Promise<T>
): Promise<T> {
  const end = dbQueryDuration.startTimer({ operation, pool })
  try {
    return await fn()
  } finally {
    end()
  }
}

// pg.Pool은 totalCount/idleCount/waitingCount를 표준 속성으로 노출.
// /metrics 호출 시점에 collect 콜백이 등록된 모든 pool을 순회하며 set —
// 항상 최신값 반환. pool 라벨로 read/write 분리.
const registeredPools = new Map<DbPoolName, Pool>()

export function registerPgPoolGauges(name: DbPoolName, pool: Pool) {
  // 첫 호출 시 Gauge 자체를 등록 — collect 콜백이 registeredPools를 순회
  if (registeredPools.size === 0) {
    new Gauge({
      name: 'pg_pool_total_connections',
      help: 'Total connections in the pool (active + idle)',
      labelNames: ['pool'],
      registers: [register],
      collect() {
        for (const [poolName, p] of registeredPools) {
          this.labels(poolName).set(p.totalCount)
        }
      },
    })
    new Gauge({
      name: 'pg_pool_idle_connections',
      help: 'Idle connections waiting to be checked out',
      labelNames: ['pool'],
      registers: [register],
      collect() {
        for (const [poolName, p] of registeredPools) {
          this.labels(poolName).set(p.idleCount)
        }
      },
    })
    new Gauge({
      name: 'pg_pool_waiting_clients',
      help: 'Clients waiting for a connection (queue length when pool is full)',
      labelNames: ['pool'],
      registers: [register],
      collect() {
        for (const [poolName, p] of registeredPools) {
          this.labels(poolName).set(p.waitingCount)
        }
      },
    })
  }

  registeredPools.set(name, pool)
}
