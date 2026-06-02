#!/usr/bin/env bash
# Demo 1: /chaos/db/error 를 5분 sustained 호출 → HighErrorRate alert fire
# → detector alertmanager poller가 받아 RCA 작성. runbook alert-high-error-rate
# 의 워크플로를 따라 5xx 분포 + 최근 deploy 회귀를 분석.
# 자율 조치 없음 — 진짜 회복은 코드/image rollback 권고(사람 결정).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

step "사전 점검"
require_detector_running
ok "detector Ready"

step "/chaos/db/error sustained loop 시작 — 매 1초 × 5분간"
# rule: sum(rate(app_errors_total[5m])) / sum(rate(http_requests_total[5m])) > 0.01 for 5m
# 짧은 burst로는 5분 평균 rate가 의미 없게 떨어지므로 백그라운드 루프로 sustained.
(
  for i in $(seq 1 300); do
    curl -fsS -o /dev/null "$API_HOST/chaos/db/error" 2>/dev/null || true
    sleep 1
  done
) &
LOOP_PID=$!
trap "kill $LOOP_PID 2>/dev/null || true; wait $LOOP_PID 2>/dev/null || true" EXIT
ok "백그라운드 루프 PID=$LOOP_PID (스크립트 종료 시 자동 정리)"

step "Alert 평가 5분 sustained + detector poller 주기까지 대기 (최대 10분)"
wait_for_investigate_done "'source': 'alertmanager'.*HighErrorRate" 600

ok "Demo 1 완료. Slack RCA 확인 — 5xx 분포 / 최근 deploy 비교 / rollback 권고."
