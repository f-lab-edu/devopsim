export interface Item {
  id: number
  name: string
  description: string | null
  view_count: number
  created_at: Date
  updated_at: Date
}

export interface CreateItemDto {
  name: string
  description?: string
}

export interface UpdateItemDto {
  name?: string
  description?: string
}

export interface ItemRepository {
  findAll(): Promise<Item[]>
  findById(id: number): Promise<Item | null>
  create(dto: CreateItemDto): Promise<Item>
  update(id: number, dto: UpdateItemDto): Promise<Item | null>
  remove(id: number): Promise<boolean>
}
