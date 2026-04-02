import fp from 'fastify-plugin'
import postgres from '@fastify/postgres'
import { FastifyInstance } from 'fastify'

async function dbPlugin(app: FastifyInstance) {
  app.register(postgres, {
    connectionString: process.env.DATABASE_URL,
  })
}

export default fp(dbPlugin)
