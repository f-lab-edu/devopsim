# Kubernetes

## 클러스터란

클러스터는 물리적 실체가 아닌 **노드들의 논리적 묶음**이다. 실제 트래픽은 항상 노드 → Pod 경로를 따른다.

```
클러스터 (논리적 개념)
  ├── Node A
  │     ├── Pod (api)
  │     ├── Pod (api)
  │     └── kube-proxy, kubelet
  └── Node B
        ├── Pod (api)
        └── kube-proxy, kubelet
```

---

## 오브젝트 분류

```
Workload        → 실제 컨테이너 실행
  Deployment      stateless 앱 (api, detector)
  StatefulSet     stateful 앱 (DB — Pod 이름/PVC 고정)
  DaemonSet       모든 노드에 1개씩 (Promtail, kube-proxy)
  Job / CronJob   일회성/반복 실행

Network         → 트래픽 라우팅/노출
  Service         내부 통신 (ClusterIP)
  Ingress         외부 → 내부 라우팅 규칙

Config          → 설정/시크릿
  ConfigMap       일반 설정값
  Secret          민감한 값 (DB 비밀번호, API 키)

Storage
  PVC             Pod가 요청하는 스토리지
  PV              실제 스토리지 (EBS, NFS 등)
```

---

## Service

### Service는 클러스터 레벨 오브젝트

특정 노드에 종속되지 않는다. 하지만 실체는 노드의 iptables 규칙으로 구현된다.

```
kubectl apply -f service.yaml
  ↓
K8s API 서버가 Service 오브젝트 저장 (etcd)
  ↓
모든 노드의 kube-proxy가 변경 감지
  ↓
각 노드 iptables에 규칙 추가:
  "ClusterIP:80으로 오면 → 살아있는 Pod IP 중 하나로"
```

**Service는 설계도, iptables 규칙이 실제 구현체다.**

### ClusterIP — 가상 IP

```
api Pod 1  10.244.0.3
api Pod 2  10.244.0.4   ← Pod IP는 재시작마다 바뀜
api Pod 3  10.244.0.5

Service ClusterIP  10.96.78.209  ← 고정 가상 IP (실제 인터페이스 없음)
```

ClusterIP는 어떤 노드에도 실제로 존재하지 않는다. 패킷이 이 IP로 오면 iptables가 가로채서 실제 Pod IP로 변환한다.

```
논리 레이어 (K8s API)     물리 레이어 (각 노드)
─────────────────────     ─────────────────────
Service 오브젝트    →     iptables 규칙
ClusterIP (가상)    →     Pod IP (실제)
```

### 실제 요청 흐름

```
curl http://10.96.78.209/health  (ClusterIP)
  ↓
패킷이 노드 네트워크 인터페이스에 도착
  ↓
iptables 규칙 매칭 → ClusterIP를 실제 Pod IP로 치환
  ↓
10.244.0.4:3000 (실제 Pod) 으로 전달
```

### CoreDNS — 클러스터 내부 DNS

K8s 표준 컴포넌트. minikube, EKS, GKE 모두 기본 포함.

```bash
kubectl get pods -n kube-system | grep coredns
# coredns-7d764666f9-wtc7w   1/1   Running
```

```
api Pod 안에서 db:5432 접근
  ↓
CoreDNS: "db" → db.default.svc.cluster.local → ClusterIP 10.96.x.x
  ↓
iptables → 실제 db Pod IP
```

### kube-proxy

모든 노드에 DaemonSet으로 존재. 트래픽을 직접 받지 않고 **iptables 규칙을 관리**한다.

```
kube-proxy (데몬, 항상 실행 중)
  → K8s API 서버 감시
  → Service/Endpoint 변경 감지
  → 해당 노드의 iptables 규칙 업데이트
```

실제 패킷 라우팅은 Linux 커널의 iptables가 처리한다. kube-proxy는 규칙 관리자 역할.

---

## Ingress

### Ingress도 클러스터 레벨 오브젝트

규칙 선언만 하고 실제 트래픽 처리는 **Ingress Controller Pod**가 담당한다.

```
Ingress 오브젝트 (규칙 선언)
  ↓ Controller가 읽음
Ingress Controller Pod (노드에 존재)
  ↓
Service (ClusterIP)
  ↓
Pod
```

### 실제 외부 요청 흐름

```
https://api.devopsim.com/health
  ↓
DNS 조회 → ALB IP 반환
  ↓
ALB (AWS 인프라, 노드 밖)
  ↓
노드 IP:Port 직접 연결
  ↓
노드의 iptables
  ↓
nginx Controller Pod or Pod
```

"클러스터가 중앙에서 받아서 전달"하는 게 아니다. 항상 특정 노드로 직접 연결된다.

### 로컬 vs AWS 구조

| | minikube (로컬) | AWS EKS |
|---|---|---|
| Controller | nginx Pod (노드에 존재) | AWS ALB (노드 밖 AWS 인프라) |
| 노드 장애 시 | 통신 불가 (단일 노드) | 다른 노드로 계속 서비스 |
| 외부 접근 | minikube tunnel → 127.0.0.1 | ALB DNS 주소 |

로컬은 노드가 하나라 노드 죽으면 모든 통신 불가. 멀티 노드 HA는 EKS에서만 의미 있다.

### minikube에서의 흐름

```
curl http://127.0.0.1/health
  ↓
minikube tunnel → 127.0.0.1을 minikube 노드 IP로 포워딩
  ↓
노드(minikube VM)의 nginx Controller Pod
  ↓
iptables → api Pod
```

### nginx → ALB 전환

Ingress 오브젝트 스펙은 동일. `ingressClassName`과 `annotations`만 변경.

```yaml
# 로컬
ingressClassName: nginx

# AWS EKS
ingressClassName: alb
annotations:
  alb.ingress.kubernetes.io/scheme: internet-facing
  alb.ingress.kubernetes.io/target-type: ip
```

ALB Controller가 Ingress를 읽고 AWS ALB를 자동 생성한다.

---

## StatefulSet vs Deployment

| | Deployment | StatefulSet |
|---|---|---|
| Pod 이름 | 랜덤 해시 (api-xxx) | 고정 순번 (db-0, db-1) |
| PVC | 공유 또는 없음 | Pod마다 자동 생성 |
| 재시작 시 PVC | - | 같은 Pod가 같은 PVC에 재연결 |
| 주 용도 | stateless 앱 | DB 등 stateful 앱 |
| 스케일 순서 | 동시 | 순서대로 (0→1→2) |

StatefulSet의 `volumeClaimTemplates`:
```yaml
volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]  # 노드 1개에서만 읽기/쓰기
      resources:
        requests:
          storage: 1Gi
```

`ReadWriteOnce` — 하나의 노드에서만 마운트 가능. postgres는 동시에 여러 곳에서 쓰면 데이터 손상 위험.

`StatefulSet` 삭제해도 PVC는 유지된다 (데이터 보호). 완전 초기화하려면 PVC 별도 삭제 필요.

### PostgreSQL Replication — 볼륨 공유가 아닌 복제

Replica는 볼륨을 공유하지 않는다. 각자 별도 볼륨을 가지고 데이터를 복제한다.

```
db-0 (Primary)  →  data-db-0 (PVC)  ← 쓰기/읽기
db-1 (Replica)  →  data-db-1 (PVC)  ← 읽기 전용
db-2 (Replica)  →  data-db-2 (PVC)  ← 읽기 전용

복제 흐름:
클라이언트 → db-0 쓰기
               ↓ WAL Streaming (거의 실시간, 밀리초 단위)
            db-1, db-2가 자기 볼륨에 반영
```

볼륨을 공유하지 않는 이유:
- PostgreSQL은 하나의 프로세스만 파일 접근을 가정하고 설계됨
- 여러 Pod가 같은 볼륨에 쓰면 파일 락 충돌 → 데이터 손상

`ReadWriteMany(RWX)` 공유 볼륨은 파일 서버, 정적 파일 서빙 등에 사용하고 DB에는 절대 사용하지 않는다.

### replicas: 1인 이유

단순히 `replicas: 3`으로 올린다고 Read Replica가 되지 않는다.

```
replicas: 3 으로만 설정하면:
  db-0, db-1, db-2 → 각자 독립된 DB로 뜸
  데이터 복제 없음, 서로 다른 데이터
```

PostgreSQL Replication을 구성하려면:
- Primary/Replica 역할 설정
- WAL Streaming 설정
- `pg_hba.conf` 인증 설정
- 장애 시 Failover 처리 (Patroni 등 HA 솔루션)

지금 단계에서는 단일 인스턴스(replicas: 1)로 -> Read Replica 설정은 week8에서 RDS Read Replica로 진행 예정.

---

## Helm Hook과 K8s Job

### Job이 Pod를 만드는 주체

```
helm install or kubectl apply
  ↓
K8s API 서버에 Job 오브젝트 생성 요청
  ↓
K8s 스케줄러가 빈 노드 찾아서 Pod 배치 결정
  ↓
kubelet(노드 에이전트)이 컨테이너 실행
  ↓
migrate 완료 → Pod 종료 (exit 0)
  ↓
Job 컨트롤러가 완료 확인
```

### Kustomize vs Helm Hook 순서 보장

**Kustomize 방식:**
```bash
kubectl apply -k overlays/local
  → db, api, migrate Job 동시 생성 (순서 보장 없음)
  → migrate Job의 wait-for-db initContainer가 대기 역할
```

**Helm Hook 방식:**
```
helm install
  → pre-install hook: migrate Job 실행 + 완료 대기
  → 완료 후: Deployment, StatefulSet 배포
```

Helm이 명시적으로 순서를 보장한다.

### pre-install vs post-install — deadlock 주의

같은 Chart 안에 DB와 migrate가 함께 있을 때 `pre-install`은 deadlock 발생:

```
pre-install hook 실행
  → migrate Job 생성
  → wait-for-db: db 기다림
  → db는 hook 완료 후 생성 예정
  → 영원히 대기 (deadlock)
```

해결: db를 별도 Chart로 분리 → api install 전에 db가 이미 존재 → `pre-install` 정상 동작.
