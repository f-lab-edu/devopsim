#!/usr/bin/env bash
# DBPoolWaiting alert 검증.
# expr: max(pg_pool_waiting_clients) > 0  AND  max(pg_pool_idle_connections) == 0
# for: 5m
# 전략: /chaos/db/burst로 동시 query 20개 → pool max(10) 초과 → waiting 발생 + idle=0.
# burst가 끝나면 풀이 해소되므로 5분 동안 지속적으로 보내야 함.
set -euo pipefail

API="${API:-http://k8s-api-api-426e66a22a-1078713864.us-east-2.elb.amazonaws.com}"
DURATION="${1:-360}"

echo "DBPoolWaiting 발현 시도 — ${DURATION}s 동안 burst 지속 발생"
echo "count=20, sleep=3 burst를 반복 → pool 항상 고갈 상태. for 5m"

END=$(($(date +%s) + DURATION))
i=0
while [ "$(date +%s)" -lt "$END" ]; do
  curl -sS -o /dev/null "$API/chaos/db/burst?count=20&sleep=3" &
  i=$((i+1))
  if [ $((i % 5)) -eq 0 ]; then
    echo "  burst #$i at $(date +%H:%M:%S)"
  fi
  sleep 2
done
wait
echo "Done — total bursts=$i"
