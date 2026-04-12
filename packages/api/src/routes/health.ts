import { FastifyInstance } from 'fastify'
import type { HealthResponse } from '@devopsim/shared'

export default async function healthRoute(app: FastifyInstance) {
  app.get<{ Reply: HealthResponse }>('/health', async () => {
    return { status: 'ok' }
  })

  app.get('/ready', async (_req, reply) => {
    try {
      await app.checkDbHealth()
      reply.send({ status: 'ok' })
    } catch (err) {
      reply.code(503).send({ status: 'unavailable' })
    }
  })

  app.get('/api/version', async () => {
    return { version: '0.0.2' }
  })
}
