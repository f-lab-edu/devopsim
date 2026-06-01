#!/usr/bin/env bash
# Detector demo 공용 헬퍼.

set -euo pipefail

API_HOST="${API_HOST:-https://api.devopsim.cloud}"
API_NAMESPACE="${API_NAMESPACE:-api}"
DETECTOR_NAMESPACE="${DETECTOR_NAMESPACE:-detector}"
ANNOTATION_KEY="detector.devopsim.cloud/investigate"

color_blue()  { printf "\033[1;34m%s\033[0m\n" "$*"; }
color_green() { printf "\033[1;32m%s\033[0m\n" "$*"; }
color_red()   { printf "\033[1;31m%s\033[0m\n" "$*"; }
color_yellow(){ printf "\033[1;33m%s\033[0m\n" "$*"; }

step() { color_blue "▶ $*"; }
ok()   { color_green "✓ $*"; }
warn() { color_yellow "⚠ $*"; }
fail() { color_red   "✗ $*"; exit 1; }

require_running_api_pod() {
  local pod
  pod=$(kubectl get pod -n "$API_NAMESPACE" -l app.kubernetes.io/name=api --no-headers 2>/dev/null \
    | awk '$3=="Running" {print $1}' | head -1)
  [[ -n "$pod" ]] || fail "Running api pod not found"
  echo "$pod"
}

require_detector_running() {
  local ready
  ready=$(kubectl get pod -n "$DETECTOR_NAMESPACE" -l app.kubernetes.io/name=detector \
    -o jsonpath='{.items[*].status.containerStatuses[*].ready}' 2>/dev/null)
  [[ "$ready" == "true" ]] || fail "detector pod is not Ready"
}

# detector logs에서 특정 source의 investigate done을 30초~max 동안 기다린다.
# 인자: <expected source string>, <timeout sec>
wait_for_investigate_done() {
  local expected="$1"
  local timeout="${2:-180}"
  local deadline=$(( $(date +%s) + timeout ))
  step "detector investigate 결과 대기 (source=$expected, timeout=${timeout}s)..."
  while (( $(date +%s) < deadline )); do
    local line
    line=$(kubectl logs -n "$DETECTOR_NAMESPACE" deploy/detector --tail=200 2>/dev/null \
      | grep "investigate done" | grep "'source': '$expected'" | tail -1 || true)
    if [[ -n "$line" ]]; then
      ok "investigate done: ${line:0:160}..."
      return 0
    fi
    sleep 5
  done
  fail "timeout — investigate done 메시지 못 받음"
}

# 호출 직전 deployment generation 저장. 호출 후 변화로 자동조치 검증.
read_deployment_generation() {
  local ns="$1"
  local name="$2"
  kubectl get deploy -n "$ns" "$name" -o jsonpath='{.status.observedGeneration}'
}
