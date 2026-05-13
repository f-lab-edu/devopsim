#!/usr/bin/env bash
# HighLatencyP95 alert 검증.
# expr: histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m]))) > 0.5
# for: 5m
# 전략: /chaos/db/slow?seconds=1로 1초 지연 요청을 지속 발생 → p95 > 500ms.
set -euo pipefail

API="${API:-http://k8s-api-api-426e66a22a-1078713864.us-east-2.elb.amazonaws.com}"
DURATION="${1:-360}"
CONCURRENCY="${CONCURRENCY:-3}"

echo "HighLatencyP95 발현 시도 — ${DURATION}s 동안 동시 ${CONCURRENCY}개 slow request"
echo "각 요청은 약 1초 지연 → p95 ~1s > 0.5s. for 5m"

cleanup() { kill 0; }
trap cleanup EXIT INT TERM

END=$(($(date +%s) + DURATION))
for _ in $(seq 1 "$CONCURRENCY"); do
  (
    while [ "$(date +%s)" -lt "$END" ]; do
      curl -sS -o /dev/null "$API/chaos/db/slow?seconds=1"
    done
  ) &
done
wait
echo "Done"
