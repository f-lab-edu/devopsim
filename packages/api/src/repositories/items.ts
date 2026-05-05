import type { Pool } from 'pg'
import type { Item, ItemRepository, PaginationParams } from '../domain/item'
import { measureDbQuery } from '../lib/metrics'

export function pgItemRepository(db: Pool): ItemRepository {
  return {
    async findAll({ page, limit }: PaginationParams) {
      return measureDbQuery('findAll', async () => {
        const offset = (page - 1) * limit
        const { rows } = await db.query<Item & { total_count: string }>(
          'SELECT *, COUNT(*) OVER() AS total_count FROM items ORDER BY created_at DESC LIMIT $1 OFFSET $2',
          [limit, offset]
        )
        const total = rows.length > 0 ? parseInt(rows[0].total_count) : 0
        return {
          data: rows.map(({ total_count, ...item }) => item as Item),
          total,
          page,
          limit,
        }
      })
    },

    async findById(id) {
      return measureDbQuery('findById', async () => {
        const { rows } = await db.query<Item>(
          'SELECT * FROM items WHERE id = $1',
          [id]
        )
        return rows[0] ?? null
      })
    },

    async findPopular(limit) {
      return measureDbQuery('findPopular', async () => {
        const { rows } = await db.query<Item>(
          'SELECT * FROM items ORDER BY view_count DESC, id ASC LIMIT $1',
          [limit]
        )
        return rows
      })
    },

    async incrementViewCount(id) {
      return measureDbQuery('incrementViewCount', async () => {
        const { rows } = await db.query<Item>(
          'UPDATE items SET view_count = view_count + 1 WHERE id = $1 RETURNING *',
          [id]
        )
        return rows[0] ?? null
      })
    },

    async create(dto) {
      return measureDbQuery('create', async () => {
        const { rows } = await db.query<Item>(
          'INSERT INTO items (name, description) VALUES ($1, $2) RETURNING *',
          [dto.name, dto.description ?? null]
        )
        return rows[0]
      })
    },

    async update(id, dto) {
      return measureDbQuery('update', async () => {
        const fields: string[] = []
        const values: unknown[] = []
        let idx = 1

        if (dto.name !== undefined) {
          fields.push(`name = $${idx++}`)
          values.push(dto.name)
        }
        if (dto.description !== undefined) {
          fields.push(`description = $${idx++}`)
          values.push(dto.description)
        }
        fields.push(`updated_at = NOW()`)
        values.push(id)
        const { rows } = await db.query<Item>(
          `UPDATE items SET ${fields.join(', ')} WHERE id = $${idx} RETURNING *`,
          values
        )
        return rows[0] ?? null
      })
    },

    async remove(id) {
      return measureDbQuery('remove', async () => {
        const { rowCount } = await db.query(
          'DELETE FROM items WHERE id = $1',
          [id]
        )
        return (rowCount ?? 0) > 0
      })
    },

    async count() {
      return measureDbQuery('count', async () => {
        const { rows } = await db.query<{ count: string }>(
          'SELECT COUNT(*)::text AS count FROM items'
        )
        return parseInt(rows[0].count, 10)
      })
    },
  }
}
