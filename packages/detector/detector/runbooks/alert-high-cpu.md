# Alert: HighCPU

Pod CPU 사용률이 임계를 초과했다.

## Goal
부하 원인(트래픽 · CPU-bound 처리 · 무한 루프/event loop block)을 좁힌다.

## Workflow
1. `alertmanager_list_alerts(matchers=["alertname=HighCPU"])` — namespace / pod 식별.
2. `promql_range(query='rate(container_cpu_usage_seconds_total{pod=~"<pod>.*"}[1m])', lookback="30m")` — CPU 시계열.
3. `promql_query(query='kube_pod_container_resource_limits{pod=~"<pod>.*", resource="cpu"}')` — limit과 비교 (saturation 여부).
4. 트래픽: `promql_range(query='rate(http_requests_total{namespace="<ns>"}[1m])', lookback="30m")`. CPU와 동조하는지.
5. event loop block 의심: `loki_query_range(query='{namespace="<ns>"} |~ "blocked|timeout|slow"', lookback="15m")`.
6. 동일 Deployment 다른 Pod도 동일한가 — Deployment-wide 부하 vs 단일 Pod 비정상.

## Synthesize Findings
- CPU saturation 시점 + 지속시간.
- 트래픽 동조 / 비동조(내부 작업) 분류.
- 단일 Pod vs Deployment-wide.

## Remediation
- 트래픽 폭증이면 HPA가 자동 scale-out 했는지 확인. `kubectl_describe(kind="Deployment", ...)`로 replicas 추이.
- 단일 Pod 비정상이면 `restart_deployment` 또는 해당 Pod `delete_pod`.
- CPU-bound 처리가 정상 패턴이면 CPU limit 상향 권고 (보고만).
