import { describe, test, expect, beforeEach, afterEach } from 'vitest'
import type { FastifyInstance } from 'fastify'
import { createTestApp } from './helpers'

describe('POST /items', () => {
  let app: FastifyInstance

  beforeEach(async () => {
    app = await createTestApp()
    await app.pg.query('TRUNCATE TABLE items RESTART IDENTITY')
  })

  afterEach(async () => {
    await app.close()
  })

  // --- ECP: 정상 클래스 ---

  test('정상 요청 → 201 + 생성된 item 반환', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/items',
      payload: { name: '테스트 아이템', description: '설명' },
    })
    expect(res.statusCode).toBe(201)
    const body = res.json()
    expect(body.id).toBeDefined()
    expect(body.name).toBe('테스트 아이템')
    expect(body.description).toBe('설명')
    expect(body.view_count).toBe(0)
  })

  test('description 없이 name만 → 201', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/items',
      payload: { name: '이름만' },
    })
    expect(res.statusCode).toBe(201)
    expect(res.json().description).toBeNull()
  })

  // --- ECP: 비정상 클래스 ---

  test('name 누락 → 400', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/items',
      payload: { description: '이름없음' },
    })
    expect(res.statusCode).toBe(400)
  })

  test('허용되지 않은 필드 포함 → Fastify가 strip 후 201 (additionalProperties 제거)', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/items',
      payload: { name: '아이템', hack: true },
    })
    // Fastify 기본 동작: 추가 필드를 거절이 아닌 제거(strip)하고 처리
    expect(res.statusCode).toBe(201)
    expect(res.json()).not.toHaveProperty('hack')
  })

  // --- BVA: name 경계값 ---

  test('name 0자(빈 문자열) → 400', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/items',
      payload: { name: '' },
    })
    expect(res.statusCode).toBe(400)
  })

  test('name 1자(최솟값) → 201', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/items',
      payload: { name: 'a' },
    })
    expect(res.statusCode).toBe(201)
  })

  test('name 255자(최댓값) → 201', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/items',
      payload: { name: 'a'.repeat(255) },
    })
    expect(res.statusCode).toBe(201)
  })

  test('name 256자(최댓값+1) → 400', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/api/items',
      payload: { name: 'a'.repeat(256) },
    })
    expect(res.statusCode).toBe(400)
  })
})

describe('GET /items/:id', () => {
  let app: FastifyInstance
  let createdId: number

  beforeEach(async () => {
    app = await createTestApp()
    await app.pg.query('TRUNCATE TABLE items RESTART IDENTITY')
    const { rows } = await app.pg.query(
      `INSERT INTO items (name) VALUES ('조회용 아이템') RETURNING id`
    )
    createdId = rows[0].id
  })

  afterEach(async () => {
    await app.close()
  })

  // --- ECP ---

  test('존재하는 id → 200 + item 반환', async () => {
    const res = await app.inject({ method: 'GET', url: `/api/items/${createdId}` })
    expect(res.statusCode).toBe(200)
    expect(res.json().id).toBe(createdId)
  })

  test('존재하지 않는 id → 404', async () => {
    const res = await app.inject({ method: 'GET', url: '/api/items/999999' })
    expect(res.statusCode).toBe(404)
    expect(res.json().message).toBe('Item not found')
  })
})

describe('PUT /items/:id', () => {
  let app: FastifyInstance
  let createdId: number

  beforeEach(async () => {
    app = await createTestApp()
    await app.pg.query('TRUNCATE TABLE items RESTART IDENTITY')
    const { rows } = await app.pg.query(
      `INSERT INTO items (name, description) VALUES ('원본', '원본설명') RETURNING id`
    )
    createdId = rows[0].id
  })

  afterEach(async () => {
    await app.close()
  })

  // --- ECP: 정상 클래스 ---

  test('name만 수정 → 200 + 변경 반영', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: `/api/items/${createdId}`,
      payload: { name: '수정된 이름' },
    })
    expect(res.statusCode).toBe(200)
    expect(res.json().name).toBe('수정된 이름')
    expect(res.json().description).toBe('원본설명')
  })

  test('description만 수정 → 200', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: `/api/items/${createdId}`,
      payload: { description: '수정된 설명' },
    })
    expect(res.statusCode).toBe(200)
    expect(res.json().description).toBe('수정된 설명')
  })

  test('name + description 동시 수정 → 200', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: `/api/items/${createdId}`,
      payload: { name: '새이름', description: '새설명' },
    })
    expect(res.statusCode).toBe(200)
    expect(res.json().name).toBe('새이름')
    expect(res.json().description).toBe('새설명')
  })

  // --- ECP: 비정상 클래스 ---

  test('빈 body → 400', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: `/api/items/${createdId}`,
      payload: {},
    })
    expect(res.statusCode).toBe(400)
  })

  test('존재하지 않는 id → 404', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: '/api/items/999999',
      payload: { name: '수정' },
    })
    expect(res.statusCode).toBe(404)
  })

  // --- BVA: name 경계값 ---

  test('name 1자 수정(최솟값) → 200', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: `/api/items/${createdId}`,
      payload: { name: 'a' },
    })
    expect(res.statusCode).toBe(200)
  })

  test('name 255자 수정(최댓값) → 200', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: `/api/items/${createdId}`,
      payload: { name: 'a'.repeat(255) },
    })
    expect(res.statusCode).toBe(200)
  })

  test('name 256자 수정(최댓값+1) → 400', async () => {
    const res = await app.inject({
      method: 'PUT',
      url: `/api/items/${createdId}`,
      payload: { name: 'a'.repeat(256) },
    })
    expect(res.statusCode).toBe(400)
  })
})

describe('DELETE /items/:id', () => {
  let app: FastifyInstance
  let createdId: number

  beforeEach(async () => {
    app = await createTestApp()
    await app.pg.query('TRUNCATE TABLE items RESTART IDENTITY')
    const { rows } = await app.pg.query(
      `INSERT INTO items (name) VALUES ('삭제용') RETURNING id`
    )
    createdId = rows[0].id
  })

  afterEach(async () => {
    await app.close()
  })

  test('존재하는 id → 204', async () => {
    const res = await app.inject({ method: 'DELETE', url: `/api/items/${createdId}` })
    expect(res.statusCode).toBe(204)
  })

  test('존재하지 않는 id → 404', async () => {
    const res = await app.inject({ method: 'DELETE', url: '/api/items/999999' })
    expect(res.statusCode).toBe(404)
  })
})
