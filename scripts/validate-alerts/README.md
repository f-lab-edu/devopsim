# alert 검증 스크립트

`infra/flux/clusters/prod/infrastructure/configs/prometheus-rules.yaml`에 정의된 8개 alert를 prod에서 실제로 fire 시키기 위한 스크립트 모음.

## 공통 환경변수

```bash
export API="http://k8s-api-api-426e66a22a-1078713864.us-east-2.elb.amazonaws.com"
```

## alert vs 발현 방법

| alert | 스크립트 | 발현 시간 (interval 30s 가정) | 위험도 |
|---|---|---|---|
| APIDown | `api-down.sh` | for 1m → ~1.5m | **HIGH** (scale=0, 가용성 손실) |
| HighErrorRate | `high-error-rate.sh` | for 5m → ~5.5m | low (500만 발생, 정상 트래픽 영향 X) |
| HighLatencyP95 | `high-latency-p95.sh` | for 5m → ~5.5m | low (chaos endpoint만) |
| CacheLowHitRatio | `cache-low-hit-ratio.sh` | for 10m → ~10.5m | low (cache flush 반복) |
| DBPoolWaiting | `db-pool-waiting.sh` | for 5m → ~5.5m | medium (pool burst, 잠시 정상 요청 영향 가능) |
| DBSlowQuery | `db-slow-query.sh` | for 10m → ~10.5m | low (chaos endpoint만) |
| PrometheusHighMemory | — | — | 인위 시뮬 보류 (cardinality 폭발 필요) |
| PrometheusScrapeFailure | `scrape-failure.sh` | for 3m → ~3.5m | medium (ServiceMonitor selector 변경, prod 메트릭 일시 끊김) |
| Watchdog | — | 정상 시 healthchecks ping. Alertmanager pod 정지로 검증 가능. **수동만 권장** |

## 검증 절차 공통

1. **Prometheus** UI에서 alert state Pending → Firing 전이 확인
   - `kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090`
   - http://localhost:9090/alerts
2. **Slack** #devopsim-alerts 메시지 수신 (warning은 일반, critical은 @here)
3. 조건 해소 후 자동 resolved 메시지 도착

## 실행 패턴

```bash
# 예: DBPoolWaiting (5분 빌드업 + 5분 추가 안정성 = 약 10분)
./scripts/validate-alerts/db-pool-waiting.sh

# alert 발현되면 Ctrl+C 후 조건 해소 → resolved 메시지 확인
```

## 안전 가이드

- **prod에서 검증**하는 게 의미 있음 (스크립트가 prod ALB로 호출)
- 작업 전 Slack에 "alert validation 진행" 공지 권장
- `APIDown`, `PrometheusScrapeFailure`는 진짜로 서비스/메트릭이 끊기니 짧게만
- 모든 스크립트는 Ctrl+C로 즉시 중단 가능. 중단 시 원상 복귀 (cleanup 함수)
