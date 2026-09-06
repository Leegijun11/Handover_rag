"""적응도 리포트 (담당: 조장) — guidelines 3-6, 3-9, 4-1, 5-9.

핵심 흐름:
  1. newcomer_id 기준 ChatLog + ChecklistItem(완료 로그) 조회
  2. 4개 신호 계산: growth_curve / chapter_heatmap / gap_task / silence_risk
  3. 신호별 LLM 요약(summary) 생성 — 질문 원문 그대로 노출 금지, 패턴 단위로만 서술
  4. AdaptationReport로 저장 (generated_at = 실제 생성 시각) 후 반환

TODO(조장): 아래는 main.py가 부팅되도록 만든 최소 스텁입니다. 직접 채워서 구현하세요.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from core.auth import CurrentUser, get_current_user, require_role
from core.rate_limit import IP_RATE_LIMIT, USER_RATE_LIMIT, ip_limiter, user_limiter

router = APIRouter(tags=["report"])


@router.post("/report/generate")
@user_limiter.limit(USER_RATE_LIMIT)
@ip_limiter.limit(IP_RATE_LIMIT)
def generate_report(request: Request, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(조장): require_role(current_user, "mentor") 검증
    # 같은 newcomer_id로 마지막 생성 후 최소 재생성 간격(예: 5분) 이내면 최근 결과 반환 (guidelines 5-9)
    # 이후 위 핵심 흐름(집계->4개 신호->LLM 요약->저장) 구현
    raise HTTPException(status_code=501, detail="담당자(조장) 구현 필요")


@router.get("/report/{newcomer_id}")
def get_latest_report(newcomer_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(조장): generated_at 기준 최신 리포트 1개 조회
    raise HTTPException(status_code=501, detail="담당자(조장) 구현 필요")


@router.get("/report/{newcomer_id}/history")
def get_report_history(newcomer_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(조장): generated_at 내림차순 전체 리포트 목록 조회
    raise HTTPException(status_code=501, detail="담당자(조장) 구현 필요")
