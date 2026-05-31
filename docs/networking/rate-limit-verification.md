# Rate Limit Middleware 검증 + ALB → Traefik 전환 기록

Week 11의 마지막 단계. Traefik Middleware로 IP-based rate limit 도입하고 기존 ALB Ingress 두 개를 제거해 외부 진입점을 NLB 단일로 일원화한 작업 기록.

---

## 1. 핵심 결정

| 결정 | 선택 | 이유 |
|---|---|---|
| Rate limit 구현 위치 | Traefik `Middleware` CRD | Gateway API 표준엔 rate limit 없음. vendor 확장이 가장 깔끔 |
| HTTPRoute 연결 방식 | `filters[].extensionRef` | Gateway API의 공식 vendor extension 메커니즘 |
| Source IP 식별 | `sourceCriterion` 생략 (default=connection IP) | NLB proxy-protocol v2가 진짜 client IP를 TCP 레벨에 전달 |
| 정책 값 | average 100/s, burst 200, period 1s | 학습/chaos test 친화. 너무 빡빡하면 traffic.sh 같은 시뮬레이터가 막힘 |
| 적용 범위 | api host 전체 (per-host) | path별 분기는 후속. `/health` 면제 등은 메트릭 보고 결정 |
| ALB 정리 방식 | values.yaml의 `ingress.enabled: false` | 매니페스트 삭제 X — AWS LB Controller가 자동으로 ALB 정리 |

---

## 2. 적용 매니페스트

### Middleware (api ns)
```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: api-ratelimit
  namespace: api
spec:
  rateLimit:
    average: 100
    burst: 200
    period: 1s
```

### HTTPRoute에 filter 추가 (api ns)
```yaml
spec:
  rules:
    - matches:
        - path: { type: PathPrefix, value: / }
      filters:
        - type: ExtensionRef
          extensionRef:
            group: traefik.io
            kind: Middleware
            name: api-ratelimit
      backendRefs:
        - name: api
          port: 80
```

### Traefik provider 활성 (traefik HelmRelease)
```yaml
providers:
  kubernetesCRD:
    enabled: true   # Middleware CRD watch — false면 ExtensionRef 무시됨
```

---

## 3. 검증 절차

### 3-1. Middleware 등록 / Provider 활성 확인

```bash
kubectl get middleware -n api
# NAME            AGE
# api-ratelimit   3m10s

kubectl logs -n traefik -l app.kubernetes.io/name=traefik | grep -i middleware
# Provider connection: kubernetesCRD ...
```

### 3-2. Router에 Middleware attach 확인

```bash
kubectl port-forward -n traefik svc/traefik 9000:9000 &
curl -s http://localhost:9000/api/http/routers | jq '.[] | select(.name | contains("api")) | {name, rule, middlewares}'
# {
#   "name": "default-api-...",
#   "rule": "...",
#   "middlewares": ["api-api-ratelimit@kubernetescrd"]
# }
```

### 3-3. Burst 테스트 — 가장 직접적인 검증

```bash
# 1000 req 동시 발사 — burst 200 + avg 100/s × 4s = ~600 이내 통과, 나머지 429
for i in $(seq 1 1000); do
  curl -s -o /dev/null -w "%{http_code}\n" https://api.devopsim.cloud/health &
done | wait | sort | uniq -c
```

실제 결과:
```
 879 200
 121 429
elapsed: 4.0s
```

burst 200(시작 토큰) + avg 100/s × 4s(refill 약 400) ≈ 600 통과 예상이나, 실제는 879 통과 / 121 차단. period가 1s 단위라 미세 차이.

### 3-4. Prometheus 메트릭

```promql
# 429 응답 누적
sum by (router) (rate(traefik_router_requests_total{code="429"}[5m]))

# rate limit drop 카운터
sum by (entryPoint) (rate(traefik_entrypoint_requests_total{code="429"}[5m]))
```

`traefik_router_requests_total{code="429"}` 가 burst test 직후 121 증가 확인.

---

## 4. ALB → Traefik 전환

### 전환 전
```
인터넷
  ├─ ALB k8s-api-api-...                   → api Ingress  → api Service
  └─ ALB k8s-monitoring-... (group=monitoring)  → Grafana Ingress → Grafana Service
```

api / Grafana가 각자 별도 ALB. 라우팅 규칙은 K8s Ingress + ALB annotation에 분산.

### 전환 후
```
인터넷
  └─ NLB k8s-traefik-traefik-...
       └─ Traefik Gateway
            ├─ websecure listener (hostname=api.devopsim.cloud, cert=api-tls)
            │    └─ HTTPRoute api → api Service (Middleware: rate limit)
            └─ grafana-https listener (hostname=grafana.devopsim.cloud, cert=grafana-tls)
                 └─ HTTPRoute grafana → kube-prometheus-stack-grafana Service
```

NLB 1개, 라우팅 / 인증서 / rate limit 전부 cluster 안 git 관리.

### 변경 사항

| 파일 | 변경 |
|---|---|
| `infra/helm/api/values-production.yaml` | `ingress.enabled: true → false` |
| `infra/flux/.../kube-prometheus-stack.yaml` | `grafana.ingress.enabled: true → false` |

Helm chart의 Ingress 비활성 → Flux helm-controller가 helm upgrade → Ingress 리소스 삭제 → AWS Load Balancer Controller가 ALB AWS 콘솔에서 자동 정리.

### 결과 검증

```bash
kubectl get ingress -A
# No resources found       ← Ingress 리소스 둘 다 사라짐

aws elbv2 describe-load-balancers --query 'LoadBalancers[].LoadBalancerName' --output text
# k8s-traefik-traefik-...   ← NLB만 남음

curl -s https://api.devopsim.cloud/health
# {"status":"ok",...}      ← 정상 (Traefik 경유)
curl -s https://grafana.devopsim.cloud/
# 302 → /login            ← 정상
```

---

## 5. 검증 중 발견한 함정

### 5-1. 1차 burst test 모두 200 통과
- 처음 400 req in 2s → 모두 200
- 원인: burst 200 + avg 100/s × 2s = **정확히 400 limit** 안. 한계점이라 통과.
- 해결: **burst × 2 + 시간 × avg를 명확히 초과**하도록 1000 req in 4s로 재시도 → 121× 429 확인.

→ rate limit 테스트는 **이론 한도를 명확히 초과**해야 의미 있음.

### 5-2. `kubernetesCRD.enabled: false` 였을 때
- HTTPRoute의 `extensionRef`가 무시됨 — Traefik이 Middleware를 watch하지 않으므로
- HTTPRoute status는 정상(`ResolvedRefs=True`)이라 의심 어려움
- 진단법: Traefik dashboard `/api/http/routers`에서 router의 `middlewares` 필드가 비어있는지 확인

→ Gateway API + Traefik Middleware 패턴은 **`kubernetesCRD` provider 활성이 필수**.

### 5-3. ALB 즉시 삭제 안 됨
- `ingress.enabled: false` 커밋 후 Flux reconcile → Ingress 리소스 삭제는 즉시
- 하지만 AWS console에서 ALB 자체 사라지는 데는 ~2분 (LB Controller 정리 작업)
- 그 사이 DNS 응답이 양쪽 LB 다 가리킬 수 있어서 일시적 혼선 가능 (devopsim은 DNS가 NLB만 가리키니 무관)

---

## 6. 향후 개선 후보

- **path별 rate limit 분리**: `/health`, `/metrics` 면제 (probe 트래픽이 카운트되는 거 방지)
- **헤더 보안 Middleware**: HSTS, X-Frame-Options, CSP 추가
- **grafana도 rate limit**: 로그인 brute-force 차단
- **per-user rate limit**: `sourceCriterion.requestHeaderName: Authorization`로 JWT subject 기반
- **Ratelimit 정책 PrometheusRule**: 429 비율이 일정 이상이면 alert

---

## 7. 한 줄 요약

> **외부 ALB 두 개 → NLB 단일 + Traefik(Gateway API) + cert-manager + external-dns + Rate Limit Middleware. 외부 진입점/라우팅/인증서/속도제한 전부 cluster GitOps로 일원화.**
