"""체크리스트 초안 생성 (담당: 조장) — guidelines 3-4, 3-9, 4-1, 5-9, 1-5.

핵심 흐름:
  1. document_id에 해당하는 DocumentChapter를 MySQL에서 조회 (ChromaDB 접근 금지 — guidelines 1-5)
  2. 챕터를 순회하며 LLM으로 태스크 후보 {title, chapter_id} 생성
  3. 저장하지 않고 리스트만 반환 (미리보기 — 실제 저장은 팀원 A의 POST /checklist)

TODO(조장): 아래는 main.py가 부팅되도록 만든 최소 스텁입니다. 직접 채워서 구현하세요.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from core.auth import CurrentUser, get_current_user, require_role
from core.rate_limit import IP_RATE_LIMIT, USER_RATE_LIMIT, ip_limiter, user_limiter

router = APIRouter(tags=["checklist_draft"])


@router.post("/checklist/draft")
@user_limiter.limit(USER_RATE_LIMIT)
@ip_limiter.limit(IP_RATE_LIMIT)
def draft_checklist(request: Request, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(조장): require_role(current_user, "mentor") 검증
    # DocumentChapter만 읽어서 {title, chapter_id} 리스트 생성 (MySQL 저장 없음)
    # OpenAI 호출 시 max_tokens 상한 필수, 저렴한 모델 사용 우선 검토 (guidelines 5-9)
    raise HTTPException(status_code=501, detail="담당자(조장) 구현 필요")
