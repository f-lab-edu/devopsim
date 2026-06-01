#!/usr/bin/env bash
# Demo 5: redis pod을 강제 종료하여 외부 종속성 실패 상황을 시뮬.
# api는 Redis miss로 cache hit ratio가 떨어지고 5xx가 발생할 수 있다.
# detector는 어떤 dependency가 문제인지 식별 + 격리/circuit breaker 권고.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

step "사전 점검"
require_detector_running
ok "detector Ready"

step "redis pod 식별"
REDIS_POD=$(kubectl get pod -n "$REDIS_NAMESPACE" --no-headers 2>/dev/null | awk '$3=="Running" {print $1}' | head -1)
[[ -n "$REDIS_POD" ]] || fail "running redis pod 없음 (namespace=$REDIS_NAMESPACE)"
ok "redis pod: $REDIS_POD"

step "redis pod 강제 삭제 — 외부 종속성 실패 유도"
kubectl delete pod -n "$REDIS_NAMESPACE" "$REDIS_POD" --grace-period=0 --force >/dev/null
ok "deleted $REDIS_POD"

step "api 측에서 redis miss/error 발생 대기"
sleep 30

wait_for_investigate_done "'reason': '(BackOff|Unhealthy|Failed|FailedScheduling)'|'alertname': '(CacheLowHitRatio|HighErrorRate)'" 420

ok "Demo 5 완료. Slack RCA 확인 — redis 의존성 실패 식별 + circuit breaker/격리 권고."
