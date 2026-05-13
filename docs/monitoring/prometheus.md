# Prometheus Stack 도입 기록

## 1. Prometheus가 뭐고 어떻게 동작하나

**Prometheus**는 시계열(time-series) 메트릭 수집/저장/질의 시스템. 핵심 특징:

- **Pull 모델**: Prometheus 서버가 주기적으로 대상 앱의 `/metrics` 엔드포인트를 HTTP로 가져옴 (push 모델인 StatsD/InfluxDB와 반대)
- **TSDB**: 자체 시계열 DB에 저장. label 기반 다차원 모델
- **PromQL**: 시계열 질의 언어 (`rate()`, `histogram_quantile()`, `sum by(...)`)
- **Service Discovery**: K8s API와 연동해 어떤 endpoint에서 메트릭을 가져갈지 자동 발견

### 동작 흐름

```
[앱 Pod]
  └─ /metrics (HTTP) 노출
        ↑
        │ (1) HTTP GET — 보통 15s 주기, 이게 "scrape"
        │
[Prometheus 서버]
  ├─ scrape config: 어디서 무엇을 가져올지
  ├─ TSDB: 가져온 시계열을 메모리/디스크에 저장
  ├─ PromQL 엔진: query 처리
  └─ /api/v1/query, /api/v1/query_range API 노출
        ↑
        │ (2) Grafana가 datasource로 PromQL 실행
        │
[Grafana 대시보드]
```

### Read / Write 동작 방식

| 동작 | 주체 | 시점 | 흐름 |
|---|---|---|---|
| **Write** (수집) | Prometheus 서버 | scrape interval(기본 15s)마다 | 대상 `/metrics` GET → 파싱 → TSDB에 append |
| **Read** (질의) | Grafana / `promtool query` / 직접 API | on-demand | PromQL → TSDB에서 시계열 조회 → 결과 반환 |

**왜 Pull 모델인가?**
- 앱은 메트릭만 노출하면 됨, 어디로 보낼지 신경 X
- 앱이 죽으면 scrape failure → "이 앱 이상함"이 자동 신호
- 인증/방화벽 관리가 단일 방향 (Prometheus → 앱)
- 단점: NAT 뒤 / 단명 Job(batch)엔 부적합 → Pushgateway로 보완

### 라벨/시계열 기반 모델

```
http_requests_total{method="GET", route="/api/items", status="200"} 1234
http_requests_total{method="GET", route="/api/items", status="500"} 7
```

같은 metric name이라도 라벨 조합이 다르면 **다른 시계열**. 라벨에 가변 값(id, timestamp 등)을 쓰면 시계열이 무한 증가 → cardinality 폭발 → OOM. 항상 유한한 라벨만 사용.

---

## 2. 설치

**Helm chart**: `prometheus-community/kube-prometheus-stack` v84.5.0 (Operator v0.90.1)
**Namespace**: `monitoring`

### 설치된 컴포넌트

| 컴포넌트 | 종류 | 역할 |
|---|---|---|
| **Prometheus Operator** | Deployment | CRD를 watch해서 Prometheus/Alertmanager StatefulSet, Secret(scrape config) 등을 생성·관리 |
| **Prometheus** | StatefulSet (Operator가 생성) | 메트릭 수집 + TSDB 저장 + PromQL 처리. PVC 10Gi (gp3) 사용 |
| **Alertmanager** | StatefulSet (Operator가 생성) | 알림 라우팅/그룹화/억제. PVC 2Gi |
| **Grafana** | Deployment | 시각화 + 기본 대시보드. Prometheus를 datasource로 자동 provisioning |
| **kube-state-metrics** | Deployment | K8s 객체 상태(Pod/Deployment/Node 등)를 메트릭으로 노출 |
| **node-exporter** | DaemonSet | 노드별 시스템 메트릭(CPU/메모리/디스크/네트워크) |
| **kube-prometheus-stack-operator (admission)** | Job (Helm hook) | 차트 설치 시 ValidatingWebhook 인증서 패치 |

### 외부 노출

세 UI 모두 ALB Ingress + `alb.ingress.kubernetes.io/group.name=monitoring` annotation으로 **단일 ALB 공유** (비용 절감).

```
ALB (group=monitoring)
  ├─ /  → Grafana
  ├─ /  → Prometheus
  └─ /  → Alertmanager
```

(host 기반 라우팅 없이 path만으로 분기 — 도메인 추가 시 host로 분리 권장)

---

## 3. 등록된 CRD와 역할 (10개)

CRD는 모두 `monitoring.coreos.com` 그룹. **Prometheus Operator**가 모두 watch하면서 실제 K8s 리소스로 변환합니다.

### CRD 목록과 흐름

| CRD | 역할 | 컨트롤러가 만드는 실제 K8s 객체 |
|---|---|---|
| **`prometheuses`** | Prometheus 서버 인스턴스를 declarative하게 정의 | `StatefulSet`(prometheus-*), `Service`, `Secret`(생성된 prometheus.yml) |
| **`alertmanagers`** | Alertmanager 인스턴스 정의 | `StatefulSet`(alertmanager-*), `Service`, `Secret` |
| **`servicemonitors`** | Service의 Endpoints를 scrape 대상으로 등록 (앱 Pod 메트릭 수집) | Prometheus의 scrape config(Secret)에 자동 추가 |
| **`podmonitors`** | Service 없이 Pod label로 직접 scrape | 동일 (Service를 거치지 않을 때) |
| **`probes`** | Blackbox 모니터링 — 외부 URL ping/HTTP check | scrape config (Blackbox exporter 경유) |
| **`scrapeconfigs`** | 임의 scrape 설정을 직접 작성 (CRD 없는 외부 시스템) | scrape config |
| **`prometheusrules`** | Recording rule + Alert rule 선언 (PromQL) | Prometheus가 rule 파일로 마운트, evaluation |
| **`alertmanagerconfigs`** | Alertmanager 라우팅 규칙(receiver, route) 선언 | Alertmanager config(Secret)에 통합 |
| **`prometheusagents`** | Prometheus Agent 모드 (수집만, 저장 X. remote_write로 전달) | StatefulSet (agent 모드 Prometheus) |
| **`thanosrulers`** | Thanos ruler 인스턴스 (long-term storage) | StatefulSet (Thanos) |

### 핵심: 컨트롤러는 "Prometheus Operator" 단 하나

```
[CRD: ServiceMonitor 생성]
       ↓
[Prometheus Operator (Deployment) 가 watch]
       ↓
[Prometheus CRD의 selector에 매칭되는 ServiceMonitor 찾음]
       ↓
[Prometheus Operator가 prometheus.yml 재생성 → Secret 업데이트]
       ↓
[Prometheus StatefulSet의 Pod이 config-reloader sidecar로 자동 reload]
       ↓
[새 scrape target 즉시 활성화]
```

**핵심 설계 포인트**: 사용자(우리)는 Prometheus의 raw config (`prometheus.yml`)를 직접 만들지 않고 CRD만 선언. Operator가 변환해서 reload까지 자동.

### ServiceMonitor → Pod 발견 흐름 (우리 api 케이스)

```
1. helm/api/templates/servicemonitor.yaml (values.serviceMonitor.enabled=true) 가
   ServiceMonitor "api" namespace=api 생성
       │
       ├ spec.selector.matchLabels: app.kubernetes.io/name=api
       └ spec.endpoints: [{port: http, path: /metrics, interval: 15s}]
       
2. Prometheus Operator가 ServiceMonitor를 watch
       │
       └─ Prometheus CRD의 spec.serviceMonitorSelector 가 nil (== 모두 발견)
            ※ helm values: serviceMonitorSelectorNilUsesHelmValues: false 로 강제

3. Operator가 Service 'api' (namespace=api) 의 Endpoints를 가져옴
       │
       └─ 그 Endpoints의 Pod IP들에 대해 scrape config 생성

4. Prometheus Pod이 scrape config 자동 reload → 15s마다 GET http://<pod-ip>:3000/metrics
```

### 자동 등록된 ServiceMonitor (kube-prometheus-stack 기본)

```
api/api                                      ← 우리가 추가한 것
monitoring/kube-prometheus-stack-alertmanager
monitoring/kube-prometheus-stack-apiserver
monitoring/kube-prometheus-stack-coredns
monitoring/kube-prometheus-stack-grafana
monitoring/kube-prometheus-stack-kube-controller-manager
monitoring/kube-prometheus-stack-kube-etcd
monitoring/kube-prometheus-stack-kube-proxy
monitoring/kube-prometheus-stack-kube-scheduler
monitoring/kube-prometheus-stack-kube-state-metrics
monitoring/kube-prometheus-stack-kubelet
monitoring/kube-prometheus-stack-operator
monitoring/kube-prometheus-stack-prometheus
monitoring/kube-prometheus-stack-prometheus-node-exporter
```

→ K8s 시스템 컴포넌트(apiserver, kubelet, etcd 등)도 자동으로 scrape 대상이 됨.

### 자동 만들어진 인스턴스

| 종류 | 이름 | 결과 객체 |
|---|---|---|
| `Prometheus` | `monitoring/kube-prometheus-stack-prometheus` (v3.11.3) | StatefulSet `prometheus-kube-prometheus-stack-prometheus` |
| `Alertmanager` | `monitoring/kube-prometheus-stack-alertmanager` (v0.32.1) | StatefulSet `alertmanager-kube-prometheus-stack-alertmanager` |

---

## 4. 핵심 설정 — 왜 이렇게 했나

### `serviceMonitorSelectorNilUsesHelmValues: false`

이거 안 켜면 다른 namespace의 ServiceMonitor를 못 봅니다. 우리 api ServiceMonitor는 `namespace=api`라 절대 자동 발견 안 됨.

이 플래그가 false → Prometheus CRD의 `spec.serviceMonitorSelector` 가 `{}`로 설정됨 → "모든 ServiceMonitor 매칭".

기본값(true)은 `release=kube-prometheus-stack` label이 있는 ServiceMonitor만 봄. 같은 chart로 만든 SMonly. 보안 측면에선 default가 안전하지만, 멀티 팀 환경에선 너무 제약.

### TSDB PVC 10Gi (gp3)

Prometheus는 메모리에 가장 최근 시계열 + 디스크에 영속화. retention 15일이면 우리 워크로드 기준 수 GB 정도. 여유 있게 10Gi.

### Ingress group.name = monitoring

3개 Ingress (Grafana/Prometheus/Alertmanager)를 한 ALB로 묶어 비용 절감. AWS LB Controller가 같은 group label 보고 단일 ALB 공유.

---

## 5. 동작 검증 시나리오

### Prometheus Targets에서 우리 api 확인

```
Prometheus UI → Status → Targets
  serviceMonitor/api/api/0  ← Up 상태여야 함
```

### PromQL 예시

```promql
# Cache hit ratio
sum(rate(cache_hits_total[5m])) /
  (sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m])))

# popular DB 쿼리 p95
histogram_quantile(0.95, rate(db_query_duration_seconds_bucket{operation="findPopular"}[5m]))

# popular 엔드포인트 응답시간 p95
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{route="/api/items/popular"}[5m]))

# 풀 부하
pg_pool_waiting_clients

# 에러율
sum(rate(app_errors_total[5m])) by (type)
```

### Grafana 기본 대시보드

`defaultDashboardsEnabled: true` 덕분에 자동 import됨:
- "Kubernetes / Compute Resources / Cluster"
- "Kubernetes / Compute Resources / Namespace (Pods)"
- "Node Exporter / Nodes"

api 전용 대시보드는 위 PromQL로 직접 만들면 됨.

---

## 6. 다음 단계 (이후 작업)

- api 전용 Grafana 대시보드 (cache hit ratio, popular p95, items_total trend)
- PrometheusRule로 alert rule 작성 (예: cache hit ratio < 50% 5분 지속 → alert)
- Read/Write 분리 후 Replica 트래픽 비율 모니터링
- (운영 시) Prometheus UI에 OAuth proxy 추가 — 지금은 익명 접근 가능

---

## 7. 오퍼레이터 패턴 (Operator Pattern)

**핵심**: 도메인 지식을 코드로 만든 컨트롤러가 CRD를 reconcile하는 패턴.

기본 K8s 컨트롤러는 Pod/Deployment 같은 범용 객체만 다룸. Operator는 도메인 객체(Prometheus, Kafka, Postgres 등)를 위한 CRD를 정의하고, 그 도메인의 운영 노하우(config reload, rolling restart, backup, version upgrade)를 자동화한다.

### 일반 컨트롤러 vs 오퍼레이터

| 항목 | 일반 컨트롤러 | 오퍼레이터 |
|---|---|---|
| 대상 | 범용 객체 (Deployment, Service) | 도메인 객체 (Prometheus, Kafka, PG) |
| 지식 | "Pod 6개 떠 있어야 함" | "쓰기 마스터 죽으면 슬레이브 승격" |
| 결과물 | ReplicaSet, Pod | StatefulSet + Secret + Service + 도메인 후처리 |

### Reconciliation Loop

```
[CR 변경 감지]
    ↓
[desired state 계산]
    ↓
[현재 state 조회]
    ↓
[diff → K8s API에 patch/create/delete]
    ↓
[Status 업데이트]
    ↓ (주기적으로 반복)
```

### Prometheus Operator의 구체적 일

| 트리거 | Operator의 동작 |
|---|---|
| `Prometheus` CR 생성 | StatefulSet, Service, RBAC, Secret(prometheus.yml) 생성 |
| `ServiceMonitor` 생성/변경 | 매칭되는 Prometheus의 scrape config 재생성 → Secret 업데이트 |
| `PrometheusRule` 변경 | rule 파일 생성 → Pod에 마운트된 ConfigMap 업데이트 → sidecar reload |
| Prometheus 버전 업그레이드 | StatefulSet image tag 변경 → rolling restart |
| `Alertmanager` CR 변경 | StatefulSet + Secret(alertmanager.yml) 재생성 |

**우리에게 의미하는 것**: devopsim은 Prometheus Operator를 사용 중(`kube-prometheus-stack` Helm chart에 포함). 덕분에 우리는 `prometheus.yml`을 직접 작성하지 않고 ServiceMonitor / PrometheusRule CRD만 git에 커밋한다. Operator가 그걸 raw config(Secret)로 번역하고 Pod reload까지 처리.

---

## 8. 데이터가 저장되는 방법 (TSDB 구조)

Prometheus는 자체 시계열 DB(TSDB)를 사용. 디스크 구조:

```
storage/
├── wal/                  # Write-Ahead Log (메모리 변경의 영속화 보장)
│   ├── 00000001
│   └── 00000002
├── chunks_head/          # 메모리에 있는 head block의 chunk 파일
├── 01HXXX.../            # Block (보통 2시간 단위, immutable)
│   ├── chunks/           # 압축된 시계열 데이터
│   ├── index             # label → chunk posting list
│   ├── meta.json         # min/max time, stats
│   └── tombstones        # 삭제 표시 (실제 삭제는 compaction 시)
└── 01HYYY.../
```

### Write 흐름

```
[scrape (15s)]
   │  sample = (metric, labels, timestamp, value)
   ↓
[Head Block (메모리)]    ── 동시에 WAL 기록 ──> [wal/]
   │  최근 ~3시간 데이터
   ↓ 2시간마다 flush
[새 Block 생성 (immutable)]
   │  blockN/{chunks, index, meta.json}
   ↓
[일정 시간 후 compaction]
   2h+2h → 6h → 1d → ...
```

### Read 흐름

```
[PromQL: rate(http_requests_total{route="/api"}[5m])]
   ↓
[Inverted Index (postings) 조회]
   route="/api" → 시계열 ID 목록
   ↓
[Chunk 로드 → 압축 해제]
   ↓
[range vector 만들고 rate() 적용]
```

### 핵심 설계 포인트

- **block은 immutable**: 동시성 처리 단순, 백업/이동 용이.
- **inverted index**: label → series ID 역색인. PromQL의 빠른 selector lookup 비결.
- **chunk encoding**: XOR (Gorilla) + double-delta. sample 1개당 평균 1~2 bytes.
- **WAL**: 메모리 head block이 디스크로 flush되기 전에 crash → WAL replay로 복구.

---

## 9. compaction

여러 작은 Block을 더 큰 Block으로 병합하는 백그라운드 과정. **꼭 필요한 이유**:

- 시간 지난 데이터는 query 빈도 낮음 → 큰 block에 합쳐도 안 느림
- 작은 block이 많으면 query 시 모든 block의 index 열람 → 느림
- 삭제 마커(tombstone) 실제 삭제는 compaction 때 일어남
- block 수 자체가 너무 많으면 메타데이터 오버헤드

### 병합 단계

```
초기:   [2h][2h][2h][2h][2h][2h]
1차:    [    6h    ][    6h    ]    # 2h × 3 → 6h
2차:    [        18h            ]   # 6h × 3 → 18h
3차:    더 큰 단위 (retention 한계까지)
```

기본 ratio = 3. retention 안의 데이터 중 가장 오래된 절반까지 compact 가능.

### compaction이 일으키는 문제

- 큰 block 만들 때 메모리 spike (특히 18h+ block) → OOM 위험
- 디스크 IO 부담
- 진행 중 query 느려질 수 있음

→ remote storage(Thanos/Mimir)는 이 부담을 별도 compactor 서비스로 분리.

---

## 10. Prometheus의 단일 프로세스 한계 극복

기본 Prometheus는 **단일 binary, 단일 머신, 로컬 디스크**. 한계:

- HA 없음 (Pod 죽으면 그 시간 메트릭 갭)
- 디스크 용량 = 데이터 양의 상한
- 수평 확장 불가
- 장기 보관 어려움

### 극복 패턴

| 방법 | 핵심 | 장점 | 단점 |
|---|---|---|---|
| **HA Pair** | 동일 config의 Prometheus 2개 동시 실행 | 단순, 다운타임 0 | 데이터 2배 저장, 중복 |
| **Federation** | 상위 Prometheus가 하위를 scrape | 단순 집계 | scale 한계, 정밀도 손실 |
| **Remote Write** | 수집한 데이터를 외부 storage로 push (Mimir/Cortex/VictoriaMetrics/Thanos receive) | 수평 확장, 장기 보관, multi-tenancy | 인프라 추가 |
| **Thanos sidecar** | Prometheus 옆 sidecar가 2h block을 S3 업로드 + querier가 통합 view | 무한 보관, 저렴(S3) | 컴포넌트 다수 (sidecar/store/querier/compactor) |
| **Agent 모드** | 수집만, 로컬 저장 X. remote_write로만 전달 | 가볍고 stateless | 단독으로 query 불가 |
| **샤딩 (hashmod)** | 시계열 hash 기준으로 여러 Prometheus가 분담 | 수평 확장 | 조인 query 복잡 |

### 우리 단계에선?

devopsim은 단일 Prometheus + 15일 retention + 10Gi PVC. 메트릭 양이 적으니 충분.

다음 단계에서 Thanos 또는 Mimir 도입 시:
1. Prometheus에 `remoteWrite` 추가
2. (Thanos일 경우) sidecar StatefulSet 옆에 추가, S3 bucket 연결
3. Grafana datasource를 Thanos querier로 교체

---

## 11. ingestion rate

초당 들어오는 sample 수(samples/sec). 용량 산정의 핵심 지표.

```
ingestion rate = active series 수 / scrape interval

예: active series 100,000개, interval 15s
   → 100,000 / 15 ≈ 6,666 samples/sec
```

### 측정

```promql
# 초당 수집 sample 수
rate(prometheus_tsdb_head_samples_appended_total[5m])

# 현재 active series 수
prometheus_tsdb_head_series

# 시계열당 평균 디스크 사용 bytes
rate(prometheus_tsdb_compaction_chunk_size_bytes_sum[1h])
  / rate(prometheus_tsdb_compaction_chunk_samples_sum[1h])
```

### 용량 산정 공식 (개략)

```
디스크 ≈ ingestion_rate × seconds × bytes_per_sample
       ≈ 6,666 × 86400 × 15일 × 1.5B
       ≈ 약 13 GB
```

→ 우리 PVC 10Gi는 metric churn이 적은 상황 기준 충분, 폭증 대비 20Gi가 안전.

### 너무 높으면

1. **scrape interval 늘림** (15s → 30s → 60s)
2. **고cardinality 라벨 drop** (`metric_relabel_configs`)
3. **불필요한 target 제거** (e.g. `go_gc_*` 같은 디테일)
4. **recording rule**로 미리 집계한 series만 보관 → raw 줄이기
5. **remote_write + agent 모드**로 로컬 부담 0화

---

## 12. metric churn

**같은 metric name인데 라벨이 자주 바뀌어서 새 시계열이 계속 생기는 현상**. cardinality 폭발의 주범.

### 전형적인 churn 예시

```promql
# 나쁜 패턴
http_request_duration_seconds_bucket{request_id="abc123", ...}    # 매 요청마다 새 series
items_view_total{user_id="u-89234", ...}                          # 사용자 수 = series 수
deploy_info{commit="3eaffeb...", started_at="2026-05-13T..."}     # 배포마다 새 series
```

### churn이 일으키는 문제

- TSDB index가 부풀어오름 → 메모리 ↑
- WAL replay 시 시간 ↑
- query latency ↑
- compaction 부담 ↑
- 결국 OOM

### 탐지

```promql
# 최근 10분 동안 새로 등장한 series 수
rate(prometheus_tsdb_head_series_created_total[10m])

# 어떤 metric이 cardinality 많은지
topk(20, count by(__name__)({__name__=~".+"}))

# 어떤 라벨이 unique 값이 많은지
count(count by(label_x) (http_requests_total))
```

### 방지 원칙

- **라벨에 unbounded 값 금지**: id, request_id, timestamp, version_hash 같은 거.
- **enum이 분명한 것만 라벨**: method(GET/POST/...), status(200/4xx/5xx), route(템플릿 경로).
- **이미 발생한 churn**: `metric_relabel_configs`로 drop / 라벨 제거.

---

## 13. kube-state-metrics

**K8s API 객체의 "상태"를 Prometheus 메트릭으로 노출**하는 별도 Deployment. K8s API 서버에 list/watch를 걸어두고 metric으로 변환.

```
사람이 보는 것:  kubectl describe pod ...
Prometheus가 scrape:  kube_pod_status_phase{phase="Running"} = 1
```

### 주요 메트릭

| 메트릭 | 의미 |
|---|---|
| `kube_pod_status_phase{phase, pod}` | Pod 현재 phase |
| `kube_pod_container_status_restarts_total` | 컨테이너 재시작 횟수 (CrashLoop 탐지) |
| `kube_deployment_status_replicas_available` | Deployment 가용 replica 수 |
| `kube_node_status_condition` | NotReady 등 노드 컨디션 |
| `kube_hpa_status_current_replicas` | HPA 현재 replica |
| `kube_persistentvolumeclaim_status_phase` | PVC bound 여부 |

### 특징

- **Stateless**: 단지 K8s API의 "거울". 자신은 데이터 저장 X.
- **kubelet/cAdvisor 메트릭과 별개**: cAdvisor는 컨테이너 리소스 사용량, kube-state-metrics는 K8s 객체 상태.
- 우리 alert 중 `APIDown`, `DBPoolWaiting`은 api custom metric 기반이라 kube-state-metrics 무관. 단, "Pod 자체가 Pending인지", "최근 5분 사이 restart 했는지" 같은 K8s 레벨 alert에는 필수.

---

## 14. node_exporter

**노드 OS 레벨 시스템 메트릭을 노출하는 DaemonSet**. 노드마다 하나씩 Pod 실행, `/proc`·`/sys`를 읽어서 변환.

### 주요 메트릭

| 카테고리 | 메트릭 예시 |
|---|---|
| CPU | `node_cpu_seconds_total{mode="idle|user|system|iowait"}` |
| 메모리 | `node_memory_MemAvailable_bytes`, `node_memory_MemTotal_bytes` |
| 디스크 공간 | `node_filesystem_avail_bytes`, `node_filesystem_size_bytes` |
| 디스크 IO | `node_disk_read_bytes_total`, `node_disk_io_time_seconds_total` |
| 네트워크 | `node_network_receive_bytes_total`, `node_network_transmit_errs_total` |
| 부하 | `node_load1`, `node_load5`, `node_load15` |
| 파일 수 | `node_filefd_allocated` |

### CPU 사용률 계산 예 (PromQL)

```promql
# 노드별 CPU 사용률(%) — idle을 빼면 사용량
100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

### 위치

- DaemonSet: 모든 노드에 1개씩
- hostNetwork=true + hostPID=true (호스트 OS 측정용)
- ServiceMonitor: `kube-prometheus-stack-prometheus-node-exporter`

---

## 15. cAdvisor

**컨테이너 단위 리소스 사용량을 노출**. kubelet에 **내장**되어 있어 별도 Deployment 불필요. `/metrics/cadvisor` 엔드포인트로 노출.

### 주요 메트릭

| 메트릭 | 의미 |
|---|---|
| `container_cpu_usage_seconds_total{container, pod, namespace}` | 컨테이너 CPU 사용 시간 |
| `container_memory_usage_bytes` | 메모리 사용량 (cache 포함) |
| `container_memory_working_set_bytes` | working set (OOM 판정 기준) |
| `container_network_receive_bytes_total` | 컨테이너 수신 트래픽 |
| `container_fs_usage_bytes` | 컨테이너 파일시스템 사용량 |

### 출처 비교 (꼭 헷갈리는 부분)

| 출처 | 측정 단위 | 예시 메트릭 |
|---|---|---|
| **node_exporter** | 노드 OS 전체 | `node_memory_MemAvailable_bytes` |
| **cAdvisor (kubelet)** | 컨테이너 (cgroup) | `container_memory_usage_bytes` |
| **kube-state-metrics** | K8s 객체 상태 | `kube_pod_status_phase` |
| **app `/metrics`** | 비즈니스 로직 | `http_requests_total`, `cache_hits_total` |

### 자주 쓰는 PromQL

```promql
# Pod별 CPU 사용 (cores)
sum by(pod) (rate(container_cpu_usage_seconds_total{namespace="api"}[5m]))

# Pod별 메모리 (MB)
sum by(pod) (container_memory_working_set_bytes{namespace="api"}) / 1024 / 1024
```

---

## 16. relabel_config

scrape 전후로 라벨을 조작하는 강력한 기능. **cardinality 통제의 핵심 도구**.

### 두 종류

| 종류 | 시점 | 대상 | 용도 |
|---|---|---|---|
| `relabel_configs` | scrape **전** | target 자체 | target keep/drop, 라벨 추가, instance 이름 정리 |
| `metric_relabel_configs` | scrape **후** | 수집된 sample | 특정 metric drop, 라벨 정리, 가변 라벨 제거 |

### 자주 쓰는 action

| action | 의미 |
|---|---|
| `keep` | regex 매칭되는 target/sample만 유지 |
| `drop` | 매칭되는 것 제거 |
| `replace` (기본) | regex 캡쳐를 target_label에 채움 |
| `labelmap` | 라벨 이름 자체를 매핑 (e.g. `__meta_kubernetes_pod_label_*` → 그대로) |
| `labeldrop` / `labelkeep` | 라벨 이름 패턴으로 drop/keep |
| `hashmod` | 시계열 hash로 샤딩 |

### 예시

```yaml
# 1) Pod의 app 라벨을 그대로 메트릭 라벨에 옮김
- source_labels: [__meta_kubernetes_pod_label_app]
  target_label: app

# 2) Go GC 디테일 메트릭은 cardinality만 잡아먹어서 drop
- source_labels: [__name__]
  regex: 'go_gc_.*'
  action: drop

# 3) 'pod' 라벨에 hash가 들어있는 경우 hash 부분 제거
- source_labels: [pod]
  regex: '(.+)-[a-z0-9]{9,10}-[a-z0-9]{5}'
  target_label: pod_template
  action: replace
```

### `__meta_*` 라벨

K8s SD가 자동으로 붙이는 메타 라벨 (scrape 전에만 존재):
- `__meta_kubernetes_namespace`
- `__meta_kubernetes_pod_name`
- `__meta_kubernetes_pod_label_<label>`
- `__address__` (host:port)

`relabel_configs`에서 이걸 가공해 실제 라벨(namespace, pod, app 등)로 옮긴다.

### 케이스 스터디: api `/metrics` cardinality 분석

이론만으로는 어떤 metric을 drop할지 판단하기 어렵다. 실제 엔드포인트를 호출해 측정한 뒤 근거 기반으로 결정한 기록.

#### 측정

```bash
curl -s http://k8s-api-api-426e66a22a-1078713864.us-east-2.elb.amazonaws.com/metrics > /tmp/api-metrics.txt
grep -v '^#' /tmp/api-metrics.txt | grep -v '^$' | wc -l
# → 184 series
```

#### Series 수 기준 Top 7 (전체의 약 62%)

| metric | series | 라벨 조합 |
|---|---|---|
| `http_request_duration_seconds_bucket` | 50 | route 5종 × bucket 10개 |
| `nodejs_gc_duration_seconds_bucket` | 21 | kind 3종(minor/incremental/major) × bucket 7개 |
| `nodejs_heap_space_size_used_bytes` | 13 | space 13종 (read_only / new / old / code / trusted …) |
| `nodejs_heap_space_size_total_bytes` | 13 | 동일 |
| `nodejs_heap_space_size_available_bytes` | 13 | 동일 |
| `db_query_duration_seconds_bucket` | 10 | operation × pool × bucket |
| `nodejs_active_resources` | 6 | type별 (TCPSocketWrap / PipeWrap / Timeout / …) |

route 분포:

```
http_requests_total{route="/ready",   status_code="200"}   ← k8s readiness probe
http_requests_total{route="/health",  status_code="200"}   ← k8s liveness probe
http_requests_total{route="/metrics", status_code="200"}   ← Prometheus 자기 자신 scrape
http_requests_total{route="/",        status_code="404"}   ← root 스캐너 (의미 없는 호출)
http_requests_total{route="/chaos/db/burst", status_code="200"}
```

#### 후보 6개 (효과 큰 순)

| # | 후보 | drop 대상 | 감소 series | 근거 | 적용 |
|---|---|---|---|---|---|
| 1 | `nodejs_heap_space_*` 3종 | 39 | V8 내부 메모리 공간별 분포. dashboard/alert에서 안 봄. `nodejs_heap_size_used_bytes` 1개로 충분 | 보류 |
| 2 | `nodejs_gc_duration_seconds_*` | 21 | GC 분포는 OOM 의심 시에만 확인. 평소 heap 사이즈가 더 직접적 신호 | 보류 |
| 3 | `nodejs_eventloop_lag_(min|max|stddev|p50|p90)_seconds` | 5 | mean/p99/raw seconds 3개만 남기면 충분 | 보류 |
| 4 | `nodejs_active_(handles|requests|resources)(_total)?` | ~10 | TCPSocketWrap/PipeWrap 디테일은 디버깅용. 평상시 안 봄 | **적용** |
| 5 | `http_request_duration_seconds_*` for `/health`,`/ready`,`/metrics` | 30 | 응답시간 알람 `HighLatencyP95`는 비즈니스 경로 대상이어야 의미. probe는 1~3ms 미만이고 사용자가 안 봄. `http_requests_total`은 유지 — APIDown 알람이 의존 | **적용** |
| 6 | `route="/"`, `status_code="404"` | 1 | 의미 없는 root 스캐너 호출. status별 트래픽 통계가 왜곡됨 | **적용** |

#### 적용 결정과 그 이유

- **#4, #5, #6 즉시 적용**: 의도가 명확하고 손실 없음. probe latency / root scanner 노이즈 / debug-only nodejs 메트릭.
- **#1, #2, #3 보류**: cardinality는 크지만, 향후 Node.js 런타임 이슈 디버깅 시 한 번쯤 필요할 수 있음. 메트릭 양이 더 늘어나거나 OOM 임박 시 추가.

#### 적용 결과 (`infra/helm/api/templates/servicemonitor.yaml`)

```yaml
endpoints:
  - port: http
    path: /metrics
    interval: 15s
    scrapeTimeout: 10s
    metricRelabelings:
      # #4 — Node.js 내부 active handles/requests/resources
      - sourceLabels: [__name__]
        regex: 'nodejs_active_(handles|requests|resources)(_total)?'
        action: drop

      # #5 — k8s probe + self-scrape 응답시간 분포 (http_requests_total은 유지)
      - sourceLabels: [__name__, route]
        regex: 'http_request_duration_seconds_(bucket|sum|count);(/health|/ready|/metrics)'
        action: drop

      # #6 — / 경로 404 노이즈 (root 스캐너)
      - sourceLabels: [route, status_code]
        regex: '/;404'
        action: drop
```

#### Prometheus relabel 규칙 메모

- 다중 `sourceLabels`는 `;`로 join되어 regex와 매칭됨.
  예: `[__name__, route]` + `bucket;/health` → 문자열 `http_request_duration_seconds_bucket;/health` 에 match.
- regex는 RE2이며 **fully anchored** (양 끝 `^...$` 자동).
- action: `drop` = 매칭되는 sample 자체 폐기. `replace`(기본)와 헷갈리지 않게.

#### 예상 효과

| 항목 | 적용 전 | 적용 후 (이론치) |
|---|---|---|
| Pod 1개 series 수 | 184 | 약 143 (-22%) |
| 보류된 #1~#3까지 적용 시 | - | 약 84 (-54%) |

Pod replica 수와 churn(재배포)을 곱하면 더 크게 누적되므로 단순 22%보다 실제 절감은 큼.

#### 검증 방법

배포 후 Prometheus UI에서:

```promql
# Pod별 active series 수
prometheus_tsdb_head_series{job="api"}      # 아니 — TSDB head는 전체. 아래로

# 우리 api job의 scrape별 sample 수
sum by(job) (scrape_samples_post_metric_relabeling{job=~".*api.*"})

# drop 대상 metric이 정말 사라졌는지
nodejs_active_handles{namespace="api"}
# → "Empty query result" 면 성공
```

---

## 17. Counter vs Gauge (메트릭 타입)

| 타입 | 특징 | 예시 | 주로 쓰는 PromQL |
|---|---|---|---|
| **Counter** | 단조 증가만, 재시작 시 0 reset | `http_requests_total`, `cache_hits_total` | `rate()`, `increase()` |
| **Gauge** | 자유롭게 증감 | `pg_pool_waiting_clients`, `items_total` | 값 그대로 / `avg_over_time()` |
| **Histogram** | bucket(le=...)+sum+count로 분포 표현 | `http_request_duration_seconds` | `histogram_quantile()` |
| **Summary** | 클라이언트에서 직접 분위수 계산 | (잘 안 씀) | 직접 quantile |

### Counter 주의

- **절대값 자체는 의미 없음**. 재시작하면 0으로 reset되니까 `http_requests_total = 12345`라는 사실 자체는 정보가 없다.
- 항상 변화량으로 본다.
  ```promql
  rate(http_requests_total[5m])              # 5분 평균 초당 증가
  increase(http_requests_total[1h])          # 1시간 동안 증가량
  ```
- Prometheus는 reset 감지 알고리즘이 있어서 0으로 떨어진 시점을 보정.

### Gauge 주의

- 직접 값에 의미 있음.
- 평균/min/max를 보려면 `*_over_time()` 함수.
  ```promql
  avg_over_time(pg_pool_waiting_clients[5m])
  max_over_time(pg_pool_waiting_clients[1h])
  ```

### Histogram 주의

- bucket은 **누적**(`le="0.1"`은 "0.1초 이하 모두").
- 분위수는 bucket의 rate를 histogram_quantile에 넘김.
  ```promql
  histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
  ```
- bucket 수가 많아질수록 시계열 수도 같이 증가 → 적당히.

### 명명 컨벤션

- counter는 항상 `_total` suffix
- histogram bucket은 `_bucket`, sum은 `_sum`, count는 `_count`
- 단위는 base SI (`_seconds`, `_bytes`) — `_ms` 같은 거 쓰면 PromQL이 산수할 때 헷갈림

---

## 18. OOM 났을 때 대처

증상: Prometheus Pod이 `OOMKilled` 상태로 재시작 반복. WAL replay 동안 더 메모리 폭증 → 시작도 못 함 → 무한 OOM loop.

### 1단계: 원인 추적

```promql
# Active series 수 (메모리 주범 후보 #1)
prometheus_tsdb_head_series

# 어떤 metric이 series 수 많은지
topk(20, count by(__name__)({__name__=~".+"}))

# 어떤 라벨이 unique 값 많은지
topk(20, count by(label_name)(metric_name))

# 초당 sample 수
rate(prometheus_tsdb_head_samples_appended_total[5m])

# 메모리 사용
process_resident_memory_bytes

# scrape duration (특정 target이 비정상적으로 느린지)
topk(10, scrape_duration_seconds)

# Head chunk (메모리 chunk)
prometheus_tsdb_head_chunks
```

### 2단계: 단기 조치 (Pod 살리기)

- **메모리 limit 증가**: `Prometheus` CR의 `spec.resources.limits.memory` 상향.
  > 주의: StatefulSet을 직접 patch하면 Operator가 다시 덮어쓴다. 반드시 CR 변경.
- **WAL replay 중이면 일단 대기** (replay 끝나야 OOM 사이클 끊어짐). `--storage.tsdb.wal-segment-size` 줄이거나 손상된 WAL segment 제거(최후의 수단).
- **무거운 query 차단**: `--query.max-samples`, `--query.timeout` 축소.

### 3단계: 중기 조치 (재발 방지)

- **고cardinality metric 식별 → drop**
  ```yaml
  metric_relabel_configs:
    - source_labels: [__name__]
      regex: 'noisy_metric_name'
      action: drop
  ```
- **scrape interval 늘림** (15s → 30s)
- **불필요한 target 제거** (예: 안 쓰는 system metric)
- **PrometheusRule로 OOM 임박 alert** (우리 alert `PrometheusHighMemory > 80%` 이미 등록됨)

### 4단계: 장기 조치 (구조 개선)

- **remote_write로 외부 storage 분리** (Thanos/Mimir/VictoriaMetrics) → 로컬은 query 전용
- **샤딩**: 메트릭 hash 기준 prometheus 여러 개 (`hashmod` action)
- **retention 단축**: `spec.retention: 7d` 또는 외부 storage에 맡기고 로컬 1d
- **Prometheus agent 모드**로 수집만 — 로컬 저장 0

### 우리 케이스 (devopsim)

- Prometheus는 t3a.medium 노드에 affinity로 고정 (`karpenter.k8s.aws/instance-size: medium`)
- PrometheusRule에 `PrometheusHighMemory > 80%` alert 등록 → 임계 도달 시 Slack 알림
- 현재 active series 수가 적어 OOM 위험 낮음, 다만 cAdvisor + node-exporter + kube-state-metrics 풀스택이라 metric churn 발생 시 빠르게 한계 도달 가능
- 다음 단계: Thanos sidecar로 S3 업로드 + retention 7일로 축소
