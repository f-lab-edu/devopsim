import { Gauge } from 'prom-client'
import type { ItemRepository } from '../../../domain/item'
import { register } from '../register'

// items 테이블 행 수를 /metrics 응답 시점에 SELECT COUNT(*)로 가져옴.
// Pull 방식 — Push(create/remove마다 inc/dec) 대비 장점:
//   - 다중 인스턴스에서도 항상 일관된 값 (각 Pod이 독립 카운터를 갖지 않음)
//   - DB 직접 수정(다른 서비스, migration)도 자동 반영
// COUNT(*)는 인덱스 스캔이라 ms 단위. /metrics scrape 주기(15~30s)와 균형 OK.
// idempotent: 테스트에서 buildApp이 여러 번 호출돼도 중복 등록 에러 회피.
export function registerItemsTotalGauge(repo: ItemRepository) {
  if (register.getSingleMetric('items_total')) return
  new Gauge({
    name: 'items_total',
    help: 'Total number of items in the database',
    registers: [register],
    async collect() {
      this.set(await repo.count())
    },
  })
}
