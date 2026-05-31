# Traefik + Ingress + HTTPS 도입 기록

> 지금까지 devopsim은 AWS ALB Ingress로 외부 노출 중. 도메인은 안 샀고 ALB의 elb.amazonaws.com 주소를 직접 사용. HTTPS도 없음.
> 이번 단계 목표: **도메인 구매 + DNS → NLB + Traefik(L7 router) + Let's Encrypt HTTPS + Rate Limit**.
> 이 문서는 그 전에 필요한 개념을 모두 정리한 메모.

---

## 0. 큰 그림 — "도메인 사면 K8s까지 어떻게 도달하나"

```
[사용자 브라우저]  https://api.example.com/items
        ↓ (1) DNS resolution
[DNS resolver] ── api.example.com → 1.2.3.4 (LB IP)
        ↓ (2) TCP/TLS connect
[NLB (L4)] ── 1.2.3.4:443 → cluster nodes:30443
        ↓ (3) NodePort → kube-proxy iptables
[Traefik Pod (L7)] ── TLS terminate + 경로 라우팅
        ↓ (4) Service ClusterIP
[api Pod] ── http://api-pod:3000/items
```

각 단계마다 다른 기술이 끼어 있고, 어디서 무엇이 끝나는지가 보안/성능/장애의 핵심 분기점.

---

## 1. L4 vs L7

OSI 모델의 두 층이지만, 인프라 맥락에선 "패킷만 보냐, HTTP 까지 보냐"의 구분.

| 항목 | L4 | L7 |
|---|---|---|
| 다루는 단위 | TCP/UDP 패킷, 5-tuple(src/dst IP·port + proto) | HTTP method, header, path, body |
| 무엇을 결정? | 어느 backend로 connection을 보낼지 | 어느 backend로 **각 요청**을 보낼지 |
| 성능 | 매우 빠름, 거의 카운터만 | TLS 해독, 헤더 파싱 등 비용 |
| 대표 | TCP/UDP LB, AWS NLB, HAProxy(TCP mode) | nginx, Envoy, Traefik, AWS ALB |
| 다룰 수 있는 라우팅 | "이 포트 → 저 풀" | "host = api.example.com & path = /v2/* → 저 풀" |
| Rate limit / WAF / TLS 종료 | (한정) | ✅ |

**우리 케이스**: API는 HTTP/HTTPS만 → L7이 자연스러움. 그런데 **NLB(L4) + Traefik(L7) 조합**이 권장되는 이유는:

- NLB는 ALB보다 싸고 빠르며 IP 고정.
- TLS 종료/라우팅/rate limit은 cluster 안에서 Traefik이 처리 → 인프라 코드를 git으로 관리.
- ALB를 쓰면 라우팅 규칙이 AWS 콘솔/Terraform 측에 분산.

→ "L4는 외부 진입점만, L7은 cluster 내부에서" 라는 분리.

---

## 2. K8s Service 타입 4가지

```
ClusterIP   (default)  ── 클러스터 내부 가상 IP. 외부 접근 불가.
NodePort                ── ClusterIP + 모든 노드의 동일 포트(30000-32767)에서 받음.
LoadBalancer            ── NodePort + 클라우드 LB를 자동 생성해서 노드들에 분산.
ExternalName            ── 단순 CNAME alias (외부 DNS 이름을 그대로 cluster 안에서 사용).
```

### Service의 본질

Service는 "Pod IP는 변하니까 안정적인 가상 IP를 주자"의 K8s 답. kube-proxy가 노드마다 iptables (또는 IPVS) rule을 깔아서, ClusterIP로 가는 패킷을 endpoint Pod IP 중 하나로 NAT.

### LoadBalancer를 만들면 일어나는 일 (AWS 기준)

```
1. kubectl apply Service{type: LoadBalancer}
        ↓
2. cloud-controller-manager가 Service를 watch
        ↓
3. AWS API 호출 → ELB 생성 (옛날엔 Classic LB, 지금은 NLB/ALB)
        ↓
4. ELB의 target = 모든 노드의 NodePort
        ↓
5. ELB DNS 이름(elb.amazonaws.com)이 Service.status.loadBalancer.ingress에 박힘
        ↓
6. 외부 트래픽 → ELB → 노드 NodePort → kube-proxy iptables → Pod
```

기본은 Classic LB. 현대적으로 NLB/ALB를 쓰려면 **AWS Load Balancer Controller**라는 별도 컨트롤러를 설치하고 annotation으로 종류 지정:

```yaml
metadata:
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: external
    service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: ip
    service.beta.kubernetes.io/aws-load-balancer-scheme: internet-facing
```

`target-type: ip`면 노드 NodePort 우회하고 **NLB가 Pod IP에 직접 routing**. 더 빠르고 hop이 줄어듦. devopsim은 이 모드로 갈 예정.

---

## 3. Ingress와 Ingress Controller — 별개의 두 개

이 둘이 자주 혼동된다. **Ingress는 명세, Ingress Controller는 그 명세를 실행하는 프로세스**.

```
Ingress (yaml)           Ingress Controller (Pod)
─────────────            ───────────────────────────
"api.example.com         "Ingress CRD watch
 path /v2 → api Service" → 자기 config 갱신
                          → 들어오는 요청 라우팅"
   ↑                            ↑
   K8s API에 박힌 선언        실제 트래픽을 받는 reverse proxy
```

### Service로는 안 되나?

LoadBalancer Service만 쓰면 다음이 어려움:
- 도메인 1개에 여러 서비스 path별 분기 (`/api` vs `/grafana`)
- TLS 인증서 cluster 안에서 관리
- 가상 호스트 분기 (host 헤더 기반)
- rate limit, WAF, header rewrite
- 한 LB로 여러 Service 묶기 (비용)

→ Ingress가 위를 표준화한 명세. 하지만 실행은 controller가 함.

### Ingress 리소스 모양

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api
  annotations:
    # 어떤 ingress controller가 처리할지 (또는 spec.ingressClassName)
spec:
  ingressClassName: traefik
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 80
  tls:
    - hosts: ["api.example.com"]
      secretName: api-tls  # 인증서 Secret
```

### Ingress Controller 종류

| 컨트롤러 | proxy 엔진 | 특징 |
|---|---|---|
| **nginx-ingress** | nginx | 가장 광범위. annotation 폭발적 많음. config reload 느림 |
| **Traefik** | 자체 (Go) | K8s-native, 동적 reload, ACME 내장, middleware 깔끔 |
| **AWS Load Balancer Controller** | AWS ALB (외부) | cluster 안에 proxy 없음. annotation으로 ALB 생성 |
| **Contour** | Envoy | gRPC/HTTP2 강함, IngressRoute/HTTPProxy CRD |
| **Istio Gateway** | Envoy | service mesh의 일부, 가장 강력하지만 무거움 |
| **HAProxy Ingress** | HAProxy | TCP/UDP까지 |

→ **이번 단계 선택: Traefik**. 이유는 다음 절.

---

## 4. Traefik이 뭐냐

Traefik (트라픽 / 트래픽 둘 다 발음) = K8s/Docker 시대에 맞춰 처음부터 동적 reverse proxy로 설계된 OSS. Go로 짜여 있고 binary 1개.

### 핵심 특징

- **Native K8s 통합**: Ingress, IngressRoute(자체 CRD), Gateway API 모두 지원.
- **동적 config**: 새 Ingress 만들면 reload 없이 바로 라우팅. nginx-ingress는 config reload 필요 (요청 drop 가능).
- **Let's Encrypt 내장**: ACME client가 binary 안에 들어있어 cert-manager 없이도 운영 가능 (단, replica 1개일 때만 안전. 다중 replica엔 cert-manager + Traefik이 정석).
- **Middleware 모델**: rate-limit, basic-auth, redirect, headers, IP-allowlist 등을 declarative CRD로 chaining.
- **Dashboard UI**: 어떤 route가 등록됐는지 시각화.
- **Plugin** (WASM 기반): 추가 기능을 plugin으로.

### Traefik 1.x vs 2.x

- 1.x: annotation 위주, 단순.
- 2.x+ (지금 표준): **IngressRoute / Middleware / TLSOption** 등 CRD-first. 학습 곡선 있지만 표현력↑.

### vs nginx-ingress

| | nginx-ingress | Traefik |
|---|---|---|
| Config 모델 | annotation 위주 (수십 개) | CRD + middleware (선언적) |
| Reload | nginx -s reload (1초 미만 끊김) | 동적, 무중단 |
| ACME | cert-manager 필요 | 내장 (또는 cert-manager) |
| Plugin | Lua (커스텀) | Plugin (WASM/Yaegi) |
| 성숙도 | 매우 높음 | 높음 |
| 학습 자료 | 매우 많음 | 보통 |

devopsim에선 **CRD 기반 선언적 설정 + middleware 학습 가치**를 보고 Traefik 선택.

---

## 5. Envoy의 역할 — 왜 자주 같이 언급되는가

Envoy는 **Lyft에서 만든 범용 L7 proxy 라이브러리**. 자체로는 Ingress Controller가 아니지만 다음의 코어:

- **Istio data plane** — service mesh의 sidecar
- **Contour** — Envoy를 Ingress Controller로 감싼 것
- **AWS App Mesh** — Envoy 기반
- **gRPC server proxies**

특징:
- xDS API로 동적 config (control plane이 push)
- HTTP/2/3, gRPC 1급 지원
- 통계 메트릭 매우 풍부

Traefik과의 차이: **Traefik은 routing 위주, Envoy는 일반 proxy framework**. Envoy 단독으로 쓰는 사람은 거의 없고 보통 Istio/Contour 같은 control plane이 동반.

→ "Ingress = nginx" 시대에서 "service mesh = Envoy" 시대로 전환 중. devopsim은 mesh까지 안 가니 Traefik 충분.

---

## 6. Ingress vs Gateway API

Ingress는 2017년쯤 표준화됐지만 한계가 명확:

| Ingress의 문제 | 결과 |
|---|---|
| HTTP만 지원, TCP/UDP/gRPC 없음 | TCP는 vendor-specific annotation |
| 표현력 부족 (host + path 정도) | header 매칭/weight split이 다 annotation |
| Vendor마다 annotation 다름 | nginx와 Traefik annotation 호환 X |
| Role 분리 없음 | 인프라팀과 앱팀이 같은 리소스 편집 |

→ K8s SIG-Network가 새로 만든 **Gateway API**: 2023년 GA.

### Gateway API의 모델

```
GatewayClass     (인프라팀 — controller 선택, "traefik")
    ↓
Gateway          (인프라팀 — listener: 443/HTTPS, TLS, attached route 정책)
    ↓
HTTPRoute        (앱팀 — host, path, header, backend, weight)
TCPRoute         (L4)
GRPCRoute        (gRPC 전용)
TLSRoute         (TLS pass-through)
```

### 장점

- L4/L7 함께
- header / query / method 매칭
- traffic split (canary, blue/green) 표준
- 인프라/앱 role 분리
- vendor 중립

### 현재 상태

- Ingress는 deprecate 아님, 당분간 공존
- 대부분 Ingress Controller (Traefik, nginx, Envoy, Istio)가 Gateway API 지원 시작
- 신규 프로젝트는 Gateway API 권장

devopsim 1단계: 익숙한 Ingress로 시작. 2단계: Gateway API로 마이그레이션 검토.

---

## 7. 도메인 → K8s 라우팅 전체 흐름 (HTTPS 포함)

도메인을 **AWS Route53에서 사거나 다른 registrar에서 사고 Route53로 위임**한다고 가정.

```
1. registrar에서 도메인 구매 (예: example.com)
        ↓
2. Route53에 hosted zone 생성
        nameserver(NS) 4개 받음
        registrar에서 이 NS로 위임 (delegation)
        ↓
3. Route53에 record 추가
        api.example.com  →  (alias) NLB DNS
        ↓
4. cluster에 NLB Service 만듦 (Traefik 앞)
        AWS LB Controller가 NLB 생성 → DNS 받음
        ↓
5. Traefik에 IngressRoute(또는 Ingress) 등록
        host=api.example.com, path=/, backend=api Service
        ↓
6. cert-manager가 ACME challenge 통과 → Let's Encrypt 인증서 받음
        Secret로 저장
        ↓
7. Traefik이 Secret을 읽어 TLS 종료
        ↓
8. 사용자: https://api.example.com/items
        DNS → NLB → Traefik(TLS 해독 + 라우팅) → api Pod
```

### external-dns (옵션)

3번을 자동화하는 방법. **external-dns**라는 컨트롤러를 클러스터에 띄우면 Ingress의 host annotation을 보고 Route53 record를 자동 생성. 매번 console 안 들어가도 됨.

---

## 8. TLS / HTTPS 기초

**HTTPS = HTTP + TLS**. TLS는 두 단계의 암호:

### Handshake (비대칭 키)

```
1. Client → Server: "TLS 1.3 쓸 수 있는 cipher 알려줘"
2. Server → Client: cipher 선택 + 서버 인증서 (서버의 public key 포함)
3. Client: CA의 public key로 서버 인증서 서명 검증
        → 신뢰할 수 있는 CA가 서명했으면 통과
4. ECDHE 같은 키 교환 → 둘만 아는 session key 생성
```

### Bulk encryption (대칭 키)

- handshake로 만든 session key (AES-256 등)로 실제 데이터 암호화
- 비대칭 키는 느려서 handshake에만, 이후엔 대칭 키
- TLS 1.3은 handshake 1 RTT, 빠름

### 인증서가 뭔지

```
{
  domain: "api.example.com",
  public_key: "...",
  issuer: "Let's Encrypt R3",
  signature: "<CA의 private key로 서명>",
  valid_from / valid_to
}
```

= "이 domain의 공개키는 이거야, 내가 보증해" + CA의 서명.

브라우저는 CA의 public key를 OS/브라우저에 미리 갖고 있어서, 서명을 검증할 수 있다.

### Certificate Authority (CA)

- 옛날: Verisign/Comodo 같은 유료 CA (사이트 1개에 연 100만원+)
- 지금: **Let's Encrypt** 무료, 자동화. 사실상 산업 표준.

### ACME 프로토콜

Let's Encrypt가 정의한 자동 발급 프로토콜. 두 가지 도전(challenge):

| Challenge | 검증 방식 | 사용 케이스 |
|---|---|---|
| **HTTP-01** | `http://api.example.com/.well-known/acme-challenge/<token>` 에 토큰 응답 | 가장 흔함. 80번 포트 열려있어야 |
| **DNS-01** | `_acme-challenge.api.example.com` TXT 레코드 | wildcard 인증서 필수, 80 포트 닫혀있을 때 |

challenge를 통과하면 CA가 "도메인 소유 증명" → 인증서 발급.

### cert-manager

K8s에서 ACME를 자동화하는 컨트롤러:

```
Issuer/ClusterIssuer  (CRD)         "이 CA에서 발급"
       ↓
Certificate  (CRD)                   "이 도메인 cert 만들어"
       ↓
cert-manager가 ACME challenge 진행
       ↓
Kubernetes Secret 생성               "이게 TLS cert + key"
       ↓
Ingress에서 spec.tls.secretName 참조
       ↓
TLS 종료 시 사용
       ↓
만료 30일 전 자동 갱신
```

---

## 9. TLS termination 위치

"TLS를 어디서 푸느냐"는 architecture 결정.

| 위치 | 장점 | 단점 |
|---|---|---|
| **LB (NLB+ACM)** | 가장 흔함. AWS ACM 무료 cert | TLS가 LB에서 끝, cluster 안은 평문 |
| **Ingress controller (Traefik)** | end-to-end 암호화 (cluster 입구까지), cert-manager로 자동화 | 약간 더 CPU |
| **Pod (mTLS)** | service mesh, 가장 안전 | 복잡, 운영 비용 |

**devopsim 선택**:
- 옵션 1 (간단): NLB → 평문 → Traefik에서 TLS는 ACM (LB 종료)
- 옵션 2 (학습 가치): NLB는 TCP만 전달 → Traefik이 cert-manager로 받은 cert로 종료

옵션 2 권장 (학습 + GitOps로 관리 가능).

---

## 10. Rate Limit

LB나 Ingress 단계에서 **악성/실수 트래픽 차단**.

### 알고리즘

| 알고리즘 | 동작 | 특징 |
|---|---|---|
| **Fixed window** | 1분에 N회 | 경계에서 burst 가능 |
| **Sliding window** | 최근 1분 (Rolling) | 더 부드러움 |
| **Token bucket** | bucket size + refill rate | burst 허용, 평균 한정 |

Traefik의 RateLimit middleware는 GCRA (token bucket의 변형).

### 무엇 기준으로 limit 하나

- **client IP** (X-Forwarded-For)
- **header** (`X-API-Key`)
- **path** (특정 endpoint만)
- **사용자 인증 정보** (JWT subject)

⚠ Traefik이 LB 뒤에 있으면 그냥 connection IP는 LB의 IP. 반드시 `X-Forwarded-For` 또는 `proxyProtocol`로 진짜 클라 IP 추출하도록 설정. 안 그러면 모든 트래픽이 한 IP로 보여서 rate limit 무력화 또는 cluster 전체가 한 번에 차단.

### Traefik Middleware 예시

```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: api-ratelimit
  namespace: api
spec:
  rateLimit:
    average: 100        # 평균 100 req/s
    burst: 200          # 순간 burst 200까지
    period: 1s
    sourceCriterion:
      ipStrategy:
        depth: 1        # X-Forwarded-For의 가장 오른쪽 IP를 클라로
```

IngressRoute에 `middlewares: [{name: api-ratelimit}]`로 연결.

---

## 11. 그래서 Traefik 작업으로 해야 될 것들 — 순서

1. **도메인 구매 + Route53 hosted zone**
   - registrar에서 example.com 구매 (10$/년 정도)
   - Route53에 hosted zone 생성, NS 받아 registrar에 위임
   - Terraform module로 관리 (`infra/terraform/modules/dns/` 신설)

2. **AWS Load Balancer Controller 설정 확인**
   - 이미 설치되어 있음 (api/Grafana ALB가 LB Controller로 떠있음)
   - NLB 모드도 같은 controller로 가능 (annotation만 바꾸면)

3. **Traefik 설치**
   - Helm chart `traefik/traefik` (v36+)
   - Service `type: LoadBalancer` + NLB annotation
   - CRD(IngressRoute, Middleware, TLSStore) 포함
   - infra/flux/.../controllers/traefik.yaml

4. **cert-manager 설치**
   - Helm chart `jetstack/cert-manager`
   - infra/flux/.../controllers/cert-manager.yaml
   - CRD 포함 옵션 enabled

5. **ClusterIssuer 생성 (Let's Encrypt prod)**
   - HTTP-01 challenge solver = Traefik
   - infra/flux/.../configs/cert-manager-issuer.yaml

6. **Route53 record 추가**
   - api.example.com → Traefik NLB DNS (alias)
   - grafana.example.com → 같은 NLB (Traefik이 host 분기)
   - Terraform `aws_route53_record`

7. **IngressRoute 작성**
   - api용 IngressRoute (host=api.example.com → api Service)
   - Grafana용 IngressRoute (host=grafana.example.com)
   - 기존 ALB Ingress와 잠시 병존

8. **Rate Limit Middleware**
   - api에 200 req/s burst, sliding window
   - sourceCriterion.ipStrategy.depth=1

9. **기존 ALB Ingress 정리**
   - 검증 끝나면 ALB Ingress 삭제 → ALB 자동 정리

10. **(선택) external-dns**
    - Ingress annotation으로 Route53 record 자동 관리

11. **(선택) Gateway API 마이그레이션**
    - 2단계로 IngressRoute → HTTPRoute

---

## 12. 자주 빠지는 함정

1. **DNS propagation**: hosted zone NS 변경 후 전 세계 resolver 반영까지 최대 48h. 보통 1~2h. 사이트 안 뜬다고 cert부터 발급하려 하면 challenge가 실패.
2. **HTTP-01 challenge 80 포트**: LB가 443만 열고 80 안 열면 challenge 실패. challenge 통과 후 80 → 443 redirect 박는 게 정석.
3. **cert-manager namespace 분리**: ClusterIssuer + Certificate는 namespace 일치해야 cross-ns 참조 가능. 보통 cert는 app namespace에.
4. **TLS termination이 LB면 X-Forwarded-Proto 잊지 말 것**: cluster 안은 평문 HTTP라 `req.protocol === 'http'`. https redirect 무한루프 위험. trust proxy 설정 또는 X-Forwarded-Proto 검사.
5. **Rate limit IP 식별 오류**: 위 10절 참고. proxy depth/strategy를 정확히.
6. **wildcard cert는 DNS-01 필수**: `*.example.com` cert는 HTTP-01로 못 받음.
7. **Let's Encrypt rate limit**: production은 도메인당 주 50개. staging에서 먼저 실험.
8. **Traefik 1.x 문서 보고 따라하면 안 됨**: 2.x부터 CRD가 완전히 다름. 항상 2.x/3.x 문서.
9. **NLB target-type=ip**: pod IP에 직접 라우팅하려면 VPC CNI가 secondary IP를 ENI에 미리 붙여야 함. EKS는 기본 지원.
10. **여러 ingress controller 공존 시 ingressClassName 빼면 모두 처리하려 함**: 명시적으로 `ingressClassName: traefik` 박을 것.

---

## 13. devopsim 현재 → 다음 단계 (구조 비교)

### 현재 (Week 10 끝)

```
인터넷
  ↓
ALB (api 전용)        ALB (monitoring group)
  ↓                    ↓
api Ingress           Grafana Ingress
  ↓                    ↓
api Service           Grafana Service
  ↓                    ↓
api Pod               Grafana Pod
```

- HTTPS 없음 (ALB는 80만)
- 도메인 없음 (elb.amazonaws.com 직접)
- 라우팅이 AWS 콘솔/annotation에 분산

### 다음 (Week 11 끝, 목표)

```
인터넷  https://api.example.com
        https://grafana.example.com
  ↓
[Route53]  api.example.com → NLB DNS
  ↓
NLB (TCP 443)        ← AWS Load Balancer Controller가 생성
  ↓                    target-type=ip, Pod IP에 직접
Traefik Pod          ← Ingress controller, TLS 종료
  ↓                    rate-limit middleware
api / grafana Service
  ↓
api / grafana Pod
```

- 도메인 + HTTPS + rate limit 모두 git으로 관리
- 단일 NLB로 비용 절감
- 클러스터 내부에서 라우팅 변경 자유

---

## 14. 참고

- Traefik docs: https://doc.traefik.io/traefik/
- cert-manager: https://cert-manager.io/docs/
- Gateway API: https://gateway-api.sigs.k8s.io/
- AWS Load Balancer Controller: https://kubernetes-sigs.github.io/aws-load-balancer-controller/
- Let's Encrypt rate limits: https://letsencrypt.org/docs/rate-limits/
- TLS 1.3 RFC8446: https://datatracker.ietf.org/doc/html/rfc8446
