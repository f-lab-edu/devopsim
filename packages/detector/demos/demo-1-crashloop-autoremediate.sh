#!/usr/bin/env bash
# Demo 1: api pod을 여러 번 crash시켜 CrashLoopBackOff 상태로 만든다.
# detector가 BackOff event를 받아 pod-crashloopbackoff runbook을 fetch하고
# restart_deployment를 호출해 자동 회복시키는 흐름을 시연한다.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

step "사전 점검"
require_detector_running
ok "detector Ready"

step "초기 api deployment generation 기록"
GEN_BEFORE=$(read_deployment_generation "$API_NAMESPACE" api)
echo "  generation_before=$GEN_BEFORE"

step "/chaos/crash 3회 연속 호출 — pod이 빠르게 죽도록"
for i in 1 2 3; do
  echo "  → crash $i/3"
  curl -fsS -X POST "$API_HOST/chaos/crash?delayMs=50" || warn "crash $i 호출 실패 (이미 죽었을 수 있음)"
  sleep 8
done

step "kubelet이 BackOff event를 발행할 때까지 대기"
sleep 20

wait_for_investigate_done "k8s_event" 240

step "조치 결과 검증"
GEN_AFTER=$(read_deployment_generation "$API_NAMESPACE" api)
echo "  generation_after=$GEN_AFTER"
if (( GEN_AFTER > GEN_BEFORE )); then
  ok "deployment generation 증가 ($GEN_BEFORE → $GEN_AFTER) — detector가 restart_deployment 호출함"
else
  warn "deployment generation 변화 없음. LLM이 restart 미호출했을 수 있음. Slack RCA에서 판단 사유 확인"
fi

step "최근 api pod 상태"
kubectl get pod -n "$API_NAMESPACE" -l app.kubernetes.io/name=api 2>&1 | tail -5

ok "Demo 1 완료. Slack RCA 확인 부탁드립니다."
