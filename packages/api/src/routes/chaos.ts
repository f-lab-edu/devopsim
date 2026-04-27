import { FastifyInstance } from 'fastify'

const MAX_BURN_MS = 10_000

export default async function chaosRoute(app: FastifyInstance) {
  // CPU를 의도적으로 소모하는 엔드포인트 (HPA / Karpenter 부하 테스트용)
  // GET /chaos/cpu?ms=2000  → 약 2초간 이벤트 루프 점유
  app.get<{ Querystring: { ms?: string } }>('/chaos/cpu', async (req, reply) => {
    const requested = Number(req.query.ms ?? 1000)
    const ms = Math.min(Math.max(requested, 1), MAX_BURN_MS)

    const end = Date.now() + ms
    let iterations = 0
    while (Date.now() < end) {
      Math.sqrt(Math.random() * Math.random())
      iterations++
    }

    reply.send({ burnedMs: ms, iterations })
  })
}
