# Loki + Alloy 도입 기록

> Prometheus가 "메트릭의 시계열 DB"라면, Loki는 "로그의 시계열 DB". 둘 다 Grafana Labs 작품이고, 의도된 짝.
> Alloy는 Grafana가 만든 통합 telemetry 수집 agent (= Promtail / Otel collector / Grafana Agent의 후계자).

---

## 0. "alloy DaemonSet + loki StatefulSet 두 개로 끝 아닌가?"

**짧게 답하면**: 토이로 굴리면 그게 맞고, 실서비스 가까이 가려면 한참 부족하다.

| 항목 | 두 개만 띄우면 | 실무에서 필요한 것 |
|---|---|---|
| 스토리지 | **로컬 PVC**에 chunks/index 저장 | S3 + TSDB shipper (chunks=object, index=cache+S3) |
| 모드 | SingleBinary (single Pod) | SSD(Simple Scalable, 3 components) — read/write 분리 |
| 인증 | `auth_enabled: false` (single-tenant) | 그대로여도 OK. 다만 명시적 결정이어야 함 |
| Retention | **무한 보관** (compactor 안 켜면 자동 삭제 X) | compactor + retention policy |
| Limits | helm default는 매우 관대 | `ingestion_rate_mb`, `max_streams_per_user`, `max_query_length` 조정 |
| 데이터 무결성 | WAL 켜져 있지만 단일 ingester | 적어도 replication_factor 3 (SSD/Distributed에서) |
| 수집 agent | "그냥 DaemonSet" | 수집 라벨 설계 → 안 그러면 stream cardinality 폭발 |
| Grafana 연동 | Helm은 안 만들어줌 | `Loki` datasource 추가 (수동/sidecar) |

→ 이 문서는 그 "한참 부족"을 메우는 작업 기록.

---

## 1. Loki가 뭐고 어떻게 동작하나

**Loki**는 **"로그 라인 본문은 인덱싱하지 않고 라벨만 인덱싱하는"** 로그 저장소. 이게 Loki를 다른 로그 시스템(Elasticsearch, OpenSearch, Splunk)과 결정적으로 가르는 한 줄이다.

### Elasticsearch와의 결정적 차이

```
Elasticsearch:  로그 한 줄 → 전체 텍스트 inverted index → 디스크↑, 메모리↑, $$↑
Loki:           로그 한 줄 → label만 index, 본문은 압축 chunk로 묶어서 object storage에 던짐
```

검색 시:
- ES: 단어 → posting list → matching docs 즉시 (= 빠르지만 비쌈)
- Loki: label로 stream 좁히기 → 해당 chunks fetch → **본문은 grep**

→ 비용은 1/10 ~ 1/100, 대신 cold query는 느릴 수 있음. devopsim 규모에선 압도적 우위.

### 동작 흐름

```
[앱 Pod stdout/stderr]                  [K8s node /var/log/pods/...]
                                              ↑
                                              │ (1) tail
                                              │
                                          [Alloy DaemonSet] (노드마다 1개)
                                              │
                                              │ (2) K8s SD로 Pod 라벨 attach
                                              │     pipeline stage로 변환/drop
                                              │
                                              │ (3) HTTP POST /loki/api/v1/push
                                              ↓
[Loki write path]
  distributor → ingester → (메모리 chunk) ─ flush ─> [object storage(S3) + index]
                              │
                              └─ WAL (PVC) — 재시작 복구

[Loki read path]
  query-frontend → querier → ingester(최근 데이터) + storage(과거 데이터)
                                ↑
                                │ (4) LogQL
                                │
                              [Grafana]
```

### 라벨 모델 — Prometheus와 거의 동일하지만 더 빡빡

```
{namespace="api", pod="api-7f8c9-x4k7m", container="api"}  ← 하나의 stream
{namespace="api", pod="api-7f8c9-y9q2p", container="api"}  ← 다른 stream
```

같은 라벨 조합 = 같은 stream = 같은 chunk에 append. **stream 개수 = 인덱스 크기 = 메모리**.

Prometheus의 cardinality 폭발 규칙이 그대로 적용된다. 그런데 Loki는 더 빡빡하다 — 보통 stream 당 데이터가 더 적어서 같은 메모리로 더 적은 stream을 다뤄야 한다.

**절대 라벨에 넣지 말 것**: request_id, trace_id, user_id, span_id, hash. 본문에 두고 LogQL의 `|~ "..."` 로 filter 한다.

---

## 2. 설치 (계획)

**Helm chart**:
- `grafana-community/loki` v16.0.0 (App Loki 3.7.2) — **2026-03-16부터 OSS Loki는 community 차트로 이관**. `grafana/loki` 7.x는 Grafana Enterprise Logs(GEL) 전용. ([#20705](https://github.com/grafana/loki/issues/20705))
- `grafana/alloy` v1.8.1 (App v1.16.1) — Alloy는 여전히 `grafana/helm-charts`.

**HelmRepository 두 개 필요**: `grafana-community` (Loki) + `grafana` (Alloy).
**Namespace**: `monitoring` (Prometheus와 공유)

### 모드 선택 — chart의 세 가지 deploymentMode

| 모드 (16.x 이후) | 구 명칭 | 컴포넌트 | 트래픽 | 우리 선택 |
|---|---|---|---|---|
| **Monolithic** | SingleBinary | Loki Pod 1 (StatefulSet) | 학습 / < 100GB/day | (1단계) ✅ |
| **SimpleScalable (SSD)** | 동일 | write StatefulSet + read Deployment + backend StatefulSet | 100GB ~ 1TB/day | (2단계) |
| **Distributed** | 동일 | distributor/ingester/querier/compactor/index-gateway/... | TB+/day, 멀티팀 | (3단계, 아마 안 감) |

> 16.x에서 `SingleBinary` → `Monolithic`으로 명칭 변경. `SingleBinary`는 alias로 호환 유지.

devopsim 트래픽 기준 SingleBinary로 시작. 단, **storage는 처음부터 S3**. (filesystem으로 띄우면 Pod 죽을 때 데이터 전부 날아감, 또 SSD 전환 시 마이그레이션 필요)

### 설치할 컴포넌트

| 컴포넌트 | 종류 | 역할 | 메모리 (대략) |
|---|---|---|---|
| **Loki** | StatefulSet (single binary) | write+read+compactor 모두 한 binary | 512Mi ~ 1Gi |
| **Alloy** | DaemonSet | 노드별 로그 수집 → Loki push | 100~300Mi/노드 |
| **gateway (선택)** | Deployment (nginx) | 인증/캐시 프록시. SSD/Distributed에선 필수, SingleBinary에선 optional | 50Mi |

#### 안 띄우는 것 (devopsim 1단계 기준)
- **Promtail**: Alloy로 대체. Promtail은 deprecated 수순.
- **fluentd / fluent-bit**: 동일 역할. Grafana 스택에선 Alloy.
- **Loki gateway**: SingleBinary에선 굳이 안 둔다. Grafana → Loki Service 직접.

### 외부 노출
- **Loki 자체는 외부 노출 X** — Grafana datasource로만 접근.
- **Grafana만 ALB** (이미 monitoring group ALB 공유 중).

---

## 3. Helm chart values — 기본값과 실무 차이

이 섹션이 핵심. `grafana/loki` chart는 `helm install loki grafana/loki` 만으로는 절대 production에 못 쓴다. 이유를 항목별로.

### 3-1. `loki.storage` — filesystem vs S3

#### 기본값
```yaml
loki:
  storage:
    type: filesystem
    bucketNames:
      chunks: chunks
      ruler: ruler
      admin: admin
```

`filesystem` = chunks/index를 **PVC 안에** 저장 (`/var/loki/chunks`, `/var/loki/index`).
PVC만 잘 잡으면 Pod 재시작해도 데이터는 남는다. 즉 "Pod 죽으면 끝"은 **persistence.enabled: false일 때만** 사실.

#### 그럼에도 S3를 권하는 이유

| 항목 | filesystem (+ PVC) | s3 |
|---|---|---|
| 데이터 상한 | PVC 용량 (gp3 max 16TB) | 사실상 무한 |
| 모드 전환 | SSD/Distributed로 못 감 | 모든 모드 호환 |
| Read 확장 | PVC RWO라 querier 1개 | querier N개 동시 read |
| 비용 (저장만) | gp3 ≈ $0.08/GB·월 | S3 Standard ≈ $0.023/GB·월 |
| 가용성 | AZ 단위 | region 단위 |
| 백업/복제 | EBS snapshot 별도 구성 | S3 versioning/replication 기본 |

→ 학습/PoC면 filesystem이어도 동작은 한다. devopsim은 "프로덕션처럼" 굴리려는 게 목적이라 처음부터 S3.

#### 우리 설정
```yaml
loki:
  storage:
    type: s3
    s3:
      region: us-east-2
      endpoint: s3.us-east-2.amazonaws.com
    bucketNames:
      chunks: devopsim-loki-chunks
      ruler:  devopsim-loki-ruler
      admin:  devopsim-loki-admin
```

자격증명은 IRSA(ServiceAccount IAM Role) 또는 ExternalSecret으로 주입. devopsim은 이미 ESO + AWS Secrets Manager 패턴 → ExternalSecret으로 통일.

> Terraform에서 S3 버킷 + IAM role 미리 만들고 IRSA로 ServiceAccount annotate.

### 3-2. `loki.schemaConfig` — TSDB v13만 쓴다

#### 기본값 (chart 버전에 따라 다름, 보통 무지정 → 강제 입력 요구)
```yaml
schemaConfig: {}
```

Loki는 schema 없이 못 뜬다. 그리고 **deprecated 포맷**(boltdb / boltdb-shipper)을 잘못 쓰면 1년 뒤 마이그레이션 지옥.

#### 우리 설정
```yaml
loki:
  schemaConfig:
    configs:
      - from: 2026-01-01           # 시작 날짜 (과거여야 함)
        store: tsdb                # 최신
        object_store: s3
        schema: v13                # 2024+ Loki는 v13 강제 권장
        index:
          prefix: index_
          period: 24h              # 인덱스 파일 분할 단위
```

**이유**: tsdb는 boltdb-shipper의 후계자. 인덱스 쓰기/읽기 속도, 압축률 둘 다 우위. v13은 chunk format v3 + structured metadata 지원.

### 3-3. `auth_enabled` — single-tenant로 명시

#### 기본값
```yaml
loki:
  auth_enabled: true              # 멀티테넌시 강제, 모든 요청에 X-Scope-OrgID 헤더 필요
```

`auth_enabled: true`인데 Alloy/Grafana 설정에 헤더 안 박으면 → 401 무한 루프. helm default가 이래서 처음 띄우는 사람이 가장 많이 막힘.

#### 우리 설정
```yaml
loki:
  auth_enabled: false
```

devopsim은 single-tenant. 운영 멀티팀 분리 필요 시 그때 켠다.

### 3-4. `loki.limits_config` — default가 너무 관대

#### 기본값 (대략)
```yaml
limits_config:
  ingestion_rate_mb: 4              # tenant당 4MB/s
  ingestion_burst_size_mb: 6
  max_streams_per_user: 0           # 무제한 ⚠
  max_global_streams_per_user: 5000
  max_query_length: 721h            # 30일+
  max_query_parallelism: 32
  retention_period: 0s              # 무제한 ⚠
```

`max_streams_per_user: 0`이 가장 위험. 라벨 잘못 박은 앱 하나가 stream 수십만 개 만들면 Loki ingester OOM.

#### 우리 설정
```yaml
loki:
  limits_config:
    ingestion_rate_mb: 8
    ingestion_burst_size_mb: 16
    max_streams_per_user: 5000      # 명시적 상한
    max_global_streams_per_user: 5000
    max_query_length: 168h          # 7일 (retention과 일치)
    max_query_parallelism: 16
    retention_period: 168h          # 7일
    reject_old_samples: true
    reject_old_samples_max_age: 12h # 12시간 이전 로그는 거부 (시계 안 맞는 agent 차단)
```

### 3-5. `loki.compactor` — 안 켜면 retention 0과 동일

#### 기본값
```yaml
compactor:
  retention_enabled: false          # ⚠ default false
```

compactor가 retention 처리를 담당. **이걸 안 켜면 위에서 `retention_period: 168h` 적어도 의미 없음.** 데이터는 영원히 쌓인다.

#### 우리 설정
```yaml
loki:
  compactor:
    retention_enabled: true
    retention_delete_delay: 2h
    retention_delete_worker_count: 150
    compaction_interval: 10m
    working_directory: /var/loki/compactor
    delete_request_store: s3
```

### 3-6. `loki.commonConfig.replication_factor`

#### 기본값 (SingleBinary)
```yaml
commonConfig:
  replication_factor: 1
```

SingleBinary에선 1이 맞다 (인스턴스 하나). 단, **SSD로 갈 때 3으로 바꾸는 걸 잊지 말 것**.

### 3-7. `loki.persistence` (StatefulSet PVC)

#### 기본값
```yaml
persistence:
  enabled: false                    # ⚠
```

`enabled: false` → emptyDir 사용. Pod 재시작하면 다 날아감.

#### PVC의 역할은 storage 선택과 무관

S3 모드여도 PVC는 **반드시** 켜야 한다. PVC에 들어가는 건:

```
/var/loki/
├── wal/                    ← 항상. ingester 메모리 chunk의 디스크 미러 (재시작 복구용)
├── chunks/                 ← flush 전 임시 chunk (메모리 부족 시 spill)
├── tsdb-shipper-cache/     ← S3에서 받아온 인덱스의 로컬 캐시
└── compactor/              ← compaction 작업 디렉토리
```

즉 "**영구 데이터는 S3, PVC는 메모리/캐시의 디스크 backing**".
WAL이 없으면 ingester가 죽었을 때 flush 안 된 최근 데이터(보통 수분~30분치)가 손실된다.

#### 우리 설정
```yaml
loki:
  persistence:
    enabled: true
    size: 10Gi
    storageClass: gp3
```

### 3-8. resource 요청

#### 기본값
chart default: requests 없음, limits 없음. **bin packing에서 우선순위 0** → 다른 Pod에 밀려서 evict될 수 있음.

#### 우리 설정 (SingleBinary, 트래픽 적음 기준)
```yaml
loki:
  resources:
    requests:
      cpu: 200m
      memory: 512Mi
    limits:
      memory: 1Gi                   # CPU limit은 안 두는 게 일반적 (throttling 회피)
```

메모리는 **active stream 수에 거의 선형**. 5,000 stream까지 1Gi면 충분.

---

## 4. Alloy values — 마찬가지로 default가 부족하다

### 4-1. 배포 모드

#### 기본값
```yaml
controller:
  type: daemonset
```

DaemonSet은 맞다. 단, **노드마다 한 개씩 뜨면서 hostPath로 `/var/log/pods`를 읽어야** 한다.

```yaml
alloy:
  mounts:
    varlog: true                    # /var/log/pods
    dockercontainers: true          # /var/lib/docker/containers (containerd면 무의미하지만 default true)
```

EKS는 containerd라서 `dockercontainers`는 false로 두는 게 청결.

### 4-2. Alloy config — 핵심

Alloy는 **component-based** 설정. River 언어(HCL 비슷). Promtail의 YAML scrape_configs와는 모양이 완전히 다름.

```hcl
// (1) K8s SD: Pod 목록 가져오기
discovery.kubernetes "pods" {
  role = "pod"
}

// (2) Pod 라벨에서 우리 메트릭 라벨로 매핑
discovery.relabel "pods" {
  targets = discovery.kubernetes.pods.targets
  rule {
    source_labels = ["__meta_kubernetes_namespace"]
    target_label  = "namespace"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_name"]
    target_label  = "pod"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_label_app_kubernetes_io_name"]
    target_label  = "app"
  }
  // 우리가 모니터링할 namespace만 keep
  rule {
    source_labels = ["namespace"]
    regex         = "api|detector|monitoring"
    action        = "keep"
  }
}

// (3) Pod 로그 tail
loki.source.kubernetes "pods" {
  targets    = discovery.relabel.pods.output
  forward_to = [loki.process.app.receiver]
}

// (4) 가공 (JSON parse, level 추출 등)
loki.process "app" {
  forward_to = [loki.write.default.receiver]

  // pino JSON 로그면 level 라벨화
  stage.json {
    expressions = { level = "level", msg = "msg" }
  }
  stage.labels {
    values = { level = "" }
  }
  // 너무 큰 line drop
  stage.drop {
    longer_than = "8192b"
    drop_counter_reason = "line_too_long"
  }
}

// (5) Loki로 전송
loki.write "default" {
  endpoint {
    url = "http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push"
  }
}
```

#### 가장 중요한 두 가지 결정

1. **어떤 라벨을 attach 할지** — Prometheus의 metric label 결정과 동일한 무게. `pod_template_hash`, `controller_uid` 같은 건 절대 라벨로 들어가면 안 됨 (= stream 폭발).
2. **어떤 라벨을 본문 → label로 추출할지** — 보통 `level`(error/warn/info), 가끔 `route` 정도. 그 이상은 본문 grep.

### 4-3. Position file (tail offset)

Alloy는 각 노드에서 어느 파일의 어디까지 읽었는지 기록해야 한다.

```hcl
loki.source.kubernetes "pods" {
  // ...
  // 내부적으로 PositionFile은 hostPath에 둠
}
```

Helm chart는 기본적으로 `/var/lib/alloy` hostPath에 position을 쓴다. **노드가 갈리면 position 잃음** → 노드 교체 시 로그 중복 가능 (cosmetic, 데이터 손실 X).

### 4-4. resource 요청

```yaml
alloy:
  resources:
    requests:
      cpu: 50m
      memory: 100Mi
    limits:
      memory: 300Mi
```

로그 폭주 시 alloy가 죽으면 노드 전체 로그 손실. limits를 너무 빡빡하게 두지 말 것.

---

## 5. 그래서 Loki 작업으로 해야 될 것들 — 순서

1. **Terraform**: S3 bucket(devopsim-loki-chunks/ruler/admin) + IRSA용 IAM role/policy 작성 → apply.
2. **ESO**: AWS Secrets Manager에 S3 credential (또는 IRSA 직접 사용 시 secret 불필요). IRSA 권장.
3. **Helm values 작성**: `infra/helm/`에 chart 가져오는 대신 HelmRelease만 작성 (Flux 패턴 그대로). values는 위 3절 합본.
4. **Flux HelmRelease 등록**:
   - `infra/flux/clusters/prod/infrastructure/controllers/loki.yaml`
   - `infra/flux/clusters/prod/infrastructure/controllers/alloy.yaml`
   - controllers `kustomization.yaml`에 추가
5. **Grafana datasource 추가**: kube-prometheus-stack values에 `additionalDataSources`로 Loki URL 등록 (자동 provisioning).
6. **Alloy config 작성**: 위 4-2 River config. 처음엔 namespace `api`만 keep 시작.
7. **검증** (다음 섹션):
   - `kubectl logs -n monitoring loki-0` 으로 ingest 로그
   - Grafana Explore → Loki → `{namespace="api"}` 쿼리
   - api Pod에 일부러 ERROR 로그 찍기 → Grafana에서 보이는지
8. **PrometheusRule 확장 (선택)**: Loki에서도 alert 가능 (LokiRule via Loki ruler). HighErrorRate가 메트릭 기반이지만, "특정 ERROR 메시지 N회/분"같은 로그 기반 alert 추가 검토.

---

## 6. 동작 검증 시나리오

```bash
# 1. Loki Pod ready
kubectl get pods -n monitoring -l app.kubernetes.io/name=loki

# 2. Alloy DaemonSet 노드 수만큼 떴는지
kubectl get ds -n monitoring alloy
kubectl get pods -n monitoring -l app.kubernetes.io/name=alloy -o wide

# 3. Loki에 데이터 도착 확인 (Pod 내부 metrics)
kubectl port-forward -n monitoring svc/loki 3100:3100
curl -s http://localhost:3100/metrics | grep loki_distributor_lines_received_total

# 4. S3에 chunk 도착 (10분 ~ 첫 flush)
aws s3 ls s3://devopsim-loki-chunks/ --recursive | head
```

### LogQL 예시 (Grafana Explore)

```logql
# api namespace의 모든 로그
{namespace="api"}

# api 컨테이너만, level=error
{namespace="api", container="api", level="error"}

# 본문에 "ECONNREFUSED" 포함
{namespace="api"} |~ "ECONNREFUSED"

# JSON 파싱 후 status_code 추출
{namespace="api"} | json | status_code >= 500

# 시간당 error 개수
sum(count_over_time({namespace="api", level="error"}[1h]))
```

---

## 7. 다음 단계

- 처음엔 SingleBinary + S3 → 트래픽 늘면 SSD로 전환
- Loki ruler 활성화하고 PrometheusRule처럼 LokiRule 추가
- Grafana에 "api 에러 로그" 대시보드 (LogQL panel)
- structured metadata (v13의 핵심 신기능) 활용 — trace_id를 라벨이 아닌 metadata로 attach

---

## 8. Loki vs Prometheus 비교 (인덱스 모델)

| 항목 | Prometheus | Loki |
|---|---|---|
| 저장 대상 | 시계열 sample (float64) | 로그 라인 (text) |
| 인덱스 | label → series 전체 | label → stream 위치만 |
| 본문 검색 | (해당 사항 없음) | object storage에서 chunks fetch 후 grep |
| 쿼리 언어 | PromQL | LogQL (PromQL syntax 흉내) |
| 데이터 압축 | gorilla XOR | gzip / snappy chunk |
| Hot path | TSDB head (메모리) | ingester chunks (메모리) |
| Cold path | 디스크 block | object storage (S3) |
| Cardinality 한계 | active series | active streams |

**같은 함정**: 가변 값(id, hash, timestamp)을 라벨에 넣으면 둘 다 폭발.
**다른 함정 (Loki만)**:
- 1초 미만 단위로 라벨이 바뀌면 chunk를 못 묶음 → 작은 chunk가 폭발적으로 늘어남 (= "small chunks problem")
- 라벨이 너무 적어도 한 stream이 너무 큼 → flush 단위 지연 + 쿼리 시 한 stream을 통째로 읽음

→ stream 당 100KB~5MB가 적정.

---

## 9. 데이터가 저장되는 방법 (Loki 디스크/S3 구조)

```
S3:
  devopsim-loki-chunks/
    fake/                        # 단일 tenant라 tenant id "fake" (auth_enabled=false 기본)
      <chunk hash>/<chunk>       # 압축된 로그 라인 묶음
  devopsim-loki-admin/
    index/
      index_19xxx/               # 24h 단위 TSDB 인덱스
        <ingester>.tsdb
  devopsim-loki-ruler/           # ruler 룰 + state

Loki Pod (PVC):
  /var/loki/
    wal/                         # WAL — 메모리 chunk를 디스크에 미러
    chunks/                      # flush 전 메모리 chunk
    boltdb-shipper-cache/        # 사용 안 함 (TSDB로 마이그)
    tsdb-shipper-cache/          # 인덱스 로컬 캐시
    compactor/
```

### Write 흐름

```
Alloy push (1 batch = 수십~수백 라인)
  ↓
distributor: validation, label 정합성 체크, ring으로 ingester 라우팅
  ↓
ingester: 메모리에 stream별 chunk 누적
  ├─ WAL에 sync (디스크)
  ↓
chunk 차거나 idle timeout (default 30m) → flush
  ├─ S3에 chunk PUT
  └─ index에 (chunk hash, time range, labels) 기록
```

### Read 흐름

```
LogQL: {namespace="api"} |~ "ERROR"
  ↓
query-frontend: split by time, sub-query 생성
  ↓
querier:
  ├─ 최근 데이터 → ingester에 RPC (memory)
  └─ 과거 데이터 → 인덱스로 chunk hash 찾기 → S3 GET → 압축 해제 → grep
  ↓
결과 합쳐서 반환
```

---

## 10. compactor

Loki의 compactor는 Prometheus compaction과 비슷한 일을 하지만 **retention 처리까지 담당**한다.

- 작은 인덱스 파일을 큰 인덱스로 병합 (S3 PUT/LIST 비용 절감)
- retention 만료 chunk 삭제 (`retention_enabled: true`일 때만)
- delete request 처리 (GDPR 등)

→ **SingleBinary에선 자동 활성화되지만 `retention_enabled: true`는 명시해야** 함.

---

## 11. 단일 binary의 한계 극복 (Loki 버전)

| 방법 | 핵심 | 우리 시점 |
|---|---|---|
| **SingleBinary** | 모든 컴포넌트 1 Pod | 현재 |
| **SimpleScalable (SSD)** | write + read + backend 3 StatefulSet | 100GB/day 넘으면 전환 |
| **Distributed** | distributor/ingester/querier/compactor/index-gateway 분리 | 멀티팀 / TB+ |
| **External cache** | Redis/Memcached로 chunk/index 캐시 | 쿼리 빈도 ↑ 시 |
| **Multi-tenant** | `auth_enabled: true` + X-Scope-OrgID | 조직 분리 시 |

→ SSD 전환은 schema/storage 그대로 두고 chart values만 변경하면 됨. 데이터 마이그레이션 없음.

---

## 12. Stream cardinality (= Loki의 metric churn)

`prometheus_tsdb_head_series` 와 동일한 의미의 Loki 지표:

```logql
# 현재 active stream 수
sum(loki_ingester_memory_streams)

# 시간당 새로 만들어진 stream
sum(rate(loki_ingester_streams_created_total[1h]))

# tenant별 chunk flush 속도
sum(rate(loki_ingester_chunks_flushed_total[5m]))
```

### 폭발 패턴

```hcl
// 나쁜 alloy config
discovery.relabel "bad" {
  rule {
    source_labels = ["__meta_kubernetes_pod_name"]
    target_label  = "pod"           // OK
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_uid"]
    target_label  = "uid"           // ⚠ Pod 재시작마다 stream 새로 생김
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_label_pod_template_hash"]
    target_label  = "rs_hash"       // ⚠ 배포마다 새 stream
  }
}
```

배포 5번 × pod 3개 = 같은 워크로드인데 stream 15개. 일주일이면 100개 쉽게 넘는다.

### 좋은 라벨 셋 (시작점)

```
namespace, pod, container, app, level
```

이 정도. nodename, instance, image_tag 등은 본문/metadata에 두기.

---

## 13. pipeline stage — Alloy의 라벨 통제 도구

Prometheus의 `metric_relabel_configs`에 해당. Alloy `loki.process` 안에서 사용:

| stage | 의미 |
|---|---|
| `stage.json` | JSON 로그 파싱해서 필드 추출 |
| `stage.regex` | 정규식으로 필드 추출 (non-JSON 로그) |
| `stage.labels` | 추출한 필드를 stream 라벨로 승격 (cardinality 주의) |
| `stage.structured_metadata` | (Loki v13) 라벨 아닌 메타데이터로 attach. 쿼리 가능 but cardinality 비용 X |
| `stage.drop` | 조건에 맞는 라인 drop |
| `stage.timestamp` | 본문에서 시간 추출 (수집 시간 ≠ 발생 시간일 때) |
| `stage.output` | 라인 본문 자체 replace |
| `stage.match` | selector 기반 분기 |

**핵심 원칙 (Loki 1.x 이전 vs 2.x+):**
- 예전엔 grep 효율을 위해 라벨을 더 박는 게 유리했음.
- 이제 v13 + tsdb는 본문 grep이 빨라서 **"의심스러우면 본문에 두기"**가 정답.

---

## 14. LogQL 기초

LogQL = log selector + filter + aggregation. PromQL을 알면 절반은 안다.

```
{stream_selector}                              ← Prometheus의 selector와 동일
{stream_selector} |= "exact substring"         ← 본문 부분 일치
{stream_selector} |~ "regex"                   ← 본문 regex
{stream_selector} != "..."                     ← 부정
{stream_selector} | json                       ← JSON 파싱
{stream_selector} | logfmt                     ← key=val 파싱
{stream_selector} | json | status_code >= 500  ← 파싱 후 filter

# 집계
count_over_time({ns="api"} |= "ERROR" [5m])
rate({ns="api"} |= "ERROR" [5m])
sum by (level) (rate({ns="api"} | json [5m]))
```

`unwrap`을 쓰면 로그 값으로 metric도 만들 수 있음 (예: 요청 latency를 로그에서 뽑아 histogram). 그러나 보통 그건 메트릭으로 하는 게 낫다.

---

## 15. 운영 함정 모음 (production gotchas)

1. **`auth_enabled` 충돌**: helm default가 모드별로 다르다 (SingleBinary는 false, SSD는 true). 모드 바꾸면 클라이언트도 헤더 추가 필요.
2. **`retention_period` 적었는데 데이터 안 지워짐**: `compactor.retention_enabled: true` 빼먹음.
3. **schema 변경 못 함**: 한 번 적은 `from:` 날짜는 못 바꾼다. 새 schema 추가는 미래 날짜로 append만 가능.
4. **chunk가 S3에 안 올라감**: `commonConfig.path_prefix`와 `compactor.working_directory`가 PVC가 아니라 emptyDir이면 재시작 시 미flush chunk 손실.
5. **alloy가 모든 노드에 안 뜸**: taints 매칭 안 됨. DaemonSet tolerations 명시 필요 (특히 control-plane 노드 제외, GPU 노드 제외 등).
6. **로그 미래 timestamp**: 시계 안 맞는 노드에서 보낸 로그는 ingester가 거부. `reject_old_samples: true`만으로는 부족, `accept_old_samples: false`도 고려.
7. **stream이 작게 쪼개짐**: alloy의 pipeline에서 매 라인마다 다른 라벨 박으면 chunk 못 묶음. `level` 같은 enum 라벨만.
8. **Grafana datasource URL**: SSD에선 `loki-gateway`, SingleBinary에선 `loki` Service. 모드 전환 시 datasource 업데이트 필요.
9. **PVC size**: WAL은 ingester memory_chunks의 1.5~2배 잡을 것. 작으면 flush가 못 따라가서 backpressure.
10. **boltdb-shipper 잔재**: 옛날 가이드/예제에 자주 나오니 주의. **tsdb만 쓴다**.

---

## 16. devopsim 단계별 계획

- **1단계 (지금 작업)**: SingleBinary + S3 + Alloy. Grafana Explore에서 로그 조회 가능.
- **2단계**: Alloy pipeline 정교화 (api JSON 로그의 level/route 추출, chaos 호출은 drop).
- **3단계**: Loki ruler 활성화 → log 기반 alert (예: ECONNREFUSED 5분간 10회).
- **4단계**: traffic이 커지면 SSD 모드로 전환.
- **5단계 (목표)**: detector agent가 alert 받았을 때 Loki에 LogQL 쿼리해서 "방금 5분간 어떤 ERROR가 났는지" 자율 조사.

---

## 17. 참고

- Loki Helm chart (OSS, 2026-03 이후): `grafana-community/loki` (https://grafana-community.github.io/helm-charts)
- Loki Helm chart (Enterprise만): `grafana/loki` 7.x
- Alloy Helm chart: `grafana/alloy` (https://grafana.github.io/helm-charts)
- Chart 이관 배경: https://github.com/grafana/loki/issues/20705
- TSDB schema v13: https://grafana.com/docs/loki/latest/operations/storage/schema/
- LogQL: https://grafana.com/docs/loki/latest/query/
