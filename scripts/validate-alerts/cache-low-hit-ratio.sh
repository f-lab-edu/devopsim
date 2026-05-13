#!/usr/bin/env bash
# CacheLowHitRatio alert 검증.
# expr: cache_hits / (cache_hits + cache_misses) < 0.5  AND  total > 0.1 rps
# for: 10m
# 전략: traffic 발생 + 매 5초 popular 캐시 flush → miss 비율 극단적으로 높임.
set -euo pipefail

API="${API:-http://k8s-api-api-426e66a22a-1078713864.us-east-2.elb.amazonaws.com}"
DURATION="${1:-700}"

echo "CacheLowHitRatio 발현 시도 — ${DURATION}s 동안 traffic + flush 반복"
echo "5초마다 cache flush → miss/hit 비율 폭증. for 10m"

cleanup() { kill 0; }
trap cleanup EXIT INT TERM

END=$(($(date +%s) + DURATION))

# background: traffic
(
  while [ "$(date +%s)" -lt "$END" ]; do
    curl -sS -o /dev/null "$API/api/items/popular"
    sleep 0.1
  done
) &

# foreground: 5초마다 flush
while [ "$(date +%s)" -lt "$END" ]; do
  curl -sS -X POST -o /dev/null "$API/chaos/cache/flush"
  echo "  flushed at $(date +%H:%M:%S)"
  sleep 5
done
wait
echo "Done"
