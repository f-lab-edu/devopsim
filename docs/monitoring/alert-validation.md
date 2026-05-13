# Alert 검증 가이드

`infra/flux/clusters/prod/infrastructure/configs/prometheus-rules.yaml`에 정의된 8개 alert가 prod에서 실제 발현되는지, Slack/healthchecks까지 알림이 도달하는지 검증한다.

## 배경 — Prometheus rule evaluation

Prometheus는 단순 query 도구가 아니라 주기적으로 PromQL을 실행하면서 alert state를 굴리는 엔진이다.

- 평가 주기: rule group의 `interval` (우리는 30s)
- 한 cycle에서 일어나는 일:
  1. expr PromQL 실행
  2. 결과 vector의 각 series별 alert state 갱신
     - 결과에 있고 state가 없던 series → `Pending` (activeAt 기록)
     - `Pending`인데 `activeAt + for` 경과 → `Firing`
     - 결과에 없어진 series → `Inactive` (Pending이었으면 리셋, Firing이었으면 resolved)
  3. Firing 결과를 Alertmanager에 HTTP POST
  4. `ALERTS{alertname,alertstate}` series를 TSDB에 기록

`for: 5m`은 "조건이 5분 연속 true"가 아니라 "같은 series가 5분 연속 결과에 포함됨"이다. 라벨이 매 cycle 바뀌면 (예: pod 이름 라벨) for가 매번 리셋되니 주의.

## 검증 절차 (공통)

각 스크립트 실행 후 아래 3곳에서 상태 확인:

### 1) Prometheus UI

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
```

- http://localhost:9090/alerts — alert state (Inactive / Pending / Firing) + activeAt
- http://localhost:9090/graph — expr 직접 실행해서 값 확인

### 2) Alertmanager UI

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093
```

- http://localhost:9093 — 받은 alert 목록 + silence + group/route 매칭

### 3) Slack #devopsim-alerts

- warning: 일반 메시지
- critical: @here 멘션
- resolved: 조건 해소 후 자동 도착

## alert 별 검증 시나리오

### APIDown (critical, for 1m)

```
expr: up{job="serviceMonitor/api/api/0"} == 0
```

| 단계 | 명령 |
|---|---|
| 발현 | `./scripts/validate-alerts/api-down.sh` (kubectl scale deploy/api -n api --replicas=0) |
| 확인 | Prometheus에서 up 시리즈가 0이 되고 약 1.5분 후 Firing |
| 복구 | Ctrl+C (스크립트가 trap으로 원본 replicas 복원) |

### HighErrorRate (warning, for 5m)

```
expr: sum(rate(app_errors_total[5m])) / sum(rate(http_requests_total[5m])) > 0.01
```

| 단계 | 명령 |
|---|---|
| 발현 | `./scripts/validate-alerts/high-error-rate.sh 360` (9:1 정상:500 비율) |
| 확인 | Prometheus expr에서 비율 > 0.01 유지, ~5.5분 후 Firing |
| 복구 | 스크립트 종료 후 자동 — 에러율 떨어지면 5분 이내 resolved |

### HighLatencyP95 (warning, for 5m)

```
expr: histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m]))) > 0.5
```

| 단계 | 명령 |
|---|---|
| 발현 | `./scripts/validate-alerts/high-latency-p95.sh 360` (chaos/db/slow?seconds=1 동시 3개) |
| 확인 | p95가 ~1s로 상승 |
| 복구 | 스크립트 종료 |

### CacheLowHitRatio (warning, for 10m)

```
expr: (cache_hits / (cache_hits + cache_misses)) < 0.5  AND  total rate > 0.1 rps
```

| 단계 | 명령 |
|---|---|
| 발현 | `./scripts/validate-alerts/cache-low-hit-ratio.sh 700` (traffic + 5s마다 flush) |
| 확인 | hit ratio < 50% 유지. for 10m이라 ~10.5분 |
| 복구 | 스크립트 종료. TTL 60s 후 정상 캐시 동작 복귀 |

### DBPoolWaiting (warning, for 5m)

```
expr: max(pg_pool_waiting_clients) > 0  AND  max(pg_pool_idle_connections) == 0
```

| 단계 | 명령 |
|---|---|
| 발현 | `./scripts/validate-alerts/db-pool-waiting.sh 360` (count=20 burst 반복) |
| 확인 | pg_pool_waiting_clients > 0 + idle == 0 동시 유지 |
| 복구 | 스크립트 종료 후 burst 풀이 정리되면 자동 resolved |

### DBSlowQuery (warning, for 10m)

```
expr: histogram_quantile(0.95, sum by (le, operation) (rate(db_query_duration_seconds_bucket[5m]))) > 0.1
```

| 단계 | 명령 |
|---|---|
| 발현 | `./scripts/validate-alerts/db-slow-query.sh 700` (chaos/db/slow + 정상 트래픽) |
| 확인 | db_query_duration_seconds p95 by operation |
| 비고 | chaos endpoint는 measureDbQuery로 감싸지지 않아 operation 라벨이 비어 있을 수 있음. 검증 후 chaos에도 measureDbQuery 적용 검토 필요 |

### PrometheusHighMemory (warning, for 10m)

```
expr: process_resident_memory_bytes{job=~".*prometheus.*"} / 2.147e9 > 0.8
```

**인위 시뮬 보류** — high-cardinality label 폭발이 필요해 정상 트래픽 발생만으론 어려움. 정기 모니터링 dashboard에서 자연 발생 시 확인.

### PrometheusScrapeFailure (warning, for 3m)

```
expr: up == 0
```

| 단계 | 명령 |
|---|---|
| 발현 | `./scripts/validate-alerts/scrape-failure.sh` (ServiceMonitor selector를 잘못된 값으로) |
| 확인 | up==0 series 등장 |
| 복구 | Ctrl+C (selector 원복) |

### Watchdog (always firing)

healthchecks.io로 1분 주기 ping. 정상 = 24시간 내내 ping 도달.

**장애 시뮬:** Alertmanager pod을 일시적으로 죽여서 6분 이상 ping 끊기면 healthchecks가 외부 채널(이메일 등)로 통지.

```bash
# 매우 위험: 모든 alert 라우팅 끊김. 검증 끝나면 즉시 deployment 복원.
kubectl scale -n monitoring statefulset/alertmanager-kube-prometheus-stack-alertmanager --replicas=0
```

## 운영 노트

- 모든 검증은 prod ALB를 직접 hit해서 실제 메트릭 발현. 별도 stage 없음
- 검증 전 Slack에 공지 권장 (예: `:warn: alert validation 진행 중 — 다음 30분간 false alarm 예상`)
- alert 발현 → resolved 한 cycle 끝에 Slack에 두 메시지가 도착해야 정상
- false positive로 알려진 패턴:
  - `pg_pool_waiting_clients > 0` 단독 → collect callback race로 가끔 1. **AND idle==0** 추가로 보완 (PR #54)
  - kube-prometheus-stack 기본 controller-manager/scheduler/etcd alert → EKS는 managed라 X. `defaultRules.rules.*: false`로 비활성화 (PR #54)
