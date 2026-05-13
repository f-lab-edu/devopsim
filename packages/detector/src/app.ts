import Fastify, { FastifyBaseLogger } from 'fastify'
import { logger } from '@devopsim/shared'
import healthRoute from './routes/health'
import metricsRoute from './routes/metrics'
import webhookRoute from './routes/webhook'
import { loadConfig, DetectorConfig } from './config'
import { HandlerRegistry } from './handlers/registry'
import { ActionStore } from './services/state'
import { createPrometheusClient, PrometheusClient } from './services/prometheus'
import { createKubernetesClient, KubernetesClient } from './services/kubernetes'
import { createBadPodEvictHandler } from './handlers/bad-pod-evict'

export interface BuildOpts {
  logger?: boolean
  prom?: PrometheusClient
  k8s?: KubernetesClient
  config?: Partial<DetectorConfig>
}

// 의존성을 옵션으로 주입 가능 — 테스트에서 mock 주입.
// prod에선 옵션 없이 호출하면 실제 client 생성.
export function buildApp(opts: BuildOpts = {}) {
  const app = opts.logger === false
    ? Fastify({ logger: false })
    : Fastify({ loggerInstance: logger as unknown as FastifyBaseLogger })

  const config = { ...loadConfig(), ...opts.config }
  const prom = opts.prom ?? createPrometheusClient(config.prometheusUrl)
  const k8s = opts.k8s ?? createKubernetesClient()
  const store = new ActionStore()
  const registry = new HandlerRegistry()

  registry.register(
    'HighErrorRate',
    createBadPodEvictHandler({
      prom,
      k8s,
      store,
      namespace: config.targetNamespace,
      deploymentName: 'api',
      errorRateThreshold: config.errorRateThreshold,
      coolDownMs: config.coolDownMs,
      protectMinReplicas: config.protectMinReplicas,
      logger: app.log,
    })
  )

  app.decorate('config', config)

  app.register(healthRoute)
  app.register(metricsRoute)
  app.register(webhookRoute, { registry, activeCount: () => store.activeCount() })

  return app
}

declare module 'fastify' {
  interface FastifyInstance {
    config: DetectorConfig
  }
}
