import type { FastifyBaseLogger } from 'fastify'
import type { AlertHandler, AlertPayload } from './types'
import type { PrometheusClient } from '../services/prometheus'
import type { KubernetesClient } from '../services/kubernetes'
import type { ActionStore } from '../services/state'
import { actionTotal, actionDuration, cooldownSkips } from '../lib/metrics'

const ALERTNAME = 'HighErrorRate'
const ACTION = 'evict_pod'

// pod별 에러율 = (해당 pod의 에러 rate) / (해당 pod의 총 요청 rate).
// http_requests_total / app_errors_total은 ServiceMonitor가 pod 라벨을 자동으로 붙임 (prometheus-operator 기본).
// 분모가 0인 pod는 결과에서 제외됨 (/ 0 → NaN → 결과 vector에서 자동 누락).
const PROMQL = `
  sum by (pod) (rate(app_errors_total{namespace="api"}[5m]))
    /
  sum by (pod) (rate(http_requests_total{namespace="api"}[5m]))
`.trim()

export interface BadPodEvictDeps {
  prom: PrometheusClient
  k8s: KubernetesClient
  store: ActionStore
  namespace: string
  deploymentName: string
  errorRateThreshold: number
  coolDownMs: number
  protectMinReplicas: boolean
  logger: FastifyBaseLogger
}

export function createBadPodEvictHandler(deps: BadPodEvictDeps): AlertHandler {
  const log = deps.logger.child({ handler: 'bad-pod-evict' })

  return {
    async onFiring(alert: AlertPayload) {
      const end = actionDuration.startTimer({ action: ACTION })

      try {
        // 1. pod별 에러율 조회
        const samples = await deps.prom.query(PROMQL)
        if (samples.length === 0) {
          log.info('no pods have request rate — skip')
          actionTotal.inc({ alertname: ALERTNAME, action: ACTION, result: 'skipped' })
          end({ result: 'skipped' })
          return
        }

        // 2. top1 (에러율 가장 높은 pod)
        const top = samples.reduce((a, b) => (a.value > b.value ? a : b))
        const targetPod = top.metric.pod
        const errorRate = top.value
        log.info({ targetPod, errorRate, samples: samples.length }, 'evaluated pod error rates')

        if (errorRate < deps.errorRateThreshold) {
          log.info({ errorRate, threshold: deps.errorRateThreshold }, 'top error rate below threshold — skip')
          actionTotal.inc({ alertname: ALERTNAME, action: ACTION, result: 'skipped' })
          end({ result: 'skipped' })
          return
        }

        // 3. cool-down 체크
        if (deps.store.isOnCoolDown(targetPod, deps.coolDownMs)) {
          log.info({ targetPod }, 'pod on cool-down — skip')
          cooldownSkips.inc({ alertname: ALERTNAME, action: ACTION })
          actionTotal.inc({ alertname: ALERTNAME, action: ACTION, result: 'skipped' })
          end({ result: 'skipped' })
          return
        }

        // 4. minReplicas 보호 — replicas==1인 deployment면 evict 시 다운타임 발생
        if (deps.protectMinReplicas) {
          const replicas = await deps.k8s.getDeploymentMinReplicas(deps.namespace, deps.deploymentName)
          if (replicas <= 1) {
            log.warn({ replicas }, 'deployment at min replicas — refuse to evict (would cause downtime)')
            actionTotal.inc({ alertname: ALERTNAME, action: ACTION, result: 'skipped' })
            end({ result: 'skipped' })
            return
          }
        }

        // 5. evict 실행
        log.info({ targetPod }, 'evicting pod')
        await deps.k8s.deletePod(deps.namespace, targetPod)

        deps.store.recordAction(alert.fingerprint, {
          alertname: ALERTNAME,
          action: ACTION,
          target: targetPod,
          at: Date.now(),
        })

        actionTotal.inc({ alertname: ALERTNAME, action: ACTION, result: 'success' })
        end({ result: 'success' })
      } catch (err) {
        log.error({ err }, 'evict action failed')
        actionTotal.inc({ alertname: ALERTNAME, action: ACTION, result: 'error' })
        end({ result: 'error' })
      }
    },

    async onResolved(alert: AlertPayload) {
      // resolved 시 fingerprint state cleanup. cool-down은 target별이라 유지 (재발 방지)
      deps.store.forgetFingerprint(alert.fingerprint)
      log.info({ fingerprint: alert.fingerprint }, 'alert resolved — state cleaned')
    },
  }
}
