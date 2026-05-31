---
name: tdd
description: spec.md를 입력으로 받아 Red-Green-Refactor 사이클을 컨텍스트 격리된 sub-agent로 순차 실행한다. test-author → impl-author → refactor를 spawn하고 각 단계 후 부모가 자동 검증.
argument-hint: <spec-path> [target-package=detector]
allowed-tools: Agent Read Write Edit Bash Glob Grep
---

## 역할

TDD(Red-Green-Refactor) 사이클을 **컨텍스트 격리된 sub-agent**로 실행한다. 각 agent는 fresh context — 다른 agent의 작업 내용을 보지 않는다.

## 입력

- `$1`: spec.md 경로 (예: `.plan/specs/promql-tool.md`)
- `$2`: 타겟 패키지 경로 (기본값: `packages/detector/detector`)

## 사전 조건

- spec.md가 존재하고 `## Acceptance Criteria` 섹션에 1줄 = 1 테스트 형태로 항목이 나열되어 있어야 함
- 사전 조건 미충족 시 사용자에게 `/spec` 먼저 실행하라고 안내하고 종료

## 흐름

### Step 1 — Red: test-author agent

`Agent` 도구로 다음과 같이 spawn:

- subagent_type: `general-purpose`
- description: "TDD Red: test 작성"
- prompt (그대로 전달, 부모 대화/다른 파일 인용 금지):
  ```
  당신은 TDD Red 단계의 test author. 작업 환경: Python 3.12 + pytest(asyncio_mode=auto) + ruff. 프로젝트: devopsim/detector.

  입력: <spec.md 절대경로>. 이 파일만 읽고 그 외 구현 코드는 절대 보지 마라.

  작업:
  1. spec.md의 ## Acceptance Criteria + ## Error & Edge Cases 각 항목마다 정확히 1개의 실패 pytest 테스트 작성.
  2. **spec.md의 § In Scope 항목 전체를 테스트로 커버해야 한다.** AC/EC에 명시 안 된 In Scope 컴포넌트(Port, Adapter, factory, 변환 로직 등)가 있으면 `TEST FAIL: missing AC for <component>` 로 보고하고 즉시 중단.
  3. 테스트 이름은 AC/EC 문장을 snake_case로 옮긴 것.
  4. 한 테스트 = 한 행위(behavior). 내부 메서드 호출 횟수/순서 검증 금지.
  5. 외부 의존성(K8s/Prom/Loki/Anthropic 등 Protocol)은 **Fake<X>** 클래스로 모사 (test 파일 안 또는 tests/fakes/). unittest.mock 사용은 httpx/subprocess 경계에서만.
  6. **HTTP 경계 Adapter**(httpx 사용)는 `httpx.MockTransport` 또는 `respx`로 boundary 단위 테스트. 요청 URL/메서드/쿼리 파라미터를 단언.
  7. async def test_* 사용. asyncio_mode=auto이므로 마커 불필요.
  8. 출력 파일: packages/detector/tests/test_<feature>.py (기존 평탄 구조 유지)
  9. ruff 모두 통과 필수. 작성 후 다음 순서로 실행:
     - `uv run ruff check <path> --fix` (isort 등 자동 수정 가능한 lint 적용 — ruff format은 import 정렬 안 함)
     - `uv run ruff format <path>` (코드 포매팅)
     - `uv run ruff check <path>` 와 `uv run ruff format --check <path>` 모두 pass 확인.

  완료 후 다음을 응답하라:
  - 생성한 파일 경로
  - 작성한 테스트 수 (AC/EC + In Scope 보강분)
  - spec.md §3 In Scope 각 항목 → test 매핑 표 (누락 0 확인)
  - `uv run pytest <path> --tb=short` 실행 결과 (반드시 fail이어야 함)
  - "RED OK" 또는 "RED FAIL: <reason>"
  ```

부모 자동 검증:
```bash
uv run pytest packages/detector/tests/unit/test_<feature>.py --tb=short 2>&1 | tee /tmp/red.log
grep -Eq "^[0-9]+ failed" /tmp/red.log    # 실패 1개 이상
git diff --stat -- 'packages/detector/detector/' | grep -q . && echo "FAIL: production 코드 변경됨" && exit 1
```
실패 시 사용자에게 보고 후 중단.

### Step 2 — Green: impl-author agent

`Agent` 도구로 spawn:

- subagent_type: `general-purpose`
- description: "TDD Green: 최소 구현"
- prompt:
  ```
  당신은 TDD Green 단계의 implementation author.

  입력: tests/unit/test_<feature>.py 절대경로. 이 테스트 파일만 읽어라. spec.md, 다른 impl 파일은 보지 마라.

  작업:
  1. 테스트가 import하는 모듈/함수/클래스 시그니처를 파악.
  2. 그 테스트만 통과시키는 가장 단순한 구현을 작성.
  3. Over-engineering 금지: 미사용 파라미터, 추측성 분기, 미래용 추상화 X.
  4. 새 의존성 추가 금지(pyproject.toml 수정 X).
  5. ruff 통과 필수.
  6. Protocol 기반 DI 구조 유지(handler에 외부 의존성을 인자로 받는 형태).

  출력 파일: packages/detector/detector/<feature>.py (또는 적절한 위치)

  검증 후 응답:
  - 생성/수정한 파일 경로
  - `uv run pytest -x -q` 실행 결과 (모두 통과여야 함)
  - "GREEN OK" 또는 "GREEN FAIL: <reason>"
  ```

부모 자동 검증:
```bash
uv run pytest -x -q 2>&1 | tee /tmp/green.log
grep -Eq "^[0-9]+ passed" /tmp/green.log
grep -Eq " failed" /tmp/green.log && echo "FAIL: 다른 테스트 깨짐" && exit 1
uv run ruff check . --no-fix
```

### Step 3 — Refactor: refactor agent

`Agent` 도구로 spawn:

- subagent_type: `general-purpose`
- description: "TDD Refactor: 정리"
- prompt:
  ```
  당신은 TDD Refactor 단계의 정리 담당.

  입력: 방금 구현된 파일 경로 + "모든 테스트가 현재 초록"이라는 사실.

  작업:
  1. 구현 파일을 읽고 다음 항목으로 평가: 명명, 중복, 함수 길이, 깊은 중첩, magic number, dead code.
  2. 행위 보존 리팩토링만 적용. 공개 API 시그니처 변경 X.
  3. 테스트 파일은 절대 수정 X.

  완료 후:
  - 적용한 리팩토링 변경 요약
  - `uv run pytest -q && uv run ruff check . && uv run ruff format --check .` 실행 결과
  - "REFACTOR OK" 또는 "REFACTOR FAIL"
  ```

부모 자동 검증:
```bash
uv run pytest --cov=detector --cov-fail-under=90 -q
uv run ruff check . && uv run ruff format --check .
git diff -- 'packages/detector/tests/**' | wc -l    # 반드시 0
```

### Step 4 — 사용자 승인

세 단계 모두 통과 후 부모 Claude가:
- 변경된 파일 목록과 핵심 diff 요약
- 추가된 테스트 수와 통과율
- coverage 수치
를 보여주고 사용자에게 **"이 사이클을 커밋해도 될까요?"** 확인. OK 받으면 커밋 메시지 제안 후 사용자 재승인 → 커밋.

## 안티패턴 (피해야 할 것)

- spec author를 자동화하지 마라. spec.md는 사용자/부모가 작성 (사용자 의도 곡해 방지).
- sub-agent prompt에 부모 conversation 내용을 인용하지 마라 (격리 보장 위반).
- 한 사이클이 30분 넘어가면 spec을 더 작은 단위로 쪼개라.
- mock 라이브러리(unittest.mock, pytest-mock)는 httpx 경계에서만. Protocol 경계는 Fake 클래스.

## DoD 체크리스트

각 단계 자동 검증에 모두 통과해야 다음 단계 진입. 한 단계라도 fail이면 사용자에게 보고 후 중단(자동 재시도 X — 사람 판단).
