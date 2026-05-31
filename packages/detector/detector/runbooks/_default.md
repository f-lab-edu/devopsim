# Default Runbook

알려진 시나리오에 매칭되지 않는 trigger에 적용한다.

## Goal
주어진 신호의 원인 가설을 좁히고, 안전한 추가 정보 수집 후 사용자에게 RCA를 보고.

## Workflow
1. trigger payload를 정독해 어떤 리소스(namespace / pod / deployment)와 메트릭·이벤트가 관련됐는지 추출.
2. `kubectl_describe`로 관련 리소스의 status·events·conditions 확인.
3. `kubectl_logs(..., previous=true)`로 최근 종료된 container 로그 확인(있다면).
4. `alertmanager_list_alerts(state="active")`로 동시에 활성화된 다른 alert 확인.
5. 시간대를 명확히 정하고 `promql_range` / `loki_query_range`로 추가 신호 수집.
6. 가설이 2개 이상이면 각 가설에 대해 가장 명확한 신호 1개로 좁히기.

## Synthesize Findings
- 관찰된 증상 + 시점 + 영향받은 리소스.
- 가장 가능성 높은 가설 1~2개 + 근거.
- 불확실한 영역은 "hypothesis"로 명시 (확정 표현 금지).

## Remediation
- 명확한 가설 + 안전한 조치(예: `restart_deployment`)만 실행.
- 불확실하면 조치하지 말고 사용자에게 보고만.
