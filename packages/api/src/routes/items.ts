import { FastifyInstance } from 'fastify'
import type { itemService } from '../services/items'
import { getItemsSchema, createItemSchema, updateItemSchema } from './schemas/items'

type ItemService = ReturnType<typeof itemService>

export default async function itemsRoute(
  app: FastifyInstance,
  opts: { service: ItemService }
) {
  const { service } = opts

  app.get<{ Querystring: { page: number; limit: number } }>(
    '/items',
    { schema: getItemsSchema },
    async (req) => {
      return service.getAll(req.query)
    }
  )

  app.get<{ Params: { id: string } }>('/items/:id', async (req) => {
    return service.getOne(Number(req.params.id))
  })

  app.post<{ Body: { name: string; description?: string } }>(
    '/items',
    { schema: createItemSchema },
    async (req, reply) => {
      const item = await service.create(req.body)
      reply.code(201).send(item)
    }
  )

  app.put<{ Params: { id: string }; Body: { name?: string; description?: string } }>(
    '/items/:id',
    { schema: updateItemSchema },
    async (req) => {
      return service.update(Number(req.params.id), req.body)
    }
  )

  app.delete<{ Params: { id: string } }>('/items/:id', async (req, reply) => {
    await service.remove(Number(req.params.id))
    reply.code(204).send()
  })
}
