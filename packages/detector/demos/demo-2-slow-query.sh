#!/usr/bin/env bash
# Demo 2: /chaos/db/slow 를 10분 sustained 호출 → DBSlowQuery alert fire
# → detector alertmanager poller가 받아 operation/pool 라벨 정밀 식별 RCA.
# 자율 조치 없음 — index/쿼리 최적화는 코드 fix.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

step "사전 점검"
require_detector_running
ok "detector Ready"

step "/chaos/db/slow?seconds=3 sustained loop 시작 — 매 5초 × 10분간"
# rule: histogram_quantile(0.95, sum by (le, operation, pool)(rate(db_query_duration_seconds_bucket[5m]))) > 0.1 for 10m
# 한 호출당 3s slow query. 5초 간격으로 120회 → 10분 sustained.
(
  for i in $(seq 1 120); do
    curl -fsS -o /dev/null "$API_HOST/chaos/db/slow?seconds=3" 2>/dev/null || true
    sleep 5
  done
) &
LOOP_PID=$!
trap "kill $LOOP_PID 2>/dev/null || true; wait $LOOP_PID 2>/dev/null || true" EXIT
ok "백그라운드 루프 PID=$LOOP_PID (스크립트 종료 시 자동 정리)"

step "Alert 10분 sustained 평가 + detector poller 대기 (최대 14분)"
wait_for_investigate_done "'source': 'alertmanager'.*(DBSlowQuery|SlowQuery)" 840

ok "Demo 2 완료. Slack RCA 확인 — operation/pool 정밀 식별 + 최적화 권고."
