#!/usr/bin/env bash
# APIDown alert 검증.
# expr: up{job="serviceMonitor/api/api/0"} == 0
# for: 1m → 약 1.5분 후 Firing.
# WARNING: replicas=0으로 만들어 서비스 완전 중단. 검증 후 자동 복구.
set -euo pipefail

NS="${NS:-api}"
DEPLOY="${DEPLOY:-api}"

original=$(kubectl get deploy "$DEPLOY" -n "$NS" -o jsonpath='{.spec.replicas}')
echo "현재 replicas=$original — 0으로 스케일 다운"

cleanup() {
  echo ""
  echo "복구: replicas=$original"
  kubectl scale deploy/"$DEPLOY" -n "$NS" --replicas="$original" >/dev/null
}
trap cleanup EXIT INT TERM

kubectl scale deploy/"$DEPLOY" -n "$NS" --replicas=0 >/dev/null
echo "scaled down. up{} == 0 → ~1.5분 후 Firing 예상."
echo "Prometheus /alerts에서 Pending→Firing 확인 후 Ctrl+C로 복구"

while true; do sleep 30; done
