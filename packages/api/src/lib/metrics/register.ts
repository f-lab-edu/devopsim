import { Registry, collectDefaultMetrics } from 'prom-client'

// 모든 메트릭이 등록되는 단일 Registry. /metrics 응답 시 이 register의 내용을 직렬화.
// (default register 대신 custom register 사용 — 테스트 격리/리셋 용이)
export const register = new Registry()

// Node.js 기본 메트릭 (heap, GC, event loop lag, process_*) 자동 수집
collectDefaultMetrics({ register })
