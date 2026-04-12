# minikube

## 환경

- Apple M-series (arm64)
- minikube v1.31.2 → v1.38.1 업그레이드
- kubectl v1.30.2 → v1.35.3 업그레이드

---

## 문제 1: minikube start 실패 — kubeconfig 파싱 에러

### 증상

```
😄  Darwin 15.0 (arm64) 의 minikube v1.31.2
✨  기존 프로필에 기반하여 docker 드라이버를 사용하는 중
👍  minikube 클러스터의 minikube 컨트롤 플레인 노드를 시작하는 중
🔥  Creating docker container (CPUs=2, Memory=4000MB) ...
🐳  쿠버네티스 v1.27.4 을 Docker 24.0.4 런타임으로 설치하는 중

❌  Exiting due to GUEST_START: failed to start node: Failed kubeconfig update:
could not read config: Error decoding config from data: kind: ExecCredential
apiVersion: client.authentication.k8s.io/v1alpha1
...
: no kind "ExecCredential" is registered for version
"client.authentication.k8s.io/v1alpha1" in scheme
"pkg/runtime/scheme.go:100"
```

### 원인

예전에 사용했던 kubeconfig(`~/.kube/config`)가 남아있었다.
`v1alpha1` ExecCredential API는 현재 kubectl에서 지원이 끊겨 파싱 자체가 실패.

### 해결

```bash
# 기존 kubeconfig 백업
cp ~/.kube/config ~/.kube/config.bak

# 초기화
cat > ~/.kube/config << 'EOF'
apiVersion: v1
kind: Config
clusters: []
contexts: []
current-context: ""
preferences: {}
users: []
EOF
```

---

## 문제 2: minikube start 실패 — K8s 버전 지원 종료

### 증상

```
! Specified Kubernetes version 1.27.4 is less than the oldest supported version: v1.28.0.
  Use `minikube config defaults kubernetes-version` for details.
! You can force an unsupported Kubernetes version via the --force flag

X Exiting due to K8S_OLD_UNSUPPORTED: Kubernetes 1.27.4 is not supported
  by this release of minikube
```

### 원인

예전 minikube 프로필에 K8s 1.27.4가 저장되어 있었다.
minikube v1.38.1은 v1.28.0 미만을 지원하지 않는다.

### 해결

기존 프로필 삭제 후 재시작. 최신 K8s 버전(v1.35.1)으로 자동 기동.

```bash
minikube delete
minikube start
```

---

## 문제 3: Secret이 kustomize apply로 덮어써짐

### 증상

`kubectl create secret`으로 실제 값을 넣었는데,
`kubectl apply -k`를 실행하면 `secret.yaml`(빈 값)으로 덮어써진다.

```
$ kubectl apply -k infra/k8s/overlays/local
secret/api-secret configured       ← 빈 값으로 덮어씀
secret/postgres-secret configured  ← 빈 값으로 덮어씀
service/api unchanged
deployment.apps/api unchanged
statefulset.apps/postgres created
```

이후 postgres Pod가 CrashLoopBackOff:

```
$ kubectl logs postgres-0
Error: Database is uninitialized and superuser password is not specified.
       You must specify POSTGRES_PASSWORD to a non-empty value for the
       superuser. For example, "-e POSTGRES_PASSWORD=password" on "docker run".

       You may also use "POSTGRES_HOST_AUTH_METHOD=trust" to allow all
       connections without a password. This is *not* recommended.

       See PostgreSQL documentation about "trust":
       https://www.postgresql.org/docs/current/auth-trust.html
```

### 원인

`base/kustomization.yaml`에 `secret.yaml`이 포함되어 있어서
`kubectl apply -k` 실행 시 빈 값으로 된 Secret이 클러스터에 적용됨.

### 해결

Secret 파일을 kustomization.yaml의 `resources`에서 제거.
Secret은 kustomize가 아닌 `kubectl create secret`으로 직접 관리.

```yaml
# base/kustomization.yaml
resources:
  - deployment.yaml
  - service.yaml
  - postgres/statefulset.yaml
  - postgres/service.yaml
  # secret.yaml은 포함하지 않음 — kubectl create secret으로 직접 생성
```

Secret 생성 명령어:

```bash
kubectl create secret generic postgres-secret \
  --from-literal=postgres-db=devopsim \
  --from-literal=postgres-user=devopsim \
  --from-literal=postgres-password=devopsim

kubectl create secret generic api-secret \
  --from-literal=database-url="postgresql://devopsim:devopsim@postgres:5432/devopsim"
```

---

## 문제 4: postgres PVC에 잘못된 초기화 상태 남음

### 증상

Secret 값을 올바르게 수정하고 StatefulSet을 재시작해도 같은 에러 반복.

```
$ kubectl rollout restart statefulset/postgres
$ kubectl logs postgres-0
Error: Database is uninitialized and superuser password is not specified.
```

### 원인

postgres가 처음 뜰 때 빈 패스워드로 초기화를 시도하면서 PVC(`postgres-data-postgres-0`)에
잘못된 상태가 기록됨. Secret을 수정해도 이미 PVC에 기록된 PGDATA가 남아있어 재시작해도 계속 실패.

### 해결

StatefulSet과 PVC를 완전히 삭제하고 재생성.

```bash
kubectl delete statefulset postgres
kubectl delete pvc postgres-data-postgres-0
kubectl apply -k infra/k8s/overlays/local
```

---

## 문제 5: api initContainer가 postgres 준비 전에 실행

### 증상

postgres가 아직 준비되지 않은 상태에서 api Pod의 migrate initContainer가 먼저 실행됨.

```
$ kubectl logs api-5b6cb869fc-g4zfn -c migrate
could not connect to postgres: Error: connect ECONNREFUSED 10.106.168.146:5432
    at TCPConnectWrap.afterConnect [as oncomplete] (node:net:1645:16) {
  errno: -111,
  code: 'ECONNREFUSED',
  syscall: 'connect',
  address: '10.106.168.146',
  port: 5432
}
Error: connect ECONNREFUSED 10.106.168.146:5432
    at TCPConnectWrap.afterConnect [as oncomplete] (node:net:1645:16) {
  errno: -111,
  code: 'ECONNREFUSED',
  syscall: 'connect',
  address: '10.106.168.146',
  port: 5432
}
```

### 원인

Deployment에 postgres 준비 완료를 기다리는 의존성 설정이 없다.
docker-compose의 `depends_on: condition: service_healthy`에 해당하는 기능이 K8s Deployment에는 없음.

### 해결 (임시)

postgres가 Running 상태가 된 후 api Deployment를 재시작.

```bash
kubectl wait --for=condition=ready pod/postgres-0 --timeout=60s
kubectl rollout restart deployment/api
kubectl rollout status deployment/api
```

### 해결

migrate를 initContainer에서 분리해 별도 Job으로 만들고, wait-for-postgres initContainer를 추가했다.

---

## 문제 6: wait-for-postgres initContainer가 응답 없이 멈춤 — pg_isready "no attempt"

### 증상

```
$ kubectl logs api-74d4657cf7-728vw -c wait-for-postgres
waiting...
postgres:5432 - no attempt
waiting...
postgres:5432 - no attempt
waiting...
```

Pod가 `Init:0/1` 상태에서 계속 멈춰있고, postgres는 `1/1 Running` 정상 상태임.

### 원인 (초기 오진)

처음에 Pod 레벨 `securityContext`의 `runAsUser: 1000`이 `postgres:16-alpine` initContainer에도 적용되어 `pg_isready`가 UID 1000으로 실행될 때 네트워크 연결을 못 한다고 판단했다.
→ `busybox:1.36` + `nc`로 교체했으나, 이는 불필요한 우회였다.

### 실제 원인

`securityContext`를 제거하고 `postgres:16-alpine` + `pg_isready`로 되돌렸더니 정상 동작했다.
Dockerfile에 이미 `USER node`가 선언되어 있어 securityContext 없어도 non-root(UID 1000)로 실행된다.
`runAsUser: 1000`을 명시했을 때 `postgres:16-alpine` 컨테이너와 충돌한 것이 실제 원인이었다.
(`postgres:16-alpine`의 기본 유저는 UID 70인데 `runAsUser: 1000`으로 강제 변경 시 pg_isready 실행 환경이 깨짐)

### 해결

`securityContext` 제거 + `postgres:16-alpine` + `pg_isready` 원래대로 복구.

```yaml
# 최종 (securityContext 없이 postgres:16-alpine 그대로 사용)
spec:
  # securityContext 제거 — Dockerfile의 USER node가 non-root 보장
  initContainers:
    - name: wait-for-postgres
      image: postgres:16-alpine
      command: ['sh', '-c', 'until pg_isready -h postgres -p 5432; do echo "waiting..."; sleep 2; done']
```

---

## 최종 기동 순서

```bash
# 1. Secret 생성
kubectl create secret generic postgres-secret \
  --from-literal=postgres-db=devopsim \
  --from-literal=postgres-user=devopsim \
  --from-literal=postgres-password=devopsim

kubectl create secret generic api-secret \
  --from-literal=database-url="postgresql://devopsim:devopsim@postgres:5432/devopsim"

# 2. postgres + api 배포
kubectl apply -k infra/k8s/overlays/local

# 3. postgres 준비 대기
kubectl wait --for=condition=ready pod/postgres-0 --timeout=60s

# 4. migrate Job 실행
kubectl apply -f infra/k8s/base/migrate-job.yaml
kubectl wait --for=condition=complete job/migrate --timeout=60s

# 5. 접속 테스트
kubectl port-forward service/api 3000:80
curl http://localhost:3000/health
curl http://localhost:3000/ready
```

## 내리기

```bash
# 리소스 삭제 (PVC 유지)
kubectl delete -k infra/k8s/overlays/local
kubectl delete secret api-secret postgres-secret

# 완전 초기화 (데이터 포함)
kubectl delete -k infra/k8s/overlays/local
kubectl delete pvc postgres-data-postgres-0
kubectl delete secret api-secret postgres-secret
```
