import type { AlertHandler } from './types'

export class HandlerRegistry {
  private handlers = new Map<string, AlertHandler>()

  register(alertname: string, handler: AlertHandler) {
    this.handlers.set(alertname, handler)
  }

  get(alertname: string): AlertHandler | undefined {
    return this.handlers.get(alertname)
  }
}
