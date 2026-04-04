import { buildApp } from '../app'
import type { FastifyInstance } from 'fastify'

export async function createTestApp(): Promise<FastifyInstance> {
  const app = buildApp({ logger: false })
  await app.ready()
  return app
}
