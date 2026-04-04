import { FastifyInstance } from 'fastify'
import type { HealthResponse } from '@devopsim/shared'

export default async function healthRoute(app: FastifyInstance) {
  app.get<{ Reply: HealthResponse }>('/health', async () => {
    return { status: 'ok' }
  })
}
