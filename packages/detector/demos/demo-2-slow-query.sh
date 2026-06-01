#!/usr/bin/env bash
# Demo 2: pg_sleep으로 의도적 slow query를 다회 발생시켜 DBSlowQuery alert을
# 발화. detector는 어떤 operation/pool의 쿼리가 느린지 정밀 식별 + 권고 RCA.
# 자율 조치 없음 — index/쿼리 최적화는 코드 fix.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

step "사전 점검"
require_detector_running
ok "detector Ready"

step "/chaos/db/slow?seconds=3 반복 호출 — DBSlowQuery alert 발화 유도"
# rule: histogram_quantile(0.95, sum by (le, operation, pool)(rate(db_query_duration_seconds_bucket[5m]))) > 0.1 for 10m
# alert이 fire하려면 10분 sustained 필요. 빠르게 budget 끌어올리려면 백그라운드로 다회.
for i in $(seq 1 15); do
  curl -fsS "$API_HOST/chaos/db/slow?seconds=3" >/dev/null 2>&1 &
done
wait
ok "/chaos/db/slow 15회 동시 호출 완료"

step "10분 sustained 평가 + detector poller 대기 (최대 12분)"

wait_for_investigate_done "'source': 'alertmanager'.*(DBSlowQuery|SlowQuery)" 720

ok "Demo 2 완료. Slack RCA 확인 — operation/pool 라벨로 어떤 쿼리가 느린지 + index/최적화 권고."
