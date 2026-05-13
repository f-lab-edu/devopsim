import { FastifyInstance } from 'fastify'
import { register } from '../lib/metrics'

export default async function metricsRoute(app: FastifyInstance) {
  app.get('/metrics', async (_req, reply) => {
    reply.header('Content-Type', register.contentType)
    return register.metrics()
  })
}
