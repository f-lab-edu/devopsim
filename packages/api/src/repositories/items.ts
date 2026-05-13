import type { Item, ItemRepository, PaginationParams } from '../domain/item'
import type { DbPools } from '../plugins/db'
import { measureDbQuery } from '../lib/metrics'

export function pgItemRepository({ read, write }: DbPools): ItemRepository {
  return {
    async findAll({ page, limit }: PaginationParams) {
      return measureDbQuery('findAll', 'read', async () => {
        const offset = (page - 1) * limit
        const { rows } = await read.query<Item & { total_count: string }>(
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
      return measureDbQuery('findById', 'read', async () => {
        const { rows } = await read.query<Item>(
          'SELECT * FROM items WHERE id = $1',
          [id]
        )
        return rows[0] ?? null
      })
    },

    async findPopular(limit) {
      return measureDbQuery('findPopular', 'read', async () => {
        const { rows } = await read.query<Item>(
          'SELECT * FROM items ORDER BY view_count DESC, id ASC LIMIT $1',
          [limit]
        )
        return rows
      })
    },

    async incrementViewCount(id) {
      return measureDbQuery('incrementViewCount', 'write', async () => {
        const { rows } = await write.query<Item>(
          'UPDATE items SET view_count = view_count + 1 WHERE id = $1 RETURNING *',
          [id]
        )
        return rows[0] ?? null
      })
    },

    async create(dto) {
      return measureDbQuery('create', 'write', async () => {
        const { rows } = await write.query<Item>(
          'INSERT INTO items (name, description) VALUES ($1, $2) RETURNING *',
          [dto.name, dto.description ?? null]
        )
        return rows[0]
      })
    },

    async update(id, dto) {
      return measureDbQuery('update', 'write', async () => {
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
        const { rows } = await write.query<Item>(
          `UPDATE items SET ${fields.join(', ')} WHERE id = $${idx} RETURNING *`,
          values
        )
        return rows[0] ?? null
      })
    },

    async remove(id) {
      return measureDbQuery('remove', 'write', async () => {
        const { rowCount } = await write.query(
          'DELETE FROM items WHERE id = $1',
          [id]
        )
        return (rowCount ?? 0) > 0
      })
    },

    async count() {
      return measureDbQuery('count', 'read', async () => {
        const { rows } = await read.query<{ count: string }>(
          'SELECT COUNT(*)::text AS count FROM items'
        )
        return parseInt(rows[0].count, 10)
      })
    },
  }
}
