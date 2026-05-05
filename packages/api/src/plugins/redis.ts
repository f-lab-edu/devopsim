import fp from 'fastify-plugin'
import { Redis } from 'ioredis'
import { FastifyInstance } from 'fastify'

declare module 'fastify' {
  interface FastifyInstance {
    redis?: Redis
  }
}

async function redisPlugin(app: FastifyInstance) {
  const url = process.env.REDIS_URL
  if (!url) {
    app.log.info('REDIS_URL not set — cache disabled')
    return
  }
  const redis = new Redis(url, {
    maxRetriesPerRequest: 3,
    enableReadyCheck: true,
    lazyConnect: false,
  })

  redis.on('error', (err) => {
    app.log.warn({ err }, 'redis connection error')
  })

  app.decorate('redis', redis)
  app.addHook('onClose', async () => {
    await redis.quit()
  })
}

export default fp(redisPlugin)
