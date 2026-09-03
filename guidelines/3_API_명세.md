# 3. API 명세

> 엔드포인트, 요청/응답 형식은 고정입니다. 임의로 바꾸지 말고, 변경이 필요하면 조장에게 요청하세요.
> 모든 요청/응답 필드는 2번(공통 데이터 모델) 섹션의 스키마를 그대로 따릅니다.

---

## 3-1. 사용자/배정 (담당: 팀원 B)

| Method | Endpoint | 요청 | 응답 |
|---|---|---|---|
| POST | `/user/register` | `{name: str, role: "newcomer" \| "mentor"}` | `User` |
| GET | `/user/{user_id}` | - | `User` |
| POST | `/assignment` | `{mentor_id: str, newcomer_id: str, document_id: str}` | `Assignment` |
| GET | `/assignment?newcomer_id=` | - | `Assignment` |
| GET | `/assignment?mentor_id=` | - | `list[Assignment]` |

**설명**
- `/user/register`: 최초 진입 시 이름·역할 입력받아 사용자 생성 (1차 빌드는 비밀번호 등 정식 인증 없음)
- `/assignment` (POST): 사수가 업로드한 문서를 특정 신입과 연결. 이 호출이 있어야 해당 신입이 챗봇을 사용할 수 있음
- `/assignment?newcomer_id=`: 챗봇·체크리스트·리포트 모듈이 "이 신입의 배정 문서가 뭔지" 확인할 때 내부적으로 사용
- `/assignment?mentor_id=`: 사수 화면에서 "내가 담당하는 신입 목록"을 보여줄 때 사용

---

## 3-2. 문서 처리 (담당: 팀원 A)

| Method | Endpoint | 요청 | 응답 |
|---|---|---|---|
| POST | `/document/upload` | `{mentor_id: str, file/text}` | `{document_id: str, chapters: list[DocumentChapter]}` |
| GET | `/document/{document_id}/chapters` | - | `list[DocumentChapter]` |

**설명**
- `/document/upload`: 사수가 인수인계서를 업로드. 챕터 단위로 구조화(`DocumentChapter`) + 청킹·임베딩(`DocumentChunk`, ChromaDB 저장)까지 한 번에 처리. `document_id`는 이 호출에서 새로 발급됨
- `/document/{id}/chapters`: HR 화면에서 목차 트리를 보여줄 때, 또는 체크리스트 작성 시 챕터 선택 목록을 채울 때 사용

---

## 3-3. 챗봇 (담당: 조장)

| Method | Endpoint | 요청 | 응답 |
|---|---|---|---|
| POST | `/chat/ask` | `{newcomer_id: str, question: str}` | `{answer: str, source_chapter_id: str \| None, answered: bool}` |
| GET | `/chat/logs?newcomer_id=` | - | `list[ChatLog]` |

**설명**
- `/chat/ask`: 내부적으로 `newcomer_id`로 Assignment를 조회해 배정된 `document_id`를 먼저 확인 → 그 문서 범위 안에서만 ChromaDB 검색 → 답변 생성. `ChatLog` 저장까지 같이 수행 (별도 저장 API 없음)
- 배정(Assignment)이 없는 신입이 요청하면 에러 응답 반환 (3-7번 공통 에러 포맷)
- 답변 실패 시 `answer`에는 "문서에 없는 내용이니 담당자에게 문의하세요" 계열 고정 문구가 담기고, `answered = false`
- `/chat/logs`: 리포트 생성 모듈이 내부적으로 호출하거나, HR가 원본 로그를 확인하고 싶을 때 사용 (질문 원문 포함 — HR 전용 화면에서만 노출)

---

## 3-4. 체크리스트 — 초안 생성 (담당: 조장)

| Method | Endpoint | 요청 | 응답 |
|---|---|---|---|
| POST | `/checklist/draft` | `{document_id: str}` | `list[{title: str, chapter_id: str}]` |

**설명**
- 문서 챕터를 순회하며 LLM이 태스크 후보를 생성. **이 단계는 저장하지 않음** — 미리보기 응답만 반환
- 반환된 리스트를 사수가 화면에서 수정·삭제·추가한 뒤, 3-5번의 저장 API로 넘겨야 실제 `ChecklistItem`이 됨 (이때 `newcomer_id`가 함께 지정되어야 함)

---

## 3-5. 체크리스트 — 편집/저장/완료 (담당: 팀원 A)

| Method | Endpoint | 요청 | 응답 |
|---|---|---|---|
| POST | `/checklist` | `{items: list[ChecklistItem 일부 필드 (newcomer_id 포함)]}` | `list[ChecklistItem]` |
| GET | `/checklist?newcomer_id=` | - | `list[ChecklistItem]` |
| PATCH | `/checklist/{item_id}` | 수정할 필드 (`title`, `chapter_id` 등) | `ChecklistItem` |
| PATCH | `/checklist/{item_id}/reorder` | `{order: int}` | `{status: "ok"}` |
| POST | `/checklist/{item_id}/complete` | `{newcomer_id: str}` | `{status: "done", completed_at: datetime}` |

**설명**
- `/checklist` (POST): 직접 작성이든 AI 초안 승인이든, 최종 확정된 항목은 전부 이 API로 저장. `newcomer_id`, `source`(`"manual"` / `"ai_draft"`) 값을 포함해서 보냄
- `/checklist/{item_id}`: 사수가 항목 내용을 나중에 수정할 때 사용
- `/checklist/{item_id}/complete`: 신입사원이 셀프 체크할 때 호출 — 별도 검증 없이 시각만 기록

---

## 3-6. 리포트 (담당: 조장)

| Method | Endpoint | 요청 | 응답 |
|---|---|---|---|
| POST | `/report/generate` | `{newcomer_id: str, period_start: datetime, period_end: datetime}` | `AdaptationReport` |
| GET | `/report/{newcomer_id}` | - | `AdaptationReport` |
| GET | `/report/{newcomer_id}/history` | - | `list[AdaptationReport]` |

**설명**
- `/report/generate`: 사수가 리포트 생성을 요청하는 시점에 호출. `ChatLog` + `ChecklistItem` 완료 로그를 모아 4개 신호(성장곡선/히트맵/완료-이해 불일치/침묵 위험)를 계산하고, 결과를 `AdaptationReport`로 저장 후 반환
  - `period_start`/`period_end`는 프론트엔드가 기본값을 자동 채워서 보냄: 이전 리포트가 있으면 "이전 리포트의 `period_end` ~ 지금", 처음 생성이면 "Assignment 생성일 ~ 지금". 사수가 원하면 직접 수정 가능
- `/report/{newcomer_id}`: `generated_at` 기준 가장 최근 리포트 1개 조회
- `/report/{newcomer_id}/history`: 이 신입에 대해 생성된 모든 리포트를 `generated_at` 내림차순으로 반환 (지난 리포트와 비교할 때 사용)
- HR 화면 전용. 신입사원 화면에서는 세 API 모두 호출하지 않음

---

## 3-7. 공통 규칙

- 모든 에러 응답은 동일한 포맷 사용: `{"error": true, "message": "..."}`
- 날짜/시간 필드는 ISO 8601 형식 문자열로 주고받음 (`datetime` 타입 직렬화 시)
- 1차 빌드에서는 비밀번호·토큰 기반 인증을 구현하지 않음. `user_id`를 프론트엔드가 보관해 매 요청에 실어 보내는 방식으로 단순화 (추후 정식 인증으로 확장 가능)

---

## 3-8. 모듈별 엔드포인트 요약

| 담당 | 엔드포인트 |
|---|---|
| 팀원 B | `/user/register`, `/user/{user_id}`, `/assignment` (POST/GET) |
| 팀원 A | `/document/upload`, `/document/{id}/chapters`, `/checklist` (POST/GET/PATCH), `/checklist/{id}/reorder`, `/checklist/{id}/complete` |
| 조장 | `/chat/ask`, `/chat/logs`, `/checklist/draft`, `/report/generate`, `/report/{newcomer_id}`, `/report/{newcomer_id}/history` |
