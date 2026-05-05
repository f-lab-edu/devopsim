import fp from 'fastify-plugin'
import postgres from '@fastify/postgres'
import { FastifyInstance } from 'fastify'
import { registerPgPoolGauges } from '../lib/metrics'

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

  // pool이 준비된 후 메트릭 등록 — collect 콜백이 /metrics 호출 시점마다 최신값 set
  app.addHook('onReady', async () => {
    registerPgPoolGauges(app.pg.pool)
  })
}

export default fp(dbPlugin)
