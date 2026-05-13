#!/usr/bin/env bash
# PrometheusScrapeFailure alert 검증.
# expr: up == 0
# for: 3m
# 전략: ServiceMonitor의 selector를 일시적으로 잘못된 라벨로 변경 → target 매칭 안 됨 → up==0.
# WARNING: prod 메트릭 일시 끊김. 검증 후 자동 복구.
set -euo pipefail

NS="${NS:-api}"
SM_NAME="${SM_NAME:-api}"

# 현재 selector 백업
ORIG=$(kubectl get servicemonitor "$SM_NAME" -n "$NS" -o jsonpath='{.spec.selector.matchLabels}')
echo "현재 selector: $ORIG"

cleanup() {
  echo ""
  echo "복구: selector 원복"
  kubectl patch servicemonitor "$SM_NAME" -n "$NS" --type=merge -p "{\"spec\":{\"selector\":{\"matchLabels\":$ORIG}}}" >/dev/null
}
trap cleanup EXIT INT TERM

echo "selector를 매칭 안 되는 값으로 변경 → scrape 실패"
kubectl patch servicemonitor "$SM_NAME" -n "$NS" --type=merge -p '{"spec":{"selector":{"matchLabels":{"app":"nonexistent-for-validation"}}}}' >/dev/null

echo "for: 3m → 약 3.5분 후 Firing 예상."
echo "Prometheus /alerts에서 Pending→Firing 확인 후 Ctrl+C로 복구"

while true; do sleep 30; done
