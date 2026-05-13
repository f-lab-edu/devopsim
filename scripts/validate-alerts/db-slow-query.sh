#!/usr/bin/env bash
# DBSlowQuery alert 검증.
# expr: histogram_quantile(0.95, sum by (le, operation) (rate(db_query_duration_seconds_bucket[5m]))) > 0.1
# for: 10m
# 전략: /chaos/db/slow?seconds=1을 지속 호출 → operation="(chaos endpoint를 doing pg_sleep)"의 p95 ~1s.
# NOTE: chaos endpoint는 measureDbQuery로 감싸지지 않음 → 실제로는 어떤 operation 라벨에도 잡히지 않을 수 있음.
#       대안: /api/items/:id 같은 정상 요청을 빠르게 보내면서 한 쪽 슬로우 쿼리도 섞는 방식.
#       일단 chaos/db/slow로 시도 + items 트래픽 섞기.
set -euo pipefail

API="${API:-http://k8s-api-api-426e66a22a-1078713864.us-east-2.elb.amazonaws.com}"
DURATION="${1:-700}"

echo "DBSlowQuery 발현 시도 — ${DURATION}s 동안 slow + 정상 요청 혼합"
echo "for 10m. 주의: chaos/db/slow는 operation 라벨이 없을 수 있어 정상 endpoint 트래픽도 같이 발생"

cleanup() { kill 0; }
trap cleanup EXIT INT TERM

END=$(($(date +%s) + DURATION))

# slow chaos
(
  while [ "$(date +%s)" -lt "$END" ]; do
    curl -sS -o /dev/null "$API/chaos/db/slow?seconds=1"
  done
) &

# 정상 트래픽 (operation 라벨 점유)
(
  while [ "$(date +%s)" -lt "$END" ]; do
    curl -sS -o /dev/null "$API/api/items/popular"
    sleep 0.5
  done
) &

wait
echo "Done"
