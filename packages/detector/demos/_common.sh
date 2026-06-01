#!/usr/bin/env bash
# Detector demo 공용 헬퍼.

set -euo pipefail

API_HOST="${API_HOST:-https://api.devopsim.cloud}"
API_NAMESPACE="${API_NAMESPACE:-api}"
DETECTOR_NAMESPACE="${DETECTOR_NAMESPACE:-detector}"
REDIS_NAMESPACE="${REDIS_NAMESPACE:-redis}"
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

# detector logs에서 investigate done 라인을 찾되, 호출 시점 이후 발생한 것만 매칭한다.
# 인자: <grep -E regex>, <timeout sec>, <since 'NOWs' 단위 — 호출 직전 시각으로부터 몇 초까지 lookback>
#
# false-positive 회피: 이전 demo의 잔재 라인을 기준 시각 이전이라 cut.
wait_for_investigate_done() {
  local pattern="$1"
  local timeout="${2:-240}"
  local now=$(date +%s)
  local deadline=$(( now + timeout ))
  step "detector investigate 대기 (pattern=$pattern, timeout=${timeout}s)..."
  while (( $(date +%s) < deadline )); do
    local elapsed=$(( $(date +%s) - now ))
    local since_arg="${elapsed}s"
    # 단, 'elapsed=0' 이면 since=0s가 의미 없으니 최소 5s.
    if (( elapsed < 5 )); then since_arg="5s"; fi
    local line
    line=$(kubectl logs -n "$DETECTOR_NAMESPACE" deploy/detector --since="$since_arg" 2>/dev/null \
      | grep "investigate done" | grep -E "$pattern" | tail -1 || true)
    if [[ -n "$line" ]]; then
      ok "investigate done: ${line:0:200}..."
      return 0
    fi
    sleep 5
  done
  fail "timeout — investigate done(pattern=$pattern) 메시지 못 받음"
}

read_deployment_generation() {
  local ns="$1"
  local name="$2"
  kubectl get deploy -n "$ns" "$name" -o jsonpath='{.status.observedGeneration}'
}
