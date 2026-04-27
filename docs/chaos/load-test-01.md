# 부하 테스트 #01 — HPA + Karpenter 검증

> 일시: 2026-04-28 02:52 ~ 03:10 (약 18분)
> 목적: hey로 부하 발생시켜 HPA 자동 스케일 + Karpenter 노드 자동 생성 동작 확인

---

## 환경

| 항목 | 값 |
|------|-----|
| 클러스터 | devopsim-prod-cluster (EKS 1.35) |
| 부하 도구 | hey |
| 대상 엔드포인트 | `GET /chaos/cpu?ms=N` (이벤트 루프를 N ms 점유) |
| ALB | `k8s-default-api-1e12d1a238-2007786267.us-east-2.elb.amazonaws.com` |

### api 설정
- Deployment requests: cpu 100m, memory 128Mi
- Deployment limits: cpu 500m, memory 256Mi
- HPA: minReplicas=2, maxReplicas=10, targetCPUUtilizationPercentage=50

### 노드 구성 (테스트 시작 시점)
- 관리형 노드 그룹: t3.medium × 2 (taint: CriticalAddonsOnly, 시스템 Pod 전용)
- Karpenter NodePool: t3a.micro × 2 (직전 배포 잔재)

---

## 초기 상태 (Phase 0)

```
HPA:        replicas=2, TARGETS=cpu 6%/50%
api Pods:   2개 (각 t3a.micro에 1개씩)
Karpenter:  t3a.micro × 2 (us-east-2a, us-east-2b)
Pod CPU:    ~5m (거의 idle)
```

---

## Phase 1 — 가벼운 부하 (30초, c=2, ms=300)

```bash
hey -z 30s -c 2 -q 1 "$ALB/chaos/cpu?ms=300"
```

### hey 결과
```
Status code distribution: [200] 60 responses
Latency p50: 0.516s, p95: 0.589s, p99: 0.589s
```

### 즉시 상태 변화
```
Pod CPU 사용량: 8m → 207m (+2486%)
HPA TARGETS:   6%/50% → 105%/50%   ← 임계점 돌파!
```

### 의도와 결과의 차이
**의도:** "기준선" 확인 (스케일 안 일어남)
**실제:** 이미 HPA 트리거 조건 도달

원인: `/chaos/cpu?ms=300`이 단일 worker로도 충분히 강한 부하. ms=300 = 0.3 CPU-second/req, 2 worker × 1 RPS = 0.6 CPU-second/s = Pod 1개의 60% 점유.

→ 우리 환경에서 "안전한 기준선"은 ms=100 이하 또는 c=1로 시작해야 함.

### 60초 후 (HPA 반응 + Karpenter 노드 생성)
```
HPA:       replicas 2 → 9 (한 번에 4.5배 점프)
Pods:      9개 (1개는 PodInitializing)
Karpenter: 노드 +3 추가
  - ip-10-0-10-239 (t3a.small)  ← 새로 등장
  - ip-10-0-10-247 (t3a.micro)
  - ip-10-0-10-96  (t3a.micro)
```

**관찰:** Karpenter가 처음으로 t3a.small을 선택. 이전 배포에서는 t3a.micro만 골랐는데, 5개 Pod를 한 노드에 몰아넣는 게 더 효율적이라고 판단한 결과 (bin-packing).

---

## Phase 2 — 중간 부하 (2분, c=10, ms=500)

```bash
hey -z 2m -c 10 "$ALB/chaos/cpu?ms=500"
```

### hey 결과
```
Status code distribution: [200] 1597 responses
Latency p50: 0.709s, p95: 1.073s, p99: 1.207s
RPS:         약 13 RPS (이론 20 RPS 미만, 응답 시간으로 자연 제한)
```

### 종료 시점 상태
```
HPA TARGETS:   385%/50% (사용률 폭증)
HPA REPLICAS:  9 → 10 (max 도달)
Karpenter 노드: 5개 (+1 추가, ip-10-0-11-19)
```

**관찰:** HPA가 max에 막혀 더 이상 Pod를 못 늘림. Pod 1개당 200%+ 사용률 (limits 500m이라 burst 가능).

---

## Phase 3 — 고부하 (3분, c=30, ms=500)

```bash
hey -z 3m -c 30 "$ALB/chaos/cpu?ms=500"
```

### hey 결과
```
Status code distribution: [200] 3033 responses (실패 0)
Latency p50: 1.458s  ← Phase 2 대비 2배
Latency p95: 3.895s
Latency p99: 7.427s  ← 대기열 누적, 최대 11.7s
```

### 종료 시점 상태
```
HPA TARGETS:   381%/50% (변화 없음, 이미 max)
REPLICAS:      10 (변화 없음)
Karpenter 노드: 5개 (변화 없음)

Pod CPU 사용량 (Phase 3 끝):
  api-...-4pdqw:  330m
  api-...-5xd7t:  358m
  api-...-7jl2r:  296m
  api-...-9xg4f:  498m  ← limits 500m 직전, throttle 가능성
  api-...-b9tc4:  300m
  api-...-dcmb4:  417m
  api-...-k9nb8:  426m
  api-...-l8kbd:  258m
  api-...-sh67w:  275m
  api-...-wwftk:  437m
```

**관찰:** maxReplicas=10에 막혀서 Pod도 노드도 더 이상 안 늘어남. 결과적으로 latency가 폭증 (대기열 쌓임). 제한이 Karpenter가 아니라 HPA에 있었음.

---

## Phase 4 — 쿨다운 관찰 (10분+)

부하 중단 후 자동 축소 흐름.

### 시간별 변화

| 시점 | HPA 사용률 | Replicas | Karpenter 노드 |
|------|-----------|----------|---------------|
| T+0   | 381%     | 10 | 5 |
| T+1m  | 5%       | 10 | 5 |
| T+2m  | 6%       | 10 | 5 |
| T+5m  | 5%       | 10 | 5 |
| T+7m  | 5%       | 10 | 5 |
| **T+10m** | **4%** | **2** | **5 (Pod 종료 진행 중)** |
| T+14m | 4%       | 2  | **2** ← consolidation 완료 |

### 핵심 관찰

**HPA scaleDown stabilization window**
- 사용률이 5% 떨어진 후에도 **5분간** replicas 그대로
- 이건 HPA의 기본 안정화 정책 (`scaleDown.stabilizationWindowSeconds: 300`)
- "혹시 다시 부하 올까봐" 즉시 줄이지 않음

**Karpenter consolidation**
- HPA가 Pod 줄인 후, 노드는 즉시 사라지지 않음
- Pod가 완전히 종료되고 노드가 비어야 → 1분(우리 설정) 후 종료
- consolidation 과정에서 **새 노드(ip-10-0-11-56) 만들고 옛 노드 삭제**하는 케이스도 관찰
  → 더 효율적 배치를 위해 Karpenter가 노드를 교체

### 최종 상태
```
HPA:        replicas=2, TARGETS=4%/50%
api Pods:   2개 (양쪽 AZ 분산)
Karpenter:  t3a.micro × 2 (초기와 거의 동일하지만 다른 노드 인스턴스)
```

---

## 학습 포인트

### 1. /chaos/cpu의 강도 산정
ms=300 + c=2 만으로도 HPA target 50%를 5배 가까이 돌파. 부하 점진 증가가 의도라면 **ms를 더 작게(100~150)** 또는 **c=1로 시작**.

### 2. HPA의 공격적 스케일업
사용률 105%에서 한 번에 replicas 2 → 9로 점프. HPA는 사용률 비율만큼 늘리려 함:
```
필요 = 현재 × (사용률 / 목표) = 2 × (105/50) ≈ 4.2 → 5개 정도 예상
실제: 9개  ← 더 공격적
```
이유: HPA는 일정 안정화 후 더 보수적으로 줄이지만, 늘릴 때는 공격적 (default `scaleUp.stabilizationWindowSeconds: 0`).

### 3. Karpenter의 bin-packing 효과
첫 노드 생성 시 t3a.micro만 선택했는데, Pod 5개 동시 발생 시 t3a.small 선택. **여러 Pod를 한 노드에 몰아넣는 게 더 비용 효율적**이라는 판단. 인스턴스 카테고리 자유도가 클수록 이 효과 큼.

### 4. HPA가 병목이 될 수 있음
Phase 3에서 maxReplicas=10에 막혀 latency 7초까지 증가. 카오스 시뮬레이션에선 maxReplicas를 좀 더 높여야 진짜 "Karpenter가 한계까지 노드 늘리는" 흐름을 볼 수 있음.

### 5. AZ 분산은 자연 발생할 수도, 안 할 수도
이번 테스트에서는 어떤 노드는 한 AZ(us-east-2a)에 몰리고, 일부만 us-east-2b로 갔다. `topologySpreadConstraints` 설정 안 한 상태라 Karpenter가 비용 우선으로 배치. 실무에선 명시적으로 분산 설정해야 함.

### 6. limits 500m가 Pod throttling 직전까지 사용됨
Phase 3 끝 시점 9xg4f Pod가 498m. limits 500m와 거의 동일. 더 부하 들어왔다면 throttle 발생. Burst limits 산정 시 워크로드 특성 고려 필요.

---

## 다음 실험 아이디어

```
[A] /chaos/cpu 강도 조절
    ms=100, c=1 → ms=200, c=2 → ms=300, c=4
    부드러운 단계적 부하로 HPA 반응 곡선 정밀 측정

[B] maxReplicas 상향 (10 → 20)
    HPA 한도가 풀리면 Karpenter가 어디까지 노드 늘리는지

[C] topologySpreadConstraints 추가
    AZ 강제 분산 vs 자연 배치 결과 비교

[D] Spot 인스턴스 도입
    NodePool에 spot 추가 → 가격 변동 따라 인스턴스 선택 차이
    SQS 인터럽션 처리 동작 확인

[E] PDB 추가 후 동일 테스트
    drain 시 동시 종료 제한 효과 측정

[F] 쿨다운 시 HPA scaleDown 정책 조정
    stabilizationWindow 짧게 (60s) → 빠른 축소 vs 안정성 트레이드오프
```

---

## 시간선 요약

```
02:52  Phase 1 시작 (30s)
02:53  HPA 트리거 → replicas 2 → 9, Karpenter 노드 +3
02:54  Phase 2 시작 (2m)
02:56  HPA replicas 10 (max 도달), Karpenter 노드 +1 (총 5개)
02:57  Phase 3 시작 (3m)
03:00  Phase 3 종료, 부하 중단
03:06  HPA 안정화 끝 → replicas 10 → 2 급감
03:10  Karpenter consolidation 완료, 노드 5 → 2
```

---

## 참고

- hey: https://github.com/rakyll/hey
- HPA 동작 원리: [docs/hpa.md](../hpa.md)
- Karpenter NodePool/EC2NodeClass: [docs/karpenter.md](../karpenter.md)
