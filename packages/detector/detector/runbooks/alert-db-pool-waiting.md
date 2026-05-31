# Alert: DBPoolWaiting

`pg_pool_waiting_clients > 0` — application의 DB connection pool에서 대기 client가 있다.

## Goal
pool 고갈의 직접 원인(slow query · 트래픽 spike · pool size 과소)을 좁힌다.

## Workflow
1. `alertmanager_list_alerts(matchers=["alertname=DBPoolWaiting"], state="active")` — 현재 발화 정보 (pool=read 또는 write, namespace).
2. `promql_range(query='pg_pool_waiting_clients{namespace="api"}', lookback="30m", step="15s")` — 대기 client 시계열. 갑작스러운 점프 vs 점진 증가.
3. `promql_range(query='pg_pool_active_connections{namespace="api"}', lookback="30m")` — 활성 connection. pool max에 닿았는지.
4. `promql_range(query='histogram_quantile(0.95, sum by (le) (rate(db_query_duration_seconds_bucket{namespace="api"}[5m])))', lookback="30m")` — p95 query 시간. slow query 원인 여부.
5. 트래픽 상관: `promql_range(query='rate(http_requests_total{namespace="api"}[1m])', lookback="30m")`.
6. `loki_query_range(query='{namespace="api"} |~ "slow|timeout|pool"', lookback="15m")` — 관련 로그.

## Synthesize Findings
- pool 고갈 시점 + 지속시간.
- slow query 패턴(p95 jump) vs 트래픽 spike vs pool size 과소 — 어느 가설인가.
- read pool vs write pool 분리.

## Remediation
- 일시 회복: pool size 상향 (config 변경 → rolling restart) — 사용자에게 권고.
- slow query 원인이면 prepared statement / index 점검 권고.
- 트래픽 spike면 HPA 동작 확인. `kubectl_describe(kind="HorizontalPodAutoscaler", ...)`로 scale 추이. minReplicas 상향 권고.
