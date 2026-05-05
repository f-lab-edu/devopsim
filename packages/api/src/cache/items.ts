import type { Redis } from 'ioredis'
import type { Item } from '../domain/item'

const POPULAR_KEY = (limit: number) => `items:popular:${limit}`
const POPULAR_PATTERN = 'items:popular:*'
const POPULAR_TTL_SECONDS = 60

export interface ItemCache {
  getPopular(limit: number): Promise<Item[] | null>
  setPopular(limit: number, items: Item[]): Promise<void>
  invalidatePopular(): Promise<void>
}

export function noopItemCache(): ItemCache {
  return {
    async getPopular() { return null },
    async setPopular() {},
    async invalidatePopular() {},
  }
}

export function redisItemCache(redis: Redis): ItemCache {
  return {
    async getPopular(limit) {
      const cached = await redis.get(POPULAR_KEY(limit))
      return cached ? (JSON.parse(cached) as Item[]) : null
    },
    async setPopular(limit, items) {
      await redis.set(
        POPULAR_KEY(limit),
        JSON.stringify(items),
        'EX',
        POPULAR_TTL_SECONDS
      )
    },
    async invalidatePopular() {
      const keys = await redis.keys(POPULAR_PATTERN)
      if (keys.length > 0) {
        await redis.del(...keys)
      }
    },
  }
}
