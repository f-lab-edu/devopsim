# Alert: HighErrorRate

HTTP 5xx 응답 비율이 임계를 초과했다.

## Goal
어떤 경로/원인으로 5xx가 발생하는지 좁힌다. application bug · 의존성 실패 · resource 고갈 등.

## Workflow
1. `alertmanager_list_alerts(matchers=["alertname=HighErrorRate"])`.
2. `promql_range(query='sum by (route, status_code) (rate(http_requests_total{namespace="<ns>", status_code=~"5.."}[1m]))', lookback="30m")` — route별 5xx 분포.
3. `loki_query_range(query='{namespace="<ns>"} |~ "ERROR|FATAL|panic|stack"', lookback="15m", limit=200)` — 에러 로그.
4. 동시 발생 alert: `alertmanager_list_alerts(state="active")` — DBPoolWaiting · HighCPU · CrashLoopBackOff 등 연관 가설 단서.
5. 의존성 상태: Redis / DB connection / 외부 API 메트릭 확인.
6. 최근 deploy 추적: image tag 변경 시점과 에러 시작 시점 비교.

## Synthesize Findings
- 5xx 발생 route(s) + 비율.
- 로그에서 추출한 직접 원인 메시지.
- 동시 발생 alert (연관 가설).
- 최근 변경과의 상관.

## Remediation
- 최근 deploy가 원인이면 직전 안정 버전 rollback 권고.
- 의존성 실패면 `fetch_runbook`으로 그 의존성 runbook 전환 (예: DBPoolWaiting).
- 일시 spike + 의존성 정상이면 `restart_deployment`로 회복 시도 후 재관찰.
