export interface CreateItemDto {
  name: string
  description?: string
}

export interface UpdateItemDto {
  name?: string
  description?: string
}
