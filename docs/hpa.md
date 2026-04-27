# HPA (HorizontalPodAutoscaler)

> 기준: 2026-04-28 / 자동 스케일링 학습 정리

---

## HPA란

워크로드의 **CPU/메모리 사용률**(또는 커스텀 메트릭)을 보고 Deployment의 replica 수를 자동으로 늘리거나 줄이는 K8s 기본 기능.

```
사용률 낮음 → replica 줄임 (비용 절감)
사용률 높음 → replica 늘림 (성능 유지)
```

---

## HPA는 Pod인가?

**아니다.** 자주 헷갈리는 부분.

```
HPA          = K8s API에 저장된 "스케일링 규칙" 객체
실제 동작     = kube-controller-manager (EKS 컨트롤 플레인)가 수행
                → AWS가 관리, 우리 노드에 안 떠있음
```

**Pod로 떠있는 것 vs Pod가 아닌 것:**

```
[Pod]
metrics-server         ← 사용량 측정 데몬
karpenter 컨트롤러      ← Deployment
ALB / EBS CSI         ← Pod 또는 DaemonSet

[Pod 아님 — 객체만 있고 동작은 control plane]
HPA
PDB
NetworkPolicy
ResourceQuota
```

HPA는 그저 "이 Deployment를 이 규칙으로 스케일해줘"라는 **선언**일 뿐.

---

## 동작 흐름

```
[15초마다 반복 — kube-controller-manager가 수행]

① HPA 객체 읽음
   "api Deployment를 50% 목표로 2~10개 사이로 유지"
        ↓
② metrics-server에 질의
   "api Pod들 CPU 사용량 알려줘"
        ↓
③ 사용률 계산
   사용률 = (실제 사용 / requests) × 100
        ↓
④ 결정
   사용률 < 목표 × 0.9  → 줄임
   사용률 > 목표 × 1.1  → 늘림
   그 사이             → 그대로
        ↓
⑤ Deployment.spec.replicas 변경
        ↓
   Deployment Controller가 Pod 추가/삭제
```

---

## 동작에 필요한 두 가지

```
[1] metrics-server
    Pod CPU/메모리 사용량 수집해서 Metrics API로 노출
    EKS는 기본 미설치 → EKS Add-on 또는 Helm으로 별도 설치

[2] resources.requests 설정
    HPA가 사용률 % 계산하려면 분모(요청량)가 있어야 함
    requests 없으면 HPA 작동 불가 (metrics-server만 있어도 안 됨)
```

`metrics-server` 없으면:
```bash
kubectl top pods
→ error: Metrics API not available

kubectl describe hpa api
→ FailedGetResourceMetric: failed to get cpu utilization
```

`requests` 없으면:
```bash
kubectl describe hpa api
→ unable to get cpu utilization (cannot calculate without requests)
```

---

## requests의 중요성

```yaml
resources:
  requests:           # "이만큼은 보장받고 싶음"
    cpu: 100m         # 0.1 vCPU
    memory: 128Mi
  limits:             # "이 이상은 못 씀"
    cpu: 500m
    memory: 256Mi
```

**HPA 사용률 계산:**
```
requests.cpu = 100m

실제 사용 50m  → 50% 사용률
실제 사용 100m → 100% 사용률
실제 사용 200m → 200% 사용률 (limits까지 burst 가능 시)
```

목표가 50%인데 실제가 100%면 → "용량을 2배로" → replica × 2.

**Karpenter 노드 사이즈 결정에도 영향:**
- Pod requests 합산 → Karpenter가 적절한 인스턴스 타입 선택
- requests 없으면 가장 작은 인스턴스 (t3a.micro 등) 추측

---

## HPA 매니페스트 구조

```yaml
apiVersion: autoscaling/v2     # v2 사용 (v1은 CPU만, v2는 메모리/커스텀 메트릭 가능)
kind: HorizontalPodAutoscaler
metadata:
  name: api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api                  # 어떤 Deployment를 스케일할지
  minReplicas: 2               # 부하 없어도 최소 유지
  maxReplicas: 10              # 부하 폭증해도 최대 한도
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 50    # 모든 Pod 평균 CPU 50% 목표
```

**이 프로젝트 설정** (`infra/helm/api/values-production.yaml`):
```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 50
```

---

## kubectl로 보는 법

```bash
kubectl get hpa

NAME   REFERENCE        TARGETS    MINPODS   MAXPODS   REPLICAS
api    Deployment/api   23%/50%    2         10        2
                        │   │
                        │   └─ 목표
                        └─── 현재 평균 사용률
```

```bash
kubectl describe hpa api

# 자세한 메트릭 + 최근 스케일 이벤트 보임
# Conditions:
#   AbleToScale     True
#   ScalingActive   True
#   ScalingLimited  False
```

---

## HPA가 Karpenter와 협력하는 그림

```
부하 발생
    ↓
api Pod CPU 사용률 80% 도달
    ↓
HPA: replica 2 → 8로 변경
    ↓
새 Pod 6개 Pending (기존 노드에 자리 부족)
    ↓
Karpenter: Pending 감지 → 새 EC2 생성
    ↓
새 노드 Ready → Pending Pod들 거기 스케줄
    ↓
부하 사라짐
    ↓
HPA: replica 8 → 2로 변경
    ↓
Pod 6개 종료
    ↓
Karpenter: 빈 노드 감지 → consolidation으로 EC2 종료
```

**역할 분담:**
```
HPA       → Pod 개수 결정 (스케줄러에 부담만 줌)
Karpenter → 그 Pod들이 들어갈 EC2 마련 (실제 인프라 생성)
```

둘이 짝이 맞아 떨어져야 자동 스케일이 동작.

---

## 흔한 실수

| 실수 | 결과 | 해결 |
|------|------|------|
| metrics-server 미설치 | HPA 메트릭 못 읽음 | EKS Add-on 또는 Helm 설치 |
| requests 미설정 | 사용률 계산 불가 | Deployment.spec.containers.resources 추가 |
| Deployment에 replicas 명시 + HPA | 두 컨트롤러가 충돌 | HPA 사용 시 Deployment.replicas 제거 또는 무시 |
| target 값이 너무 높음 (90%+) | 트리거 늦어 응답 지연 | 50~70% 권장 |
| min과 max 차이가 너무 큼 | 급격한 스케일 변동 | 환경에 맞는 합리적 범위 |

---

## 우리 프로젝트 체크리스트

```
[✅] metrics-server 설치 (EKS Add-on)
[✅] api Deployment에 resources.requests 설정
[✅] HPA 매니페스트 작성 (helm 차트 templates)
[✅] values-production.yaml에서 autoscaling.enabled: true
[ ] hey로 부하 → HPA 스케일 → Karpenter 노드 추가 검증
```

---

## 참고

- HPA 공식 문서: https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/
- metrics-server: https://github.com/kubernetes-sigs/metrics-server
- autoscaling/v2 API: https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.32/#horizontalpodautoscaler-v2-autoscaling
