"""신입-사수-문서 배정 (담당: 팀원 B) — guidelines 3-1, 3-9.

TODO(팀원 B): 아래는 main.py가 부팅되도록 만든 최소 스텁입니다. 직접 채워서 구현하세요.
"""

from fastapi import APIRouter, Depends, HTTPException

from core.auth import CurrentUser, get_current_user, require_role, require_self

router = APIRouter(tags=["assignment"])


@router.post("/assignment", status_code=201)
def create_assignment(current_user: CurrentUser = Depends(get_current_user)):
    # TODO(팀원 B): require_role(current_user, "mentor") +
    # require_self(current_user, 요청 바디의 mentor_id) 검증 후 Assignment 생성
    # - 이미 그 newcomer_id로 활성 Assignment가 있으면 새 행을 만들지 말고 document_id만
    #   바꿔서 UPDATE (재배정). assigned_at은 최초 생성 시각 그대로 유지 — 여기서 갱신하면
    #   /report/generate의 최초 리포트 기간 기준(assigned_at)이 매번 리셋됨 (guidelines 2-2, 3-1)
    raise HTTPException(status_code=501, detail="담당자(팀원 B) 구현 필요")


@router.get("/assignment")
def get_assignment(
    newcomer_id: str | None = None,
    mentor_id: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    # TODO(팀원 B): newcomer_id -> Assignment 단건, mentor_id -> Assignment 리스트
    # - newcomer_id로 조회 시 require_self(current_user, newcomer_id) 검증
    # - mentor_id로 조회 시 require_role(current_user, "mentor") +
    #   require_self(current_user, mentor_id) 검증
    # (그 전엔 로그인만 하면 아무 신입/사수의 배정 정보나 조회 가능했던 문제 — guidelines 3-9)
    raise HTTPException(status_code=501, detail="담당자(팀원 B) 구현 필요")
