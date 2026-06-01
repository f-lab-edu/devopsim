#!/usr/bin/env bash
# Demo 1: api 5xx 에러를 인위적으로 만들어 HighErrorRate alert을 발화시킨다.
# detector는 Alertmanager poller로 이걸 받고, runbook alert-high-error-rate 를
# fetch해 분포 분석 + 최근 deploy 회귀를 추적하는 RCA를 작성한다.
# 자율 조치는 하지 않음 — 코드 fix가 정답인 시나리오로 'RCA의 가치'에 집중.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

step "사전 점검"
require_detector_running
ok "detector Ready"

step "/chaos/db/error 반복 호출 — HighErrorRate alert 발화 유도"
# rule: sum(rate(app_errors_total[5m])) / sum(rate(http_requests_total[5m])) > 0.01 for 5m
# 빠르게 비율을 끌어올리려면 짧은 시간에 다회 호출.
for i in $(seq 1 30); do
  curl -fsS "$API_HOST/chaos/db/error" >/dev/null 2>&1 || true
done
ok "/chaos/db/error 30회 호출 완료"

step "Alert 평가 + detector alertmanager poller 주기까지 대기 (최대 7분)"

wait_for_investigate_done "'source': 'alertmanager'.*HighErrorRate" 420

ok "Demo 1 완료. Slack RCA 확인 — 5xx 분포 / 최근 deploy 시점 / rollback 권고가 포함되어야 함."
