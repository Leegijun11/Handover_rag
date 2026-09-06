"""체크리스트 편집/저장/완료 (담당: 팀원 A) — guidelines 3-5, 3-9, 4-2.

TODO(팀원 A): 아래는 main.py가 부팅되도록 만든 최소 스텁입니다. 직접 채워서 구현하세요.
"""

from fastapi import APIRouter, Depends, HTTPException

from core.auth import CurrentUser, get_current_user, require_role, require_self

router = APIRouter(tags=["checklist"])


@router.post("/checklist", status_code=201)
def save_checklist(current_user: CurrentUser = Depends(get_current_user)):
    # TODO(팀원 A): require_role(current_user, "mentor") 검증 후 items 저장
    # (source="manual"/"ai_draft", newcomer_id 필수)
    raise HTTPException(status_code=501, detail="담당자(팀원 A) 구현 필요")


@router.get("/checklist")
def get_checklist(newcomer_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(팀원 A): newcomer_id로 ChecklistItem 목록 조회 (order 기준 정렬)
    raise HTTPException(status_code=501, detail="담당자(팀원 A) 구현 필요")


@router.patch("/checklist/{item_id}")
def update_checklist_item(item_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(팀원 A): require_role(current_user, "mentor") 검증 후 title/chapter_id 등 수정
    raise HTTPException(status_code=501, detail="담당자(팀원 A) 구현 필요")


@router.patch("/checklist/{item_id}/reorder")
def reorder_checklist_item(item_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(팀원 A): require_role(current_user, "mentor") 검증 후 order 값 수정
    raise HTTPException(status_code=501, detail="담당자(팀원 A) 구현 필요")


@router.post("/checklist/{item_id}/complete")
def complete_checklist_item(item_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # TODO(팀원 A): require_self(current_user, 요청 바디의 newcomer_id) 검증 후
    # 검증 절차 없이 완료 시각만 기록 (셀프 체크)
    raise HTTPException(status_code=501, detail="담당자(팀원 A) 구현 필요")
