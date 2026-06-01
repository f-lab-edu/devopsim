# Detector demos

devopsim/detector의 트리거 채널 3종을 시연하는 스크립트.

## 사전 조건

- `kubectl` 컨텍스트가 EKS prod에 연결되어 있을 것
- `api.devopsim.cloud` HTTPS 도달 가능
- `CHAOS_DANGEROUS_ENABLED=true`로 api가 배포되어 있을 것 (Demo 2 필요)
- detector Pod이 Ready
- detector dedup이 30분이므로, 같은 (reason, namespace) trigger를 30분 내 재호출하면 dedup으로 막힌다 — 시연 사이 30분 간격이 안전. 단발 트리거는 그대로 OK.

## 데모 목록

| 스크립트 | 트리거 | 기대 동작 |
|---|---|---|
| `demo-1-crashloop-autoremediate.sh` | `/chaos/crash` × 3회 → CrashLoopBackOff event | runbook `pod-crashloopbackoff` fetch → `restart_deployment` 자율 호출 → deployment generation 증가 + 한국어 RCA |
| `demo-2-oom-rca.sh` | `/chaos/memory-leak` (빠른 누수) → OOMKilled | runbook `pod-oom-killed` fetch → restart 또는 limit 상향 권고를 포함한 한국어 RCA |
| `demo-3-annotation-driven.sh` | `kubectl annotate` (사용자가 직접) | 자유 조사 후 한국어 RCA — 사고 없이도 사람이 점검 요청하는 흐름 |

## 실행

```bash
bash packages/detector/demos/demo-1-crashloop-autoremediate.sh
bash packages/detector/demos/demo-2-oom-rca.sh
bash packages/detector/demos/demo-3-annotation-driven.sh
```

## 안전장치

- detector의 write tool 3종(`restart_deployment` / `scale_deployment` / `delete_pod`)은 `allowed_namespaces=("api",)` 화이트리스트로 제한
- `dry_run=false` 일 때만 실제 수행. `dry_run=true`면 kubectl `--dry-run=server`로 검증만
- 위 외의 변경(예: `kubectl edit`, secret 수정, node drain, RBAC 변경)은 tool로 제공되지 않음 — 임의 변경 불가

## 검증 포인트

각 데모 실행 후:
1. 콘솔에 `investigate done` 라인이 잡히는가
2. (Demo 1·2 자율 조치) deployment `observedGeneration` 변화 — 자율 restart가 일어났는지
3. Slack 채널의 한국어 RCA 메시지
4. Grafana `devopsim-detector` 대시보드의 investigation rate / token usage 변화
