# 3. API 명세

> 엔드포인트, 요청/응답 형식은 고정입니다. 임의로 바꾸지 말고, 변경이 필요하면 조장에게 요청하세요.
> 모든 요청/응답 필드는 2번(공통 데이터 모델) 섹션의 스키마를 그대로 따릅니다.

---

## 3-1. 사용자/배정 (담당: 팀원 B)

| Method | Endpoint | 인증 | 요청 | 응답 |
|---|---|---|---|---|
| POST | `/user/register` | 불필요 | `{name: str, email: str, password: str, role: "newcomer" \| "mentor"}` | `User` (password_hash 제외) |
| POST | `/user/login` | 불필요 | `{email: str, password: str}` | `{access_token: str, token_type: "bearer", user: User}` |
| GET | `/user/{user_id}` | 필요 | - | `User` (password_hash 제외) |
| DELETE | `/user/{user_id}` | 필요 (본인만) | - | 204 No Content |
| POST | `/assignment` | 필요 (mentor) | `{mentor_id: str, newcomer_id: str, document_id: str}` | `Assignment` |
| GET | `/assignment?newcomer_id=` | 필요 (본인만) | - | `Assignment` |
| GET | `/assignment?mentor_id=` | 필요 (mentor, 본인만) | - | `list[Assignment]` |

**설명**
- `/user/register`: 이름·이메일·비밀번호·역할을 입력받아 사용자 생성. 비밀번호는 해시해서 `password_hash`로 저장, 응답에는 포함하지 않음. 이메일은 로그인 식별자로만 쓰이며 중복 가입 방지 외의 인증(메일 발송 등)은 하지 않음 (2차 확장 항목)
- `/user/login`: 이메일+비밀번호 검증 후 JWT(`access_token`) 발급. 프론트엔드는 이후 모든 요청에 `Authorization: Bearer <access_token>` 헤더를 실어 보냄
- `/user/{user_id}` (DELETE, 신설): 회원 탈퇴. **토큰의 `user_id`가 경로의 `user_id`와 같아야 함** — 아니면 403 (3-9). `users` 행만 삭제하는 1차 범위이며, 사수가 올린 문서/배정이나 신입의 채팅·체크리스트 기록에 대한 연쇄 삭제는 하지 않음 — 재배정 시 `chapter_id`가 고아로 남는 것(위 재배정 설명 참고)과 같은 성격의 accepted 1차 한계
- `/assignment` (POST): 사수가 업로드한 문서를 특정 신입과 연결. 이 호출이 있어야 해당 신입이 챗봇을 사용할 수 있음. 토큰의 `user_id`가 요청 바디의 `mentor_id`와 일치해야 함 (3-9 참고). **같은 신입에게 이미 활성 Assignment가 있는 상태로 다시 호출되면(재배정) 기존 행을 `document_id`만 교체해서 덮어씀(UPDATE) — 새 행을 만들지 않고 `assignment_id`/`assigned_at`은 그대로 유지** (팀원 B 제안 채택; 이유는 2번 문서 `Assignment.assigned_at` 설명 참고). 재배정 후 기존 `ChecklistItem.chapter_id`/`ChatLog.matched_chapter_id`가 옛 문서의 챕터를 가리키는 채로 남는 문제는 1차 빌드 범위 밖으로 둠(드문 케이스로 간주)
- `/assignment?newcomer_id=`: 신입 본인이 자기 사수 이름을 조회할 때 사용(4-3 참고), 챗봇·체크리스트·리포트 모듈도 내부적으로 같은 조회 로직 사용. **토큰의 `user_id`가 그 `newcomer_id`와 같아야 함** — 아니면 403 (3-9 신설)
- `/assignment?mentor_id=`: 사수 화면에서 "내가 담당하는 신입 목록"을 보여줄 때 사용. **토큰의 `user_id`가 그 `mentor_id`와 같아야 함** — 아니면 403 (3-9 신설)

---

## 3-2. 문서 처리 (담당: 팀원 A)

| Method | Endpoint | 요청 | 응답 |
|---|---|---|---|
| POST | `/document/upload` | `{mentor_id: str, files: list[<파일>]}` **또는** `{mentor_id: str, chapters: list[{title: str, content: str}]}` + 공통 선택 필드 `label: str` | `{document_id: str, chapters: list[DocumentChapter]}` |
| GET | `/document/{document_id}/chapters` | - | `list[DocumentChapter]` |
| GET | `/document?mentor_id=` | - | `list[{document_id: str, label: str, uploaded_at: datetime}]` |

**설명**
- `/document/upload`: 사수가 인수인계서를 등록. 입력 방식은 두 가지
  - **파일 업로드** (`files`, 신설 — 복수 지원): 서버가 파일마다 목차(장-절)를 자동 파싱해서 `DocumentChapter` 생성. **파일을 여러 개 보낼 수 있음** — 인수인계서가 여러 파일로 나뉘어 있는 경우(부서별 별도 파일 등)를 지원하기 위함. 파일을 받은 순서대로 각각 독립적으로 파싱한 뒤 챕터를 이어붙여 **하나의 `document_id`**로 합침 — chapter_id는 파일과 무관하게 매번 새로 발급되므로 파일 간 목차 번호가 겹쳐도 문제없음
  - **직접 입력** (`chapters`): 사수가 화면에서 챕터를 하나씩 작성(제목+본문)해서 이미 확정된 구조로 보냄 — 서버는 자동 파싱 없이 받은 그대로 `DocumentChapter`로 저장 (프론트 "챕터 추가" 폼 UI, 4-2/4-3 브리프 참고)
  - 두 경로 모두 챕터 저장 후 각 챕터 내용을 청킹해서 `DocumentChunk` 생성 + 임베딩 후 ChromaDB에 저장까지 한 번에 처리. 청크 분할 기준(문단/글자 수 등)은 입력 방식과 무관하게 팀원 A 재량. `document_id`는 이 호출에서 새로 발급됨. 파일 크기 상한(10MB, 5-9)은 파일 하나 기준으로 각각 적용
  - 업로드 시점에 대표 `label`(목록 화면용, 아래 참고)을 함께 저장. **요청에 `label`을 직접 보내면 그 값을 그대로 쓰고(신설), 비우면** file 모드는 첫 파일명에서 확장자를 뺀 값(여러 개면 "A 외 N개"), chapters 모드는 첫 챕터 제목으로 서버가 자동 계산. 수정 API는 따로 없음 — `label`을 훑어보는 목록 화면 자체가 없고(배정 드롭다운에만 쓰임) 재업로드가 더 단순하기 때문
- `/document/{id}/chapters`: HR 화면에서 목차 트리를 보여줄 때, 또는 체크리스트 작성 시 챕터 선택 목록을 채울 때 사용
- `/document?mentor_id=` (신설): 이 사수가 올린 문서 목록을 최신순으로 반환 — 배정 화면의 문서 선택 드롭다운용. 토큰의 `user_id`가 그 `mentor_id`와 같아야 함(3-9). `label`엔 `Document`에 제목 필드가 없어서(2-3) 업로드 시점에 계산해둔 대표 이름이 담김. **이전엔 이 목록을 프론트가 브라우저 localStorage로만 들고 있어서 다른 브라우저/기기에서는 안 보였음 — 이 API로 대체**

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
- 1차 빌드부터 이메일+비밀번호 기반 로그인과 JWT 인증을 구현함 (이메일 인증 메일 발송만 2차로 미룸). `/user/register`, `/user/login`을 제외한 모든 API는 `Authorization: Bearer <access_token>` 헤더 필요 — 자세한 규칙은 3-9 참고
- `/chat/ask`, `/checklist/draft`, `/report/generate` 등 LLM을 호출하는 엔드포인트는 사용자별·IP별 rate limit이 걸려 있음 (5-9 참고). 한도 초과 시 429 응답

---

## 3-8. 모듈별 엔드포인트 요약

| 담당 | 엔드포인트 |
|---|---|
| 팀원 B | `/user/register`, `/user/login`, `/user/{user_id}`, `/assignment` (POST/GET) |
| 팀원 A | `/document/upload`, `/document/{id}/chapters`, `/checklist` (POST/GET/PATCH), `/checklist/{id}/reorder`, `/checklist/{id}/complete` |
| 조장 | `/chat/ask`, `/chat/logs`, `/checklist/draft`, `/report/generate`, `/report/{newcomer_id}`, `/report/{newcomer_id}/history` |

---

## 3-9. 인증 규칙 (1차 빌드부터 적용)

> 인증 로직 자체(`/user/login`에서 토큰 발급, 토큰 검증 의존성)는 팀원 B가 `backend/core/auth.py`에 구현하고, 나머지 담당자는 자기 라우터에서 이 의존성을 가져다 쓰기만 하면 됩니다 (5-2 폴더 구조 참고).

- `/user/register`, `/user/login`을 제외한 모든 엔드포인트는 `Authorization: Bearer <access_token>` 헤더가 필수입니다. 헤더가 없거나 토큰이 만료/위조된 경우 **401**
- 서버는 토큰에서 `user_id`, `role`을 추출합니다. 요청 바디·쿼리에 `newcomer_id`/`mentor_id` 등 신원 필드가 함께 오는 기존 API 형식은 그대로 유지하되(요청/응답 스키마 변경 없음), 서버가 **토큰의 user_id·role과 그 필드가 일치하는지 검증**합니다. 불일치 시 **403**
  - 예: `POST /assignment` 요청 바디의 `mentor_id`는 토큰의 `user_id`와 같아야 함
  - 예: `POST /checklist/{item_id}/complete` 요청 바디의 `newcomer_id`는 토큰의 `user_id`와 같아야 함
  - 예: `GET /assignment?newcomer_id=`의 `newcomer_id`, `GET /assignment?mentor_id=`의 `mentor_id`도 각각 토큰의 `user_id`와 같아야 함 (신설 — 그 전엔 로그인만 하면 아무 신입/사수의 배정 정보나 조회 가능했던 문제, 팀원 B 지적으로 발견)
- `mentor` 전용 API(`/document/upload`, `/assignment` POST, `/checklist/draft`, `/checklist` POST/PATCH/reorder, `/report/*`, `/assignment?mentor_id=`)는 토큰의 `role`이 `"mentor"`가 아니면 **403**
- `GET /user/{user_id}`는 신원 필드가 URL 경로에만 있지만, 노출되는 정보가 이름/이메일/역할 정도라 토큰만 유효하면 통과 (다른 사람 조회 자체는 허용 — 사수 이름 조회 등 기존 플로우 유지)
- `DELETE /user/{user_id}`(신설)는 GET과 달리 **본인만** 가능 — 경로의 `user_id`가 토큰의 `user_id`와 달라도 다른 사람 계정을 지울 수 있으면 안 되므로, 조회와 달리 항상 self-check함. 불일치 시 **403**
- `GET /document/{document_id}/chapters`는 다름 — 챕터 본문 전체(인수인계서 내용)가 그대로 노출되는 조회라 토큰 유효성만으로는 부족함. **토큰의 `user_id`가 (a) 그 `document_id`를 업로드한 사수이거나, (b) 그 `document_id`로 배정받은 신입(`Assignment.newcomer_id`) 중 하나여야** 통과, 둘 다 아니면 **403**. 이 검증을 하려면 `document.py`(팀원 A)가 `Assignment`(팀원 B 소유 모델/데이터) 조회가 필요하므로, 조회 방식은 두 담당자가 직접 협의해서 정함 (0번 문서의 "인접 담당자끼리 협의" 원칙)
  - 이 검증이 가능하려면 `document/upload` 시점에 "이 `document_id`를 누가(mentor_id) 올렸는지"를 어딘가에 남겨둬야 함 — 이 매핑은 2번 문서(공통 데이터 모델)에 별도 필드로 없으므로, 팀원 A가 자기 재량으로 내부 테이블에 기록 (프론트/타 모듈에 노출되는 스키마가 아니라 내부 구현 디테일)


