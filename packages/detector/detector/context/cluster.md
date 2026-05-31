# devopsim 클러스터 컨텍스트

agent가 진단·조치 시 참조할 환경 정보. 이 문서가 그대로 LLM system prompt에 inject된다.

> 참고: 실제 발생하는 장애의 *원인*을 미리 알려주는 cheat sheet가 아니다. 토폴로지·라벨·신호 위치만 제공한다.

## 클러스터
- 이름: `devopsim-prod-cluster`
- 리전: `us-east-2` (AWS)
- 버전: K8s 1.35
- 노드: Karpenter — `t3a.small` (default), `t3a.medium` (Prometheus 노드 affinity)

## Namespace 토폴로지
- `api` — `api` Deployment (Fastify 5 API) + `api-secret` ExternalSecret(RDS 자격증명 등)
- `monitoring` — kube-prometheus-stack, Loki, Alloy(DaemonSet), Grafana, Alertmanager. ExternalSecret: `alertmanager-healthchecks`, `alertmanager-slack`
- `redis` — Redis in-cluster (replicas:1, no PVC)
- `traefik` — Traefik v40.2.0 + Gateway API
- `reloader` — Stakater Reloader (`reloader-reloader` deployment) — Secret 변경 감지 후 의존 Deployment rolling restart
- `external-secrets` — ESO controller (ClusterSecretStore: `aws-secretsmanager`)
- `cert-manager`, `external-dns`, `flux-system`
- `detector` — 자기 자신 (이 프로젝트)

## Public 엔드포인트
- `https://api.devopsim.cloud` — api (HTTP/2, Let's Encrypt prod)
- `https://grafana.devopsim.cloud` — Grafana
- 트래픽 경로: Route 53 → Traefik NLB → Gateway API HTTPRoute → Service

## 주요 Deployment
- `api/api` — Fastify 5, 2~10 replicas (HPA, target CPU 50%), **resources.limits.memory=256Mi**, `/metrics`, `/health`, `/ready`
- `monitoring/kube-prometheus-stack-prometheus`, `monitoring/loki`, `monitoring/alloy` (DaemonSet)
- `redis/redis`
- `traefik/traefik`
- `reloader/reloader-reloader`

## Prometheus 라벨 컨벤션
- 공통: `namespace`, `pod`, `container`, `job`, `instance`, `node`
- HTTP: `route`, `method`, `status_code`
- DB: `pool` ∈ `{read, write}`
- service discovery: kube-prometheus-stack 자동 (PodMonitor / ServiceMonitor)

## Loki 라벨 컨벤션
- `namespace`, `pod`, `container`, `node` — Alloy가 자동 부착
- LogQL 검색 예: `{namespace="api"} |~ "error|FATAL"`

## 주요 PrometheusRule alert
- `HighCPU` — pod CPU 사용률 임계
- `DBPoolWaiting` — `pg_pool_waiting_clients > 0`
- `HighErrorRate` — 5xx 비율 임계
- `Watchdog` — 항상 active (healthchecks.io ping)
- 정의 위치: `infra/flux/clusters/prod/.../prometheus-rules.yaml`

## K8s Event / Pod status 신호 (detector trigger)
- **OOMKilled**: Event resource로 발생 **안 함**. `pod.status.containerStatuses[*].lastState.terminated.reason` 직접 watch 필요. `exitCode == 137`.
- **CrashLoopBackOff**: `Event reason=BackOff` + `pod.status.containerStatuses[*].state.waiting.reason`.
- **FailedScheduling**, **Unhealthy**: Event resource로 정상 발생.

## 외부 Secret (AWS Secrets Manager + ESO)
- `devopsim-prod/detector/anthropic-api-key`
- `devopsim-prod/detector/slack-webhook`
- `devopsim-prod/alertmanager/slack`
- `devopsim-prod/alertmanager/healthchecks`
- `devopsim-prod/rds/master`

## Slack
- `#devopsim-alerts` — Alertmanager(사람) + detector(RCA 리포트)
- critical alert만 `@here` mention
