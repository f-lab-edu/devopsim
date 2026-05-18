# t3a.small 노드의 Pod density 한계로 DaemonSet Pending

## 증상

Loki + Alloy 배포 직후 4개 노드 중 한 곳에 alloy DaemonSet Pod이 영원히 Pending.

```
$ kubectl get pods -n monitoring -l app.kubernetes.io/name=alloy -o wide
NAME          READY   STATUS    NODE
alloy-8b69p   2/2     Running   ip-10-0-11-214 (t3.medium)
alloy-8c5v2   0/2     Pending   <none>          ← 안 뜸
alloy-j6g9l   2/2     Running   ip-10-0-10-59  (t3.medium)
alloy-vmzs7   2/2     Running   ip-10-0-10-48  (t3a.medium)
```

이벤트:

```
$ kubectl describe pod alloy-8c5v2 -n monitoring
...
Warning  FailedScheduling  0/4 nodes are available:
  1 Too many pods, 3 node(s) didn't satisfy plugin(s) [NodeAffinity].
```

- `Too many pods` = 노드 1개의 Pod 한계 도달.
- `NodeAffinity` = 나머지 3개는 이미 alloy가 떠 있어 affinity로 제외 (DaemonSet은 노드당 1 Pod).

## 원인

### 1. AWS VPC CNI의 Pod density 공식

EKS default CNI = AWS VPC CNI는 **노드 ENI 수 × IP per ENI - 1** 을 노드의 Pod 상한으로 잡는다 (`hostNetwork: true` 제외). 인스턴스 타입별 ENI/IP 수:

| 인스턴스 | ENI | IP/ENI | 이론 max | EKS allocatable |
|---|---|---|---|---|
| t3a.nano | 2 | 2 | 3 | 4 |
| t3a.micro | 2 | 2 | 3 | 4 |
| t3a.small | 3 | 4 | 11 | **8** |
| t3a.medium | 3 | 6 | 17 | **17** |
| t3a.large | 3 | 12 | 35 | **35** |

EKS는 보수적으로 자체 한계(`.status.allocatable.pods`)를 두고, t3a.small은 8로 노출됨.

### 2. 우리 t3a.small 노드 (ip-10-0-11-47)의 현황

```
$ kubectl get pods -A --field-selector spec.nodeName=ip-10-0-11-47.us-east-2.compute.internal
api          api-5db6c98d99-z6slc                          1/1   Running  ← 1
kube-system  aws-load-balancer-controller-...vcclk         1/1   Running  ← 2
kube-system  aws-node-dt8vk                                2/2   Running  ← 3 (CNI DS)
kube-system  ebs-csi-node-cdscp                            3/3   Running  ← 4 (CSI DS)
kube-system  kube-proxy-rns5b                              1/1   Running  ← 5 (DS)
monitoring   kube-prometheus-stack-kube-state-metrics-...  1/1   Running  ← 6
monitoring   kube-prometheus-stack-prometheus-node-exporter-...  1/1   Running  ← 7 (DS)
redis        redis-56d6f9f884-jk59j                        1/1   Running  ← 8
```

→ 8/8 가득참. 9번째 자리 = alloy DS 갈 곳 없음.

### 3. 데이터 손실 범위

alloy 미배포 노드의 Pod 로그는 Loki에 수집 안 됨:
- `api` Pod 1개 — 다른 노드에 다른 replica가 있어 부분 손실
- `redis` Pod — 1 replica라 전체 손실
- aws-node, kube-state-metrics, node-exporter 등 시스템 컴포넌트 로그도 손실

## 해결책 검토

| 옵션 | 효과 | 비용 |
|---|---|---|
| **A. 무시** | 데이터 부분 손실 | 0 |
| **B. AWS VPC CNI prefix delegation** | Pod limit ~110 (모든 노드 타입) | aws-node DS env에 `ENABLE_PREFIX_DELEGATION=true` + 노드 교체 필요. 전 클러스터 영향 |
| **C. NodePool에서 small 이하 제외** | 다음 consolidation 때 t3a.medium+ 로 교체 | NodePool 한 줄 수정 (✅ 채택) |
| **D. alloy `hostNetwork: true`** | Pod IP 안 받음 → 한계 무관 | listen port 12345 호스트와 충돌 위험, 보안 분리 깨짐 |

C 채택 이유:
- devopsim 워크로드 기준 t3a.medium 정도면 충분하고 비용 차이도 미미.
- prefix delegation은 운영 클러스터에서 도입할 만한 정석이지만 학습 단계엔 오버킬.
- 한 줄 수정으로 즉시 효과.

## 적용

### NodePool 수정

`infra/flux/clusters/prod/infrastructure/configs/karpenter-nodepool.yaml`:

```yaml
spec:
  template:
    spec:
      requirements:
        # ... 기존 requirements ...
        - key: karpenter.k8s.aws/instance-size
          operator: NotIn
          values: ["nano", "micro", "small"]
```

### 적용 후 동작

1. Flux가 NodePool CRD 업데이트
2. Karpenter consolidation 루프(`consolidateAfter: 1m`)가 기존 t3a.small을 drift 판정
3. 새 medium+ 노드 provision → 기존 small의 Pod 들 drain → 이전
4. alloy DaemonSet이 새 노드에 자동 배치 → 8c5v2 Pending 해소

## 재현/검증 명령어

```bash
# 1. Pending alloy pod 있는지
kubectl get pods -n monitoring -l app.kubernetes.io/name=alloy --field-selector status.phase=Pending

# 2. 노드별 Pod capacity vs 실제 사용량
kubectl get nodes -o custom-columns='NAME:.metadata.name,SIZE:.metadata.labels.karpenter\.k8s\.aws/instance-size,POD_CAP:.status.allocatable.pods'

for node in $(kubectl get nodes -o name); do
  count=$(kubectl get pods -A --field-selector spec.nodeName=${node##*/} --no-headers | wc -l)
  echo "${node##*/}: $count pods"
done

# 3. NodePool 변경 후 Karpenter가 drift 판정한 노드
kubectl get nodeclaim
```

## 학습 메모

- DaemonSet은 노드당 1 Pod이 원칙 → **노드 Pod density가 작으면 DaemonSet이 못 올라가 관측성 사각지대 발생**.
- 이번 케이스의 본질은 "AWS VPC CNI가 노드 ENI/IP에 묶여 있어 작은 인스턴스에 Pod이 많이 못 뜬다". 다른 CNI(Cilium native routing, Calico VXLAN 등) 쓰면 Pod limit이 ENI와 무관.
- prefix delegation은 EKS에서 흔히 권장되는 정석이지만 기존 클러스터에 적용하려면 노드 교체가 필요. 신규 클러스터는 처음부터 켜는 게 정답.
- 가벼운 워크로드라도 t3a.small은 K8s에서 자주 함정. **DaemonSet이 많은 환경(VPC CNI + EBS CSI + node-exporter + alloy + ...)은 최소 medium 권장**.
