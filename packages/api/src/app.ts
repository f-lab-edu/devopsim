import Fastify, { FastifyBaseLogger } from 'fastify'
import { logger } from '@devopsim/shared'
import { AppError } from './errors'
import dbPlugin from './plugins/db'
import healthRoute from './routes/health'
import itemsRoute from './routes/items'
import { pgItemRepository } from './repositories/items'
import { itemService } from './services/items'

export function buildApp(opts: { logger?: boolean } = {}) {
  // 테스트 시 logger: false, 그 외엔 shared pino logger 주입
  // pino.Logger와 FastifyBaseLogger는 런타임 호환이지만 타입이 다소 달라 단언 필요
  const app = opts.logger === false
    ? Fastify({ logger: false })
    : Fastify({ loggerInstance: logger as unknown as FastifyBaseLogger })

  app.setErrorHandler((error: Error & { statusCode?: number; validation?: unknown }, _req, reply) => {
    if (error instanceof AppError) {
      reply.code(error.statusCode).send({ message: error.message })
    } else if (error.validation) {
      reply.code(400).send({ message: error.message })
    } else {
      app.log.error(error)
      reply.code(500).send({ message: 'Internal Server Error' })
    }
  })

  app.register(dbPlugin)

  app.after(() => {
    const repo = pgItemRepository(app.pg.pool)
    const service = itemService(repo)
    app.register(itemsRoute, { service, prefix: '/api' })
  })

  app.register(healthRoute)

  return app
}
