import { Counter } from 'prom-client'
import { register } from './register'

export const cacheHits = new Counter({
  name: 'cache_hits_total',
  help: 'Cache hit count',
  labelNames: ['endpoint'],
  registers: [register],
})

export const cacheMisses = new Counter({
  name: 'cache_misses_total',
  help: 'Cache miss count',
  labelNames: ['endpoint'],
  registers: [register],
})

export interface CacheMetrics {
  hit(endpoint: string): void
  miss(endpoint: string): void
}

export const cacheMetrics: CacheMetrics = {
  hit: (e) => cacheHits.inc({ endpoint: e }),
  miss: (e) => cacheMisses.inc({ endpoint: e }),
}
