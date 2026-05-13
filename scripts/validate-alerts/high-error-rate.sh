#!/usr/bin/env bash
# HighErrorRate alert 검증.
# expr: sum(rate(app_errors_total[5m])) / sum(rate(http_requests_total[5m])) > 0.01
# for: 5m → 약 5.5분 후 Firing.
# 전략: 정상 트래픽 + 의도적 500 에러를 1% 초과 비율로 섞어서 발생.
set -euo pipefail

API="${API:-http://k8s-api-api-426e66a22a-1078713864.us-east-2.elb.amazonaws.com}"
DURATION="${1:-360}"

echo "HighErrorRate 발현 시도 — ${DURATION}s 동안 정상:500 = 9:1 비율 트래픽"
echo "for: 5m이라 약 5.5분 후 fire 예상"

END=$(($(date +%s) + DURATION))
COUNT=0
ERR=0
while [ "$(date +%s)" -lt "$END" ]; do
  R=$((RANDOM % 10))
  if [ "$R" -lt 1 ]; then
    # 1/10 → /chaos/db/error (500)
    curl -sS -o /dev/null "$API/chaos/db/error" || true
    ERR=$((ERR + 1))
  else
    # 9/10 → 정상 요청
    curl -sS -o /dev/null "$API/api/items/popular"
  fi
  COUNT=$((COUNT + 1))
  if [ $((COUNT % 20)) -eq 0 ]; then
    sleep 0.2
  fi
done

echo "Done — total=$COUNT errors=$ERR (rate ~$(echo "scale=3; $ERR/$COUNT" | bc))"
