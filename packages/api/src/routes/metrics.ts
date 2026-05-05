import { FastifyInstance } from 'fastify'
import { register } from '../lib/metrics'

// HTTP 메트릭 수집 hook은 plugins/metrics-hooks.ts (fp 처리됨)에 분리.
// 이 파일은 /metrics 노출 라우트만 담당.
export default async function metricsRoute(app: FastifyInstance) {
  app.get('/metrics', async (_req, reply) => {
    reply.header('Content-Type', register.contentType)
    return register.metrics()
  })
}
