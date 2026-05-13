import { FastifyInstance } from 'fastify'

export default async function healthRoute(app: FastifyInstance) {
  app.get('/health', async () => ({ status: 'ok', uptime: Math.round(process.uptime()) }))

  app.get('/ready', async () => ({ status: 'ok' }))

  app.get('/api/version', async () => ({
    service: process.env.APP_SERVICE ?? 'detector',
    version: process.env.APP_VERSION ?? 'dev',
    commit: process.env.APP_COMMIT ?? 'unknown',
    buildDate: process.env.APP_BUILD_DATE ?? 'unknown',
  }))
}
