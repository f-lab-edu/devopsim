// @ts-nocheck
/** @type {import('node-pg-migrate').MigrationBuilder} */

exports.up = (pgm) => {
  pgm.createTable('items', {
    id:          { type: 'serial',       primaryKey: true },
    name:        { type: 'varchar(255)', notNull: true },
    description: { type: 'text' },
    view_count:  { type: 'integer',      notNull: true, default: 0 },
    created_at:  { type: 'timestamptz',  notNull: true, default: pgm.func('NOW()') },
    updated_at:  { type: 'timestamptz',  notNull: true, default: pgm.func('NOW()') },
  })
}

exports.down = (pgm) => {
  pgm.dropTable('items')
}
