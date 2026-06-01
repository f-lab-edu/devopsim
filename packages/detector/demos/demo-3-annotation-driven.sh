#!/usr/bin/env bash
# Demo 3: 사용자가 임의의 pod에 annotation을 달아 detector를 수동 트리거한다.
# 사고가 없어도 SRE가 "이 pod 좀 봐봐"라고 요청하는 흐름.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"

step "사전 점검"
require_detector_running
ok "detector Ready"

POD=$(require_running_api_pod)
ok "대상 pod: $POD"

step "annotation 추가"
kubectl annotate pod -n "$API_NAMESPACE" "$POD" "$ANNOTATION_KEY=true" --overwrite >/dev/null
ok "annotated $POD"

wait_for_investigate_done "annotation" 240

ok "Demo 3 완료. Slack RCA 확인 부탁드립니다."
