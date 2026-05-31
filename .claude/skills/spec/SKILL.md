---
name: spec
description: 모호한 기능 아이디어를 5단계 인터뷰로 구체화해 .plan/specs/<feature>.md를 작성한다. test-author agent가 단독으로 읽고 1:1로 테스트를 도출할 수 있는 EARS + Given-When-Then 형식. /tdd 스킬의 입력으로 사용.
argument-hint: <feature-idea>
allowed-tools: Read Write Edit Glob Grep Bash AskUserQuestion
---

## 역할

사용자의 모호한 기능 아이디어를 5단계 인터뷰로 정제해 spec.md를 생성한다. spec.md는 **"Acceptance Criteria 한 줄 = pytest 함수 한 개"** 라는 1:1 invariant를 만족해야 한다.

이게 곧 harness engineering의 *guide*(feedforward 제약)다. `/tdd` 스킬의 test-author/impl-author/refactor-agent가 안전하게 컨텍스트 격리된 채로 동작하려면 spec의 품질이 결정적이다.

## 입력

- `$1`: 기능 아이디어 한 줄 (예: "promql tool 만들기", "OOM detector trigger 추가")

비어있으면 사용자에게 한 줄 요청을 받는다.

## 출력

`.plan/specs/<kebab-case-feature>.md` 파일.

## 인터뷰 5단계

### Step 1 — Restate & Frame

사용자 한 줄 요청을 한 문단으로 재진술한다. 형식:

> "내가 이해한 바: <한 문단 요약>. 맞나요?"

불분명한 영역에는 `[NEEDS CLARIFICATION: ...]` 마커를 남기고 단계 2에서 해소한다.

### Step 2 — Coverage-based questioning

다음 8개 카테고리에서 **누락된 정보만** 적응형으로 질문한다. 규칙:

- **한 turn 최대 2개 질문.** 적은 질문이 가능하면 적게.
- **답 나온 영역 재질문 금지.**
- `AskUserQuestion` 도구로 옵션식 선택지 제공 (사용자 빠른 선택).
- **"모르겠다/상관없다"** 답변엔: 합리적 디폴트 옵션을 추천(Recommended)으로 표시하고 confirm만 받는다.

질문 카테고리:

| # | 카테고리 | 예시 질문 |
|---|---|---|
| 1 | 목적/사용자 | 누가/언제/왜 호출? user story 한 줄로 |
| 2 | 입력 계약 | 어떤 입력? 타입/필수/유효 범위/예시 1개 |
| 3 | 출력 계약 | 성공 시 정확히 무엇을 반환/변경? 예시 응답 |
| 4 | 트리거/전제조건 | 동작 조건? EARS 분류 — `While`(상태), `When`(이벤트), `If`(분기) 중 어느 것? |
| 5 | 실패/예외 | 잘못된 입력/권한/외부 의존성 실패 시 각각 어떻게? status code, 에러 형식 |
| 6 | 경계 | 0개/최댓값/동시성/중복 호출/멱등성 중 정의 필요한 것? |
| 7 | 비기능 | 성능 SLA, 보안, 감사로그, 리소스 한계 중 명시할 것? |
| 8 | Out of Scope | 이 PR에서 **명시적으로 안 하는 것**? (사용자가 기대할 법한데 제외) |

선택 추가 질문:
- "기존 코드/엔드포인트 중 비슷한 패턴이 있는가?" → 일관성 단서
- "이 기능이 '됐다'고 판단할 *관찰 가능한 신호* 1개?" → 검증 hook

### Step 3 — Acceptance criteria 합의

누적 답변을 EARS + Given-When-Then 형태로 5~15개 작성한다.

- EARS 형식: `When <trigger>, the system shall <response>.`
- 보조 GWT: `Given <state>, When <action>, Then <observable outcome>.`
- **한 AC = 한 테스트.** 관찰 가능한 outcome만. "잘 동작한다" 같은 표현 금지.

초안을 사용자에게 보여주고 빠진 것 추가/수정 받는다.

### Step 4 — Edge case & Out of Scope

- Error/Edge case를 EC-1, EC-2... 로 명시적 enumeration. 형식: `If <invalid>, then the system shall <response>.`
- Out of Scope 목록을 명시 — test-author가 테스트 안 만들 영역 (스코프 누수 방지).

### Step 5 — Review checklist (self-check)

spec 초안에 대해 다음을 자체 확인:

- [ ] 모든 AC가 정확히 1개 pytest 함수로 매핑 가능한가?
- [ ] AC가 관찰 가능한 outcome만 기술하는가? (내부 메서드 호출/상태 검증 X)
- [ ] Out of Scope가 명시되어 있는가?
- [ ] 외부 의존성(Protocol)이 명시되어 있는가? (Fake 클래스가 어디 필요한지 test-author가 알 수 있게)
- [ ] `[NEEDS CLARIFICATION]` 마커가 없거나, 의도적으로 남긴 것인가?
- [ ] **§3 In Scope의 모든 항목이 §5 AC 또는 §6 EC에 매핑되는가?** 컴포넌트(Port, Adapter, factory, 변환 로직 등)별 행동이 빠짐없이 AC로 표현되어야 한다 — 누락 시 test-author가 못 만들고 impl-author가 안 만든다.
- [ ] **외부 시스템 경계(httpx/subprocess 등)가 In Scope에 있으면 Adapter 행동을 별도 AC로?** Port behavior AC만으로는 boundary 검증이 누락된다. Adapter는 `httpx.MockTransport` / `respx` 같은 boundary mock으로 검증 가능.

통과 시 파일 저장 후:

```
✅ spec 완료: .plan/specs/<feature>.md
다음: /tdd .plan/specs/<feature>.md
```

## spec.md 출력 템플릿

```markdown
# Spec: <feature name>

## 1. Goal
<1-2 문장. why + who>

## 2. User Story
As a <role>, I want <capability>, so that <benefit>.

## 3. Scope
### In Scope
- ...

### Out of Scope
- ...   <!-- test-author가 테스트 안 만들 영역 -->

## 4. Inputs / Outputs Contract
| Field | Type | Required | Constraints | Example |
| ----- | ---- | -------- | ----------- | ------- |
|       |      |          |             |         |

## 5. Acceptance Criteria (EARS + GWT)
- **AC-1.** When <trigger>, the system shall <response>.
  - Given <state>, When <action>, Then <observable outcome>.
- **AC-2.** ...

> 규칙: 한 AC = 한 pytest 함수.

## 6. Error & Edge Cases
- **EC-1.** If <invalid input>, then the system shall return <error response>.
- **EC-2.** ...

## 7. Non-Functional
- Performance: ...
- Security: ...
- Observability: ...

## 8. External Dependencies (Protocol → Fake)
- `KubernetesPort` → `tests/fakes/FakeK8s`
- `PrometheusPort` → `tests/fakes/FakePrometheus`
- ...

## 9. Open Questions
- [NEEDS CLARIFICATION: ...]  <!-- 비어 있으면 spec 완료 -->
```

## Anti-patterns (피해야 할 것)

- ❌ 한 turn에 5개 이상 질문 — 사용자 피로/이탈
- ❌ 모든 카테고리를 강제 질문 — 누락된 것만
- ❌ "모르겠다"에 추가 캐묻기 — 디폴트 옵션 제안 후 confirm
- ❌ spec author를 자동화(별도 sub-agent) — 사용자 의도 곡해 위험. 대화 흐름으로 진행
- ❌ `[NEEDS CLARIFICATION]` 마커 무시한 채 완료 — 마커 있으면 spec 미완 표시
- ❌ AC에 구현 디테일 포함 — 관찰 가능한 outcome만

## 참고

이론적 배경: Martin Fowler "Harness engineering for coding agent users" (2026), GitHub Spec Kit, AWS Kiro, EARS(Mavin et al.), LLMREI(RE 2025).
