import { Counter, Gauge, Histogram, Registry, collectDefaultMetrics } from 'prom-client'

export const register = new Registry()
collectDefaultMetrics({ register })

export const webhookReceived = new Counter({
  name: 'detector_webhook_received_total',
  help: 'Total Alertmanager webhook calls received',
  labelNames: ['alertname', 'status'],
  registers: [register],
})

export const actionTotal = new Counter({
  name: 'detector_action_total',
  help: 'Detector actions attempted',
  labelNames: ['alertname', 'action', 'result'],
  registers: [register],
})

export const actionDuration = new Histogram({
  name: 'detector_action_duration_seconds',
  help: 'Detector action duration in seconds',
  labelNames: ['action', 'result'],
  buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5],
  registers: [register],
})

export const activeAlerts = new Gauge({
  name: 'detector_active_alerts',
  help: 'Number of alerts currently being tracked',
  registers: [register],
})

export const cooldownSkips = new Counter({
  name: 'detector_cooldown_skips_total',
  help: 'Actions skipped due to cool-down',
  labelNames: ['alertname', 'action'],
  registers: [register],
})
