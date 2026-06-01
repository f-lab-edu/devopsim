#!/usr/bin/env bash
# Demo 3: api Deployment의 image를 일부러 존재하지 않는 tag로 변경 → 새 pod이
# ImagePullBackOff/ErrImagePull. K8s event Failed 등 발생 → detector trigger.
# detector는 kubectl_rollout_history로 직전 revision의 image tag와 비교해
# rollback 권고 RCA. 자율 조치는 하지 않는다 (image 변경 권한은 의도적으로 없음).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

step "사전 점검"
require_detector_running
ok "detector Ready"

step "현재 api image 백업"
CURRENT_IMAGE=$(kubectl get deploy -n "$API_NAMESPACE" api -o jsonpath='{.spec.template.spec.containers[0].image}')
ok "현재 image: $CURRENT_IMAGE"

cleanup() {
  warn "복구: api image를 $CURRENT_IMAGE 로 되돌림"
  kubectl set image -n "$API_NAMESPACE" deploy/api "api=$CURRENT_IMAGE" --record 2>/dev/null || true
  kubectl rollout status -n "$API_NAMESPACE" deploy/api --timeout=180s 2>&1 | tail -2 || true
}
trap cleanup EXIT

step "api image를 broken tag로 변경 — ImagePullBackOff 유도"
BROKEN_IMAGE="893286712531.dkr.ecr.us-east-2.amazonaws.com/devopsim/api:0.0.0-nonexistent"
kubectl set image -n "$API_NAMESPACE" deploy/api "api=$BROKEN_IMAGE" >/dev/null
ok "image set → $BROKEN_IMAGE"

step "K8s event Failed/ImagePullBackOff 발생 대기"
sleep 25

wait_for_investigate_done "'source': 'k8s_event'.*'reason': '(Failed|FailedScheduling|BackOff)'" 240

ok "Demo 3 완료. Slack RCA 확인 — rollout_history 비교 + rollback 권고가 포함되어야 함."
