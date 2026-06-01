# Detector demos

devopsim/detector의 가치를 시연하는 5개 시나리오. 자율 조치는 한정적이고
**RCA(=의사결정 압축)** 가 핵심 가치라는 컨셉.

## 시나리오 매트릭스

| Demo | 트리거 | detector 행동 | 어필 가치 |
|---|---|---|---|
| 1 (`error-rate-regression`) | `/chaos/db/error` 다회 → HighErrorRate alert | 5xx 분포 분석 + `kubectl_rollout_history` 로 최근 deploy 회귀 추적 → rollback 권고 | RCA + 회귀 추적 |
| 2 (`slow-query`) | `/chaos/db/slow` 다회 → DBSlowQuery alert | operation/pool 라벨로 정밀 식별 + index/쿼리 최적화 권고 | RCA 정밀 진단 |
| 3 (`image-pull-error`) | `kubectl set image` 로 broken tag → ImagePullBackOff | `rollout_history` 로 직전 image 비교 → rollback 권고 (스크립트가 자동 복구) | RCA + image rollback 회귀 추적 |
| 4 (`annotation`) | `kubectl annotate pod` | 자유 조사 → 한국어 RCA | ChatOps 스타일 on-demand 조사 |
| 5 (`redis-down`) | `kubectl delete pod -n redis` | 외부 종속성 실패 식별 + circuit breaker/격리 권고 | 의존성 incident 진단 |

자율 조치(`restart_deployment` / `scale_deployment` / `delete_pod`)는 의도적으로
사용 안 함 — 진짜 회복은 코드/config fix가 정답이고 detector의 가치는 그
의사결정을 5분에 압축해 사람에게 전달하는 것.

## 사전 조건

- `kubectl` 컨텍스트가 EKS prod (devopsim-prod-cluster) 에 연결
- `api.devopsim.cloud` HTTPS 도달 가능
- detector Pod Ready
- 30분 dedup cool-down — 같은 (reason, namespace) trigger는 30분 내 1건만. demo 사이 30분 간격 권장.

## 실행

```bash
bash packages/detector/demos/demo-1-error-rate-regression.sh
bash packages/detector/demos/demo-2-slow-query.sh
bash packages/detector/demos/demo-3-image-pull-error.sh
bash packages/detector/demos/demo-4-annotation.sh
bash packages/detector/demos/demo-5-redis-down.sh
```

## 안전 장치

- detector write tool은 `allowed_namespaces=("api",)` 화이트리스트 + `dry_run` 옵션
- 이 demo들은 **자율 조치 시나리오가 없어** detector가 prod 리소스를 변경하지 않음
- demo 3은 broken image를 일부러 set한 뒤 스크립트가 EXIT trap으로 자동 복구

## 검증 포인트

1. 콘솔에 `investigate done` 라인 + Slack 채널 한국어 RCA
2. Demo 1·3: RCA에 `rollout_history` 호출 흔적 + rollback 권고 포함 여부
3. Demo 2: operation/pool 라벨 식별 정확도
4. Demo 5: redis 의존성 식별 + 격리 권고
5. Grafana `devopsim-detector` 대시보드에서 investigation rate / tokens / tool calls 변화
