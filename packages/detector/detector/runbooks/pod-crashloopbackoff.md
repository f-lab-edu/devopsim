# Pod CrashLoopBackOff

container가 반복 실패하고 있다. `Event reason=BackOff` + `state.waiting.reason=CrashLoopBackOff`.

## Goal
container가 시작 직후 또는 짧은 시간 내에 종료되는 직접 원인을 파악한다. exit code · 직전 stdout/stderr · readiness probe 실패 여부로 좁힌다.

## Workflow
1. `kubectl_describe(kind="Pod", namespace=<ns>, name=<pod>)` — Events에서 BackOff 빈도/간격, Failed/Created 시퀀스, probe 실패 메시지.
2. `kubectl_logs(namespace=<ns>, pod=<pod>, previous=true, tail_lines=200)` — 죽기 직전 로그. startup failure, missing env, panic/traceback.
3. `kubectl_events(namespace=<ns>, field_selector="involvedObject.name=<pod>")` — 그 Pod의 모든 event 시간순.
4. Deployment-wide인가? `kubectl_get(kind="Pod", namespace=<ns>)`로 동일 deployment 전체 상태.
5. 최근 변경 추적: image tag, env, Secret 변경. Reloader 동작 흔적.

## Synthesize Findings
- container exit code + 마지막 로그 라인 (또는 startup probe 실패).
- backoff 발생 빈도·지속시간.
- Deployment-wide vs 단일 Pod.
- 최근 변경과의 상관.

## Remediation
- 신규 image/config가 원인으로 의심되면 직전 안정 버전 rollback (사용자에게 권고).
- 일시적 외부 의존성 실패면 시간 두고 재관찰. 또는 `restart_deployment`로 강제 재시작.
- 환경 변수/Secret 문제면 `kubectl_describe(kind="Secret", ...)`로 누락 확인 후 사용자에게 보고.
