import { FastifyInstance } from 'fastify'
import type { HandlerRegistry } from '../handlers/registry'
import type { AlertPayload } from '../handlers/types'
import { webhookReceived, activeAlerts } from '../lib/metrics'

// Alertmanager webhook body schema (subset). 전체 spec:
// https://prometheus.io/docs/alerting/latest/configuration/#webhook_config
interface AlertmanagerWebhookBody {
  version: string
  groupKey: string
  status: 'firing' | 'resolved'
  receiver: string
  alerts: AlertPayload[]
}

export default async function webhookRoute(
  app: FastifyInstance,
  opts: { registry: HandlerRegistry; activeCount: () => number }
) {
  app.post<{ Body: AlertmanagerWebhookBody }>('/webhook', async (req, reply) => {
    const body = req.body
    if (!body || !Array.isArray(body.alerts)) {
      return reply.code(400).send({ error: 'invalid payload' })
    }

    for (const alert of body.alerts) {
      const alertname = alert.labels?.alertname ?? 'unknown'
      webhookReceived.inc({ alertname, status: alert.status })

      const handler = opts.registry.get(alertname)
      if (!handler) {
        req.log.warn({ alertname }, 'no handler registered')
        continue
      }

      try {
        if (alert.status === 'firing') {
          await handler.onFiring(alert)
        } else {
          await handler.onResolved(alert)
        }
      } catch (err) {
        req.log.error({ err, alertname, fingerprint: alert.fingerprint }, 'handler error')
      }
    }

    activeAlerts.set(opts.activeCount())
    return { ok: true, processed: body.alerts.length }
  })
}
