import type { ItemRepository, CreateItemDto, UpdateItemDto } from '../domain/item'
import { AppError } from '../errors'

export function itemService(repo: ItemRepository) {
  return {
    getAll() {
      return repo.findAll()
    },

    async getOne(id: number) {
      const item = await repo.findById(id)
      if (!item) throw new AppError(404, 'Item not found')
      return item
    },

    create(dto: CreateItemDto) {
      return repo.create(dto)
    },

    async update(id: number, dto: UpdateItemDto) {
      if (dto.name === undefined && dto.description === undefined) {
        throw new AppError(400, 'No fields to update')
      }
      const item = await repo.update(id, dto)
      if (!item) throw new AppError(404, 'Item not found')
      return item
    },

    async remove(id: number) {
      const deleted = await repo.remove(id)
      if (!deleted) throw new AppError(404, 'Item not found')
    },
  }
}
