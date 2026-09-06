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
    raise HTTPException(status_code=501, detail="담당자(팀원 B) 구현 필요")


@router.get("/assignment")
def get_assignment(
    newcomer_id: str | None = None,
    mentor_id: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    # TODO(팀원 B): newcomer_id -> Assignment 단건, mentor_id -> Assignment 리스트
    raise HTTPException(status_code=501, detail="담당자(팀원 B) 구현 필요")
