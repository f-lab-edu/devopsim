import { Counter } from 'prom-client'
import { register } from './register'

// type 라벨은 'app_error' | 'validation' | 'unhandled' 3종 — cardinality 안전.
// error.message 같은 자유 텍스트는 절대 라벨로 쓰지 말 것 (시계열 폭발).
export const appErrorsTotal = new Counter({
  name: 'app_errors_total',
  help: 'Total application errors handled by the global error handler',
  labelNames: ['type'],
  registers: [register],
})
