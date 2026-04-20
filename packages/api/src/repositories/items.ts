import type { Pool } from 'pg'
import type { Item, ItemRepository } from '../domain/item'
import { dbQueryDuration, dbConnectionErrors } from '../routes/metrics'

async function measured<T>(operation: string, fn: () => Promise<T>): Promise<T> {
  const end = dbQueryDuration.startTimer({ operation })
  try {
    const result = await fn()
    end()
    return result
  } catch (err) {
    end()
    dbConnectionErrors.inc()
    throw err
  }
}

export function pgItemRepository(db: Pool): ItemRepository {
  return {
    findAll() {
      return measured('findAll', async () => {
        const { rows } = await db.query<Item>(
          'SELECT * FROM items ORDER BY created_at DESC'
        )
        return rows
      })
    },

    findById(id) {
      return measured('findById', async () => {
        const { rows } = await db.query<Item>(
          'SELECT * FROM items WHERE id = $1',
          [id]
        )
        return rows[0] ?? null
      })
    },

    create(dto) {
      return measured('create', async () => {
        const { rows } = await db.query<Item>(
          'INSERT INTO items (name, description) VALUES ($1, $2) RETURNING *',
          [dto.name, dto.description ?? null]
        )
        return rows[0]
      })
    },

    update(id, dto) {
      return measured('update', async () => {
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

    remove(id) {
      return measured('remove', async () => {
        const { rowCount } = await db.query(
          'DELETE FROM items WHERE id = $1',
          [id]
        )
        return (rowCount ?? 0) > 0
      })
    },
  }
}
