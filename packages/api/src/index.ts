import Fastify from 'fastify'
import dbPlugin from './plugins/db'
import healthRoute from './routes/health'

const app = Fastify({ logger: true })

app.register(dbPlugin)
app.register(healthRoute)

const start = async () => {
  try {
    await app.listen({ port: 3000, host: '0.0.0.0' })
  } catch (err) {
    app.log.error(err)
    process.exit(1)
  }
}

start()
