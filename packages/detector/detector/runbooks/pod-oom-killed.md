# Pod OOMKilled

container가 kernel OOM으로 종료됐다. `pod.status.containerStatuses[*].lastState.terminated.reason=OOMKilled`, `exitCode=137`.

## Goal
어떤 container가 왜 메모리를 다 썼는지 좁힌다. 일시 회복(restart)과 영구 권고(limit 상향)를 구분한다.

## Workflow
1. `kubectl_describe(kind="Pod", namespace=<ns>, name=<pod>)` — 최근 Events + container statuses + resource limits.
2. `kubectl_logs(namespace=<ns>, pod=<pod>, previous=true, tail_lines=200)` — 죽기 직전 로그. "out of memory" / traceback / 명시적 에러 키워드.
3. `promql_range(query='container_memory_working_set_bytes{pod=~"<pod>.*"}', lookback="30m", step="30s")` — 메모리 시계열. 정상→limit 도달 시각.
4. `promql_query(query='kube_pod_container_resource_limits{pod=~"<pod>.*", resource="memory"}')` — limit 값.
5. 동일 Deployment의 다른 Pod도 같은 패턴? `kubectl_get(kind="Pod", namespace=<ns>)`로 deployment-wide vs 단일 인스턴스 구분.
6. 트래픽 상관: `promql_range(query='rate(http_requests_total{namespace="<ns>"}[1m])', lookback="30m")`.

## Synthesize Findings
- 메모리 시계열 곡선 (정상 baseline → limit 도달 시각).
- 단일 Pod vs Deployment-wide 패턴.
- 트래픽 spike와 동조(load 의존 누수) 여부.
- 의심되는 직접 원인 (hypothesis).

## Remediation
- 즉시 회복: `restart_deployment(<deployment>, <ns>)` — in-progress 정리.
- 영구 권고(보고만): memory limit 상향, HPA target memory 조정, 메모리 누수 원인 코드 fix.
