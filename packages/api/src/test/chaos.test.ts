import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import type { FastifyInstance } from 'fastify'
import { createTestApp } from './helpers'

describe('POST /chaos/memory-leak', () => {
  let app: FastifyInstance
  const originalFlag = process.env.CHAOS_DANGEROUS_ENABLED

  beforeEach(async () => {
    vi.useFakeTimers()
    app = await createTestApp()
  })

  afterEach(async () => {
    if (process.env.CHAOS_DANGEROUS_ENABLED === 'true') {
      await app.inject({ method: 'POST', url: '/chaos/memory-leak/stop' })
    }
    vi.clearAllTimers()
    vi.useRealTimers()
    await app.close()
    if (originalFlag === undefined) {
      delete process.env.CHAOS_DANGEROUS_ENABLED
    } else {
      process.env.CHAOS_DANGEROUS_ENABLED = originalFlag
    }
  })

  test('CHAOS_DANGEROUS_ENABLED 미설정 → 403', async () => {
    delete process.env.CHAOS_DANGEROUS_ENABLED
    const res = await app.inject({ method: 'POST', url: '/chaos/memory-leak' })
    expect(res.statusCode).toBe(403)
  })

  test('정상 → 202 + started', async () => {
    process.env.CHAOS_DANGEROUS_ENABLED = 'true'
    const res = await app.inject({
      method: 'POST',
      url: '/chaos/memory-leak?mbPerTick=5&intervalMs=500',
    })
    expect(res.statusCode).toBe(202)
    expect(res.json()).toMatchObject({ status: 'started', mbPerTick: 5, intervalMs: 500 })
  })

  test('두 번째 호출 → 409', async () => {
    process.env.CHAOS_DANGEROUS_ENABLED = 'true'
    await app.inject({ method: 'POST', url: '/chaos/memory-leak' })
    const res = await app.inject({ method: 'POST', url: '/chaos/memory-leak' })
    expect(res.statusCode).toBe(409)
    expect(res.json().status).toBe('already_running')
  })

  test('파라미터 clamping', async () => {
    process.env.CHAOS_DANGEROUS_ENABLED = 'true'
    const res = await app.inject({
      method: 'POST',
      url: '/chaos/memory-leak?mbPerTick=1000&intervalMs=50',
    })
    expect(res.json()).toMatchObject({ mbPerTick: 100, intervalMs: 100 })
  })

  test('stop → 200 + released', async () => {
    process.env.CHAOS_DANGEROUS_ENABLED = 'true'
    await app.inject({ method: 'POST', url: '/chaos/memory-leak' })
    const res = await app.inject({ method: 'POST', url: '/chaos/memory-leak/stop' })
    expect(res.statusCode).toBe(200)
    expect(res.json().status).toBe('stopped')
  })

  test('stop without start → 404', async () => {
    process.env.CHAOS_DANGEROUS_ENABLED = 'true'
    const res = await app.inject({ method: 'POST', url: '/chaos/memory-leak/stop' })
    expect(res.statusCode).toBe(404)
  })
})

describe('POST /chaos/crash', () => {
  let app: FastifyInstance
  let exitSpy: ReturnType<typeof vi.spyOn>
  const originalFlag = process.env.CHAOS_DANGEROUS_ENABLED

  beforeEach(async () => {
    vi.useFakeTimers()
    exitSpy = vi.spyOn(process, 'exit').mockImplementation(() => undefined as never)
    app = await createTestApp()
  })

  afterEach(async () => {
    vi.clearAllTimers()
    vi.useRealTimers()
    exitSpy.mockRestore()
    await app.close()
    if (originalFlag === undefined) {
      delete process.env.CHAOS_DANGEROUS_ENABLED
    } else {
      process.env.CHAOS_DANGEROUS_ENABLED = originalFlag
    }
  })

  test('CHAOS_DANGEROUS_ENABLED 미설정 → 403', async () => {
    delete process.env.CHAOS_DANGEROUS_ENABLED
    const res = await app.inject({ method: 'POST', url: '/chaos/crash' })
    expect(res.statusCode).toBe(403)
  })

  test('정상 → 202 + delayMs 후 process.exit(1)', async () => {
    process.env.CHAOS_DANGEROUS_ENABLED = 'true'
    const res = await app.inject({ method: 'POST', url: '/chaos/crash?delayMs=100' })
    expect(res.statusCode).toBe(202)
    expect(res.json()).toMatchObject({ status: 'exiting', delayMs: 100 })
    expect(exitSpy).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(100)
    expect(exitSpy).toHaveBeenCalledWith(1)
  })

  test('파라미터 clamping', async () => {
    process.env.CHAOS_DANGEROUS_ENABLED = 'true'
    const res = await app.inject({ method: 'POST', url: '/chaos/crash?delayMs=99999' })
    expect(res.json().delayMs).toBe(5000)
  })
})
