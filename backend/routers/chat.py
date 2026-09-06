"""챗봇 RAG (담당: 조장) — guidelines 3-3, 3-9, 4-1, 5-9.

핵심 흐름 (LangGraph 그래프로 구성 예정, guidelines 4-1):
  1. 조회: newcomer_id로 Assignment 조회 -> document_id 확정 (Assignment 없으면 404)
  2. 검색: document_id 범위로 ChromaDB 검색 (core.chroma_client.get_collection(document_id))
  3. 판단: 검색 결과 유사도가 충분한지 판단
  4. 생성: 충분하면 OpenAI로 답변 생성 + matched_chapter_id 기록,
     부족하면 answered=False + 고정 문구 ("문서에 없는 내용이니 담당자에게 문의하세요")
     — 이 시점에 "문서 보강" 언급 절대 금지 (guidelines 1-7, 4-1)
  5. 저장: ChatLog 생성 (question_type 분류 포함)

TODO(조장): 아래는 main.py가 부팅되도록 만든 최소 스텁입니다. 직접 채워서 구현하세요.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from core.auth import CurrentUser, get_current_user, require_self
from core.rate_limit import IP_RATE_LIMIT, USER_RATE_LIMIT, ip_limiter, user_limiter

router = APIRouter(tags=["chat"])


@router.post("/chat/ask")
@user_limiter.limit(USER_RATE_LIMIT)
@ip_limiter.limit(IP_RATE_LIMIT)
def ask(request: Request, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(조장): require_self(current_user, 요청 바디의 newcomer_id) 검증
    # 이후 위 핵심 흐름(조회->검색->판단->생성->저장) 구현.
    # OpenAI 호출 시 max_tokens 상한 필수 (guidelines 5-9)
    raise HTTPException(status_code=501, detail="담당자(조장) 구현 필요")


@router.get("/chat/logs")
def get_logs(newcomer_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(조장): newcomer_id로 ChatLog 목록 조회 (HR 화면·리포트 모듈에서 사용)
    raise HTTPException(status_code=501, detail="담당자(조장) 구현 필요")
