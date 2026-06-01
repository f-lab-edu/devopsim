#!/usr/bin/env bash
# Demo 2: api pod에 memory-leak을 주입해 OOMKilled를 유발한다.
# detector가 pod_status update를 받아 pod-oom-killed runbook을 fetch하고
# 즉시 회복 + 영구 권고를 포함한 RCA를 Slack에 작성한다.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

step "사전 점검"
require_detector_running
ok "detector Ready"

GEN_BEFORE=$(read_deployment_generation "$API_NAMESPACE" api)
echo "  generation_before=$GEN_BEFORE"

step "/chaos/memory-leak 시작 (mbPerTick=50, intervalMs=200) — 빠른 누수"
curl -fsS -X POST "$API_HOST/chaos/memory-leak?mbPerTick=50&intervalMs=200" \
  || fail "/chaos/memory-leak 호출 실패 (CHAOS_DANGEROUS_ENABLED=true 확인)"

step "OOMKilled 발생까지 대기 (memory limit 도달)"
sleep 60

step "OOMKilled 발생 확인"
oom=$(kubectl get pod -n "$API_NAMESPACE" -l app.kubernetes.io/name=api \
  -o jsonpath='{.items[*].status.containerStatuses[*].lastState.terminated.reason}' 2>/dev/null)
echo "  terminated reasons: $oom"
if echo "$oom" | grep -q OOMKilled; then
  ok "OOMKilled 감지됨"
else
  warn "OOMKilled 아직 안 잡힘. detector가 BackOff event로 받을 수 있음"
fi

wait_for_investigate_done "pod_status\\|k8s_event" 240

step "조치 결과 검증 (OOM runbook 권장은 restart_deployment 또는 RCA만)"
GEN_AFTER=$(read_deployment_generation "$API_NAMESPACE" api)
echo "  generation_after=$GEN_AFTER"
if (( GEN_AFTER > GEN_BEFORE )); then
  ok "detector가 restart_deployment 호출 (즉시 회복)"
else
  ok "detector가 자동 조치 보류 (RCA + 권고만). 영구 fix는 limit 상향 — Slack RCA 확인"
fi

ok "Demo 2 완료. Slack RCA 확인 부탁드립니다."
