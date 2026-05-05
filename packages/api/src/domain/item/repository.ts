import type { PaginationParams, PaginatedResult } from '@devopsim/shared'
import type { Item } from './entity'
import type { CreateItemDto, UpdateItemDto } from './dto'

export interface ItemRepository {
  findAll(params: PaginationParams): Promise<PaginatedResult<Item>>
  findById(id: number): Promise<Item | null>
  findPopular(limit: number): Promise<Item[]>
  incrementViewCount(id: number): Promise<Item | null>
  create(dto: CreateItemDto): Promise<Item>
  update(id: number, dto: UpdateItemDto): Promise<Item | null>
  remove(id: number): Promise<boolean>
  count(): Promise<number>
}
