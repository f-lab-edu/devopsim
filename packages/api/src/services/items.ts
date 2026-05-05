import type { ItemRepository, CreateItemDto, UpdateItemDto, PaginationParams } from '../domain/item'
import type { ItemCache } from '../cache/items'
import type { CacheMetrics } from '../lib/metrics'
import { AppError } from '../errors'

export function itemService(repo: ItemRepository, cache: ItemCache, metrics: CacheMetrics) {
  return {
    getAll(params: PaginationParams) {
      return repo.findAll(params)
    },

    async getOne(id: number) {
      const item = await repo.incrementViewCount(id)
      if (!item) throw new AppError(404, 'Item not found')
      // view_count 변경 → popular 순위 바뀔 수 있어 popular 캐시 전체 무효화
      await cache.invalidatePopular()
      return item
    },

    async getPopular(limit: number) {
      const cached = await cache.getPopular(limit)
      if (cached) {
        metrics.hit('popular')
        return cached
      }
      metrics.miss('popular')
      const items = await repo.findPopular(limit)
      await cache.setPopular(limit, items)
      return items
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
