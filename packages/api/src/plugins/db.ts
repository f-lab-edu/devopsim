import fp from 'fastify-plugin'
import postgres from '@fastify/postgres'
import { FastifyInstance } from 'fastify'
import type { Pool } from 'pg'
import { registerPgPoolGauges } from '../lib/metrics'

export interface DbPools {
  read: Pool
  write: Pool
}

declare module 'fastify' {
  interface FastifyInstance {
    checkDbHealth: () => Promise<void>
  }
}

async function dbPlugin(app: FastifyInstance) {
  // read replica가 없는 환경에선 동일 URL로 fallback — 로컬/테스트 호환
  const writeUrl = process.env.DATABASE_WRITE_URL ?? process.env.DATABASE_URL
  const readUrl = process.env.DATABASE_READ_URL ?? writeUrl

  app.register(postgres, { connectionString: writeUrl, name: 'write' })
  app.register(postgres, { connectionString: readUrl, name: 'read' })

  app.decorate('checkDbHealth', async () => {
    await Promise.all([
      app.pg.write.pool.query('SELECT 1'),
      app.pg.read.pool.query('SELECT 1'),
    ])
  })

  app.addHook('onReady', async () => {
    registerPgPoolGauges('write', app.pg.write.pool)
    registerPgPoolGauges('read', app.pg.read.pool)
  })
}

export default fp(dbPlugin)
