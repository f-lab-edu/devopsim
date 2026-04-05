import fp from 'fastify-plugin'
import postgres from '@fastify/postgres'
import { FastifyInstance } from 'fastify'

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
}

export default fp(dbPlugin)
