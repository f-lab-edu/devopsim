import fp from 'fastify-plugin'
import postgres from '@fastify/postgres'
import { FastifyInstance } from 'fastify'
import { monitorPgPool } from '@christiangalsterer/node-postgres-prometheus-exporter'
import { register } from '../lib/metrics'

declare module 'fastify' {
  interface FastifyInstance {
    checkDbHealth: () => Promise<void>
  }
}

async function dbPlugin(app: FastifyInstance) {
  app.register(postgres, {
    connectionString: process.env.DATABASE_URL,
  })

  app.decorate('checkDbHealth', async () => {
    await app.pg.pool.query('SELECT 1')
  })

  // pool이 준비된 후 Prometheus 모니터링 시작
  // pool.query를 내부적으로 패치해서 query_duration, errors 자동 수집
  app.addHook('onReady', async () => {
    monitorPgPool(app.pg.pool, register)
  })
}

export default fp(dbPlugin)
