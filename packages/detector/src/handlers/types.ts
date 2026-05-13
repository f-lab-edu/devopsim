// Alertmanager webhook payload (subset). spec:
// https://prometheus.io/docs/alerting/latest/configuration/#webhook_config
export interface AlertPayload {
  status: 'firing' | 'resolved'
  fingerprint: string
  labels: Record<string, string>
  annotations: Record<string, string>
  startsAt: string
  endsAt: string
}

export interface AlertHandler {
  onFiring(alert: AlertPayload): Promise<void>
  onResolved(alert: AlertPayload): Promise<void>
}
