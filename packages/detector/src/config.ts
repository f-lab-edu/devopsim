export interface DetectorConfig {
  port: number
  prometheusUrl: string
  targetNamespace: string
  targetLabelSelector: string
  coolDownMs: number
  errorRateThreshold: number
  protectMinReplicas: boolean
}

export function loadConfig(): DetectorConfig {
  return {
    port: Number(process.env.PORT ?? 3000),
    prometheusUrl:
      process.env.PROMETHEUS_URL ?? 'http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090',
    targetNamespace: process.env.TARGET_NAMESPACE ?? 'api',
    targetLabelSelector: process.env.TARGET_LABEL_SELECTOR ?? 'app.kubernetes.io/name=api',
    coolDownMs: Number(process.env.COOL_DOWN_MS ?? 5 * 60_000),
    errorRateThreshold: Number(process.env.ERROR_RATE_THRESHOLD ?? 0.01),
    protectMinReplicas: process.env.PROTECT_MIN_REPLICAS !== 'false',
  }
}
