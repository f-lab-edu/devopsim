import type { Pool } from 'pg'
import type { Item, ItemRepository } from '../domain/item'

export function pgItemRepository(db: Pool): ItemRepository {
  return {
    async findAll() {
      const { rows } = await db.query<Item>(
        'SELECT * FROM items ORDER BY created_at DESC'
      )
      return rows
    },

    async findById(id) {
      const { rows } = await db.query<Item>(
        'SELECT * FROM items WHERE id = $1',
        [id]
      )
      return rows[0] ?? null
    },

    async create(dto) {
      const { rows } = await db.query<Item>(
        'INSERT INTO items (name, description) VALUES ($1, $2) RETURNING *',
        [dto.name, dto.description ?? null]
      )
      return rows[0]
    },

    async update(id, dto) {
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
    },

    async remove(id) {
      const { rowCount } = await db.query(
        'DELETE FROM items WHERE id = $1',
        [id]
      )
      return (rowCount ?? 0) > 0
    },
  }
}
