# 외부 트래픽 → api Pod 도달 흐름 (devopsim)

`https://api.devopsim.cloud/items` 요청 한 번이 클러스터 안 api Pod까지 도달하는 과정 + 각 단계가 어떤 K8s 리소스를 어떻게 참조하는지.

---

## 0. 전체 흐름 한 장

```
[브라우저]  https://api.devopsim.cloud/items
    │
    │ ① DNS 질의
    ▼
[Route53] api.devopsim.cloud (ALIAS) → k8s-traefik-traefik-...elb.us-east-2.amazonaws.com
    │                                       (NLB 도메인을 IP로 풀면 3.151.215.52 등 여러 개)
    │ ② TCP/TLS 443 connect
    ▼
[NLB (L4)] target-type=ip, proxy-protocol v2 wrap
    │
    │ ③ Pod IP에 직접 전달 (kube-proxy 우회)
    ▼
[Traefik Pod] :8443
    │   ④ proxy-protocol parse → 진짜 client IP 복원
    │   ⑤ TLS handshake (Secret api-tls의 cert 제시)
    │   ⑥ TLS 종료 (이후 평문 HTTP)
    │   ⑦ HTTPRoute 매칭: hostname=api.devopsim.cloud, path=/items
    │
    │ ⑧ backendRefs: api Service:80
    ▼
[api Service] (ClusterIP 172.20.96.200, 80)
    │   ⑨ Endpoints (api Pod IP 리스트)에서 한 곳 선택
    │
    ▼
[api Pod] :3000 (targetPort)
    └─ /items 응답
```

각 단계의 "무엇을 보고 결정하는지"가 핵심.

---

## 1. ①~② DNS 단계

| 누구 | 무엇 본다 | 결과 |
|---|---|---|
| 브라우저 | OS의 resolver 설정 | resolver(예: 8.8.8.8)로 query 보냄 |
| Public resolver | `.cloud` TLD 서버 → Route53 NS | Route53 hosted zone으로 question 전달 |
| Route53 hosted zone | `api.devopsim.cloud` record | ALIAS → NLB DNS → IP 응답 (`3.151.215.52` 등) |

### Route53 record는 누가 만들었나
`apps/api-httproute.yaml`의 `hostnames: [api.devopsim.cloud]`를 **external-dns** Pod이 watch → Route53 API로 ALIAS A record 생성. TXT 두 개도 같이 만들어 ownership 추적(`_extdns-...`).

### 확인 명령
```bash
dig api.devopsim.cloud +short
# 3.151.215.52   (NLB IP)

kubectl get httproute -A
# api  api  ["api.devopsim.cloud"]   ...

aws route53 list-resource-record-sets --hosted-zone-id Z022477834TFH8MCFO9QI \
  --query "ResourceRecordSets[?Name=='api.devopsim.cloud.']"
```

---

## 2. ③ NLB → Pod IP

### NLB 자체 정체
- `traefik` namespace의 `Service/traefik`(type=LoadBalancer)에 의해 만들어짐
- AWS Load Balancer Controller가 Service annotation 보고 NLB를 AWS에 provision
- `target-type=ip` → NLB가 **Pod IP에 직접 connection** (NodePort/kube-proxy 우회)

### proxy-protocol v2
- Service annotation `aws-load-balancer-proxy-protocol: "*"` → NLB가 모든 connection을 PP v2로 wrap
- 첫 바이트에 클라 IP 메타데이터(13~108 byte) → 그 다음부터 진짜 TLS handshake

### 확인 명령
```bash
kubectl get svc traefik -n traefik
# k8s-traefik-traefik-...elb.us-east-2.amazonaws.com   80:32xxx/TCP,443:31xxx/TCP

aws elbv2 describe-target-groups --query "..."
# target-type: ip, targets = Traefik Pod IP들
```

---

## 3. ④~⑥ Traefik 안에서

### proxy-protocol 파싱
- Traefik의 `ports.web/websecure.proxyProtocol.trustedIPs: ["0.0.0.0/0"]` 설정
- PP v2 prefix를 떼어내 클라 IP를 `X-Real-IP` 등으로 보존 → rate limit / access log에서 사용

### TLS 종료
- HTTPS 요청은 `websecure` entryPoint(8443)로 들어옴
- Traefik이 Gateway의 `listeners[websecure].certificateRefs.name = api-tls` 보고 `api-tls` Secret의 cert/key 로드
- SNI(api.devopsim.cloud) 확인 → 매칭되는 cert 응답 → TLS handshake 완료
- 이후 평문 HTTP 처리

### Secret `api-tls`가 어떻게 거기 있냐
- cert-manager가 Gateway annotation(`cert-manager.io/cluster-issuer: letsencrypt-prod`) + listener config 보고 `Certificate` CRD 자동 생성
- ClusterIssuer `letsencrypt-prod`의 ACME flow(HTTP-01 challenge) 실행 → cert 발급 → Secret 생성/갱신

### Traefik이 어떤 라우팅 정보 보는지
- `kubernetesGateway` provider 활성 → cluster의 모든 GatewayClass / Gateway / HTTPRoute를 watch
- 자기 GatewayClass(`controllerName: traefik.io/gateway-controller`)에 속한 Gateway만 처리

---

## 4. ⑦ HTTPRoute 매칭

`apps/api-httproute.yaml`:
```yaml
spec:
  parentRefs:
    - name: traefik-gateway       # 어느 Gateway에 attach할지
      namespace: traefik
      sectionName: websecure      # 어느 listener에
  hostnames:
    - api.devopsim.cloud           # host 필터
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /                # path 필터
      backendRefs:
        - name: api                 # 어느 Service로 보낼지
          port: 80
```

Traefik의 결정 순서:
1. 들어온 요청의 SNI/Host: `api.devopsim.cloud` → 매칭되는 HTTPRoute 후보 추림
2. path `/items` → `PathPrefix: /` 매칭
3. 해당 rule의 `backendRefs.name=api, port=80` → 다음 단계로

### sectionName으로 HTTP/HTTPS 분리
- `api-httproute.yaml`: `sectionName: websecure` → HTTPS만 받음
- `api-http-redirect.yaml`: `sectionName: web` + RequestRedirect filter → HTTP는 301로 https로 보냄

### 확인
```bash
kubectl describe httproute api -n api
# Status.Parents[0].Conditions: Accepted=True, ResolvedRefs=True
```

---

## 5. ⑧ Service → Pod (cluster 내부)

### Service `api`
- `api` namespace, ClusterIP `172.20.96.200`, port 80
- selector: `app.kubernetes.io/name=api`
- **자동으로** EndpointSlice 만들어짐 (selector 매칭되는 Pod IP 리스트)

### 흐름
1. Traefik이 cluster-internal HTTP로 `http://api.api.svc.cluster.local:80/items` 호출 (또는 Service ClusterIP 직접)
2. **CoreDNS** ConfigMap 의해 `api.api.svc.cluster.local` → `172.20.96.200` (ClusterIP) 응답
3. **kube-proxy** (iptables 모드)가 ClusterIP로 가는 패킷을 EndpointSlice 중 한 Pod IP로 DNAT
4. Pod의 `targetPort: 3000`(api Service의 spec)로 도달

### CoreDNS 역할 요약
- cluster 안 DNS 서버 (kube-system의 CoreDNS Deployment)
- `*.svc.cluster.local` 같은 cluster 내부 이름은 자기가 응답
- 외부 도메인(api.devopsim.cloud 등)은 upstream(노드의 resolv.conf)으로 forward

> Traefik이 `api.devopsim.cloud`를 cluster 안에서 resolve할 일은 없음 (HTTPRoute에서 host 매칭은 Header `Host` 비교일 뿐, DNS 안 함). 클러스터 안 DNS는 Service명 → ClusterIP만 처리.

### kube-proxy 역할 요약
- DaemonSet (모든 노드에 1개씩)
- 각 노드의 iptables/IPVS rule을 cluster의 Service/EndpointSlice 정보로 동기화
- "ClusterIP:port로 가는 패킷 → 무작위 Pod IP로 DNAT" 규칙을 만듦
- **NLB target-type=ip라 외부 → Traefik 까지는 kube-proxy 우회**. cluster 내부 Service 호출만 kube-proxy 사용.

### 확인
```bash
kubectl get svc api -n api -o wide
kubectl get endpointslices -n api -l kubernetes.io/service-name=api
# Pod IP들이 나옴

kubectl get pods -n api -l app.kubernetes.io/name=api -o wide
# IP가 EndpointSlice와 일치하는지
```

---

## 6. 관여하는 K8s 리소스 요약표

| 리소스 | 어디 만들어졌나 | 무엇 보고 다음 단계로 |
|---|---|---|
| `Route53 HostedZone` (devopsim.cloud) | Terraform `module.dns` | NS 4개 — registrar에서 위임 |
| `Route53 ALIAS Record` (api.devopsim.cloud) | external-dns가 HTTPRoute 보고 자동 생성 | NLB DNS → IP |
| `Service/traefik` (LoadBalancer) | Traefik HelmRelease | AWS LB Controller가 보고 NLB 생성 |
| `NLB` (AWS) | AWS LB Controller가 Service 보고 provision | target-type=ip → Pod IP에 forward |
| `Gateway/traefik-gateway` | Traefik HelmRelease | listeners + cert annotation |
| `GatewayClass/traefik` | Traefik HelmRelease | controllerName으로 Traefik이 자기 거 식별 |
| `HTTPRoute/api` (api ns) | flux apps/ | parentRefs로 Gateway에 attach |
| `HTTPRoute/api-http-redirect` | flux apps/ | sectionName=web에 301 filter |
| `Certificate/api-tls` (traefik ns) | cert-manager가 Gateway annotation 보고 자동 | issuerRef → ClusterIssuer letsencrypt-prod |
| `ClusterIssuer/letsencrypt-prod` | configs/cert-manager-issuers.yaml | ACME server URL + HTTP-01 solver |
| `Secret/api-tls` (kubernetes.io/tls) | cert-manager가 cert 발급 후 생성 | Gateway가 마운트해 TLS 종료 시 사용 |
| `Service/api` (ClusterIP) | api Helm chart | selector → EndpointSlice |
| `EndpointSlice` (api ns) | endpoint controller 자동 | Pod IP 리스트 |
| `Pod/api-*` (api ns) | api Deployment | 실제 트래픽 처리 |
| `CoreDNS` (kube-system) | EKS addon | `*.svc.cluster.local` → ClusterIP |
| `kube-proxy` (DaemonSet) | EKS addon | ClusterIP → Pod IP DNAT |

---

## 7. 같은 흐름이 grafana에도 그대로 (per-host)

`grafana.devopsim.cloud` 트래픽:
- DNS: external-dns가 만든 `grafana.devopsim.cloud` ALIAS → 같은 NLB
- Traefik Gateway의 `grafana-https` listener (hostname=grafana.devopsim.cloud, cert=grafana-tls)
- HTTPRoute(grafana) in monitoring ns → Service `kube-prometheus-stack-grafana:80`

→ listener와 HTTPRoute만 추가하면 호스트 추가가 패턴 복제. cert는 cert-manager가, DNS는 external-dns가 자동.

---

## 8. 빠른 디버깅 명령

```bash
# DNS 단계
dig api.devopsim.cloud +short                       # public resolver
kubectl logs -n external-dns deploy/external-dns | tail -20

# NLB 단계
kubectl get svc traefik -n traefik
aws elbv2 describe-target-health --target-group-arn ...

# Traefik 단계
kubectl get gateway -n traefik
kubectl get httproute -A
kubectl logs -n traefik -l app.kubernetes.io/name=traefik | tail -30

# cert 단계
kubectl get certificate,challenge -A
echo | openssl s_client -connect api.devopsim.cloud:443 -servername api.devopsim.cloud 2>/dev/null \
  | openssl x509 -noout -issuer -subject -dates

# Service / Pod 단계
kubectl get svc,endpointslices,pods -n api -l app.kubernetes.io/name=api -o wide

# 종합 (외부 검증)
curl -v https://api.devopsim.cloud/health
curl -sI http://api.devopsim.cloud/health     # 301 to https
```

---

## 9. 한 줄 요약

> **"DNS는 external-dns가, cert는 cert-manager가, 라우팅은 Traefik+Gateway API가, cluster 안 분기는 Service/CoreDNS/kube-proxy가 자동."**
>
> 새 호스트 추가 = HTTPRoute 한 개(+redirect 한 개) + Gateway listener 한 줄. 나머지는 자동 동기화.
