export const createItemSchema = {
  body: {
    type: 'object',
    required: ['name'],
    properties: {
      name: { type: 'string', minLength: 1, maxLength: 255 },
      description: { type: 'string' },
    },
    additionalProperties: false,
  },
} as const

export const updateItemSchema = {
  body: {
    type: 'object',
    properties: {
      name: { type: 'string', minLength: 1, maxLength: 255 },
      description: { type: 'string' },
    },
    additionalProperties: false,
    minProperties: 1,
  },
} as const
