import { describe, test, expect, vi, beforeEach } from 'vitest'
import { buildApp } from '../app'
import type { PrometheusClient } from '../services/prometheus'
import type { KubernetesClient } from '../services/kubernetes'

function makeWebhookPayload(opts: { status?: 'firing' | 'resolved'; fingerprint?: string } = {}) {
  return {
    version: '4',
    groupKey: 'g',
    status: opts.status ?? 'firing',
    receiver: 'detector-webhook',
    alerts: [
      {
        status: opts.status ?? 'firing',
        fingerprint: opts.fingerprint ?? 'fp-1',
        labels: { alertname: 'HighErrorRate', severity: 'warning', service: 'api' },
        annotations: {},
        startsAt: new Date().toISOString(),
        endsAt: new Date().toISOString(),
      },
    ],
  }
}

describe('bad-pod-evict handler — HighErrorRate', () => {
  let prom: PrometheusClient & { query: ReturnType<typeof vi.fn> }
  let k8s: KubernetesClient & {
    listPods: ReturnType<typeof vi.fn>
    deletePod: ReturnType<typeof vi.fn>
    getDeploymentMinReplicas: ReturnType<typeof vi.fn>
  }

  beforeEach(() => {
    prom = {
      query: vi.fn(),
    } as never
    k8s = {
      listPods: vi.fn().mockResolvedValue([]),
      deletePod: vi.fn().mockResolvedValue(undefined),
      getDeploymentMinReplicas: vi.fn().mockResolvedValue(2),
    } as never
  })

  test('top1 pod이 threshold 이상이면 evict', async () => {
    prom.query.mockResolvedValue([
      { metric: { pod: 'api-aaa' }, value: 0.05 },
      { metric: { pod: 'api-bbb' }, value: 0.001 },
    ])

    const app = buildApp({ logger: false, prom, k8s, config: { errorRateThreshold: 0.01, protectMinReplicas: true } })
    await app.ready()

    const res = await app.inject({ method: 'POST', url: '/webhook', payload: makeWebhookPayload() })
    expect(res.statusCode).toBe(200)
    expect(k8s.deletePod).toHaveBeenCalledWith('api', 'api-aaa')
    expect(k8s.deletePod).toHaveBeenCalledTimes(1)

    await app.close()
  })

  test('threshold 미만이면 skip', async () => {
    prom.query.mockResolvedValue([{ metric: { pod: 'api-aaa' }, value: 0.005 }])

    const app = buildApp({ logger: false, prom, k8s, config: { errorRateThreshold: 0.01 } })
    await app.ready()

    await app.inject({ method: 'POST', url: '/webhook', payload: makeWebhookPayload() })
    expect(k8s.deletePod).not.toHaveBeenCalled()
    await app.close()
  })

  test('replicas == 1 + protectMinReplicas=true → skip (다운타임 방지)', async () => {
    prom.query.mockResolvedValue([{ metric: { pod: 'api-aaa' }, value: 0.5 }])
    k8s.getDeploymentMinReplicas.mockResolvedValue(1)

    const app = buildApp({ logger: false, prom, k8s, config: { errorRateThreshold: 0.01, protectMinReplicas: true } })
    await app.ready()

    await app.inject({ method: 'POST', url: '/webhook', payload: makeWebhookPayload() })
    expect(k8s.deletePod).not.toHaveBeenCalled()
    await app.close()
  })

  test('cool-down 안에 같은 pod이 다시 top1이면 skip', async () => {
    prom.query.mockResolvedValue([{ metric: { pod: 'api-aaa' }, value: 0.5 }])

    const app = buildApp({
      logger: false, prom, k8s,
      config: { errorRateThreshold: 0.01, coolDownMs: 60_000 },
    })
    await app.ready()

    // 첫 webhook — evict 실행
    await app.inject({ method: 'POST', url: '/webhook', payload: makeWebhookPayload({ fingerprint: 'fp-1' }) })
    expect(k8s.deletePod).toHaveBeenCalledTimes(1)

    // 같은 pod이 다시 top1 — cool-down으로 skip
    await app.inject({ method: 'POST', url: '/webhook', payload: makeWebhookPayload({ fingerprint: 'fp-2' }) })
    expect(k8s.deletePod).toHaveBeenCalledTimes(1)

    await app.close()
  })

  test('resolved webhook은 evict 안 함', async () => {
    const app = buildApp({ logger: false, prom, k8s })
    await app.ready()

    await app.inject({
      method: 'POST',
      url: '/webhook',
      payload: makeWebhookPayload({ status: 'resolved' }),
    })
    expect(k8s.deletePod).not.toHaveBeenCalled()
    expect(prom.query).not.toHaveBeenCalled()
    await app.close()
  })

  test('등록 안 된 alertname은 무시', async () => {
    const app = buildApp({ logger: false, prom, k8s })
    await app.ready()

    const body = makeWebhookPayload()
    body.alerts[0].labels.alertname = 'SomeOtherAlert'

    const res = await app.inject({ method: 'POST', url: '/webhook', payload: body })
    expect(res.statusCode).toBe(200)
    expect(k8s.deletePod).not.toHaveBeenCalled()
    await app.close()
  })
})
