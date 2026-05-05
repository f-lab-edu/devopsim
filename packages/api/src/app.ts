import Fastify, { FastifyBaseLogger } from 'fastify'
import { logger } from '@devopsim/shared'
import { AppError } from './errors'
import dbPlugin from './plugins/db'
import redisPlugin from './plugins/redis'
import metricsHooksPlugin from './plugins/metrics-hooks'
import chaosRoute from './routes/chaos'
import healthRoute from './routes/health'
import itemsRoute from './routes/items'
import metricsRoute from './routes/metrics'
import { pgItemRepository } from './repositories/items'
import { noopItemCache, redisItemCache } from './cache/items'
import { itemService } from './services/items'
import { cacheMetrics, appErrorsTotal, registerItemsTotalGauge } from './lib/metrics'

export function buildApp(opts: { logger?: boolean } = {}) {
  // 테스트 시 logger: false, 그 외엔 shared pino logger 주입
  // pino.Logger와 FastifyBaseLogger는 런타임 호환이지만 타입이 다소 달라 단언 필요
  const app = opts.logger === false
    ? Fastify({ logger: false })
    : Fastify({ loggerInstance: logger as unknown as FastifyBaseLogger })

  app.setErrorHandler((error: Error & { statusCode?: number; validation?: unknown }, _req, reply) => {
    if (error instanceof AppError) {
      appErrorsTotal.inc({ type: 'app_error' })
      reply.code(error.statusCode).send({ message: error.message })
    } else if (error.validation) {
      appErrorsTotal.inc({ type: 'validation' })
      reply.code(400).send({ message: error.message })
    } else {
      appErrorsTotal.inc({ type: 'unhandled' })
      app.log.error(error)
      reply.code(500).send({ message: 'Internal Server Error' })
    }
  })

  app.register(metricsHooksPlugin)
  app.register(dbPlugin)
  app.register(redisPlugin)

  app.after(() => {
    const repo = pgItemRepository(app.pg.pool)
    const cache = app.redis ? redisItemCache(app.redis) : noopItemCache()
    const service = itemService(repo, cache, cacheMetrics)
    registerItemsTotalGauge(repo)
    app.register(itemsRoute, { service, prefix: '/api' })
  })

  app.register(healthRoute)
  app.register(metricsRoute)
  app.register(chaosRoute)

  return app
}
